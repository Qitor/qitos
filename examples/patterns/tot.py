"""Pattern: Tree-of-Thought (multiple candidate actions + search-based selection)."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.planning import DynamicTreeSearch
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import EpubToolSet
from qitos.render import ClaudeStyleHook

from examples.common import add_common_args, build_model_from_args, make_trace_writer, setup_workspace

THOUGHT_PROMPT = """Question: {question}\nEPUB path: {epub_path}\nEvidence:\n{evidence}\n
Return JSON:
{
  "thoughts": [{"idea": "...", "score": 0.0, "action": {"name": "epub.list_chapters|epub.search|epub.read_chapter", "args": {...}}}],
  "can_answer": true_or_false,
  "answer": "optional"
}
"""


@dataclass
class ToTState(StateSchema):
    epub_path: str = "book.epub"
    question: str = ""
    evidence: List[str] = field(default_factory=list)


class ToTAgent(AgentModule[ToTState, Dict[str, Any], Action]):
    def __init__(self, llm: Any, workspace_root: str):
        registry = ToolRegistry()
        registry.register_toolset(EpubToolSet(workspace_root=workspace_root), namespace="epub")
        super().__init__(tool_registry=registry, llm=llm)

    def init_state(self, task: str, **kwargs: Any) -> ToTState:
        return ToTState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 12)),
            epub_path=str(kwargs.get("epub_path", "book.epub")),
            question=str(kwargs.get("question", "")),
        )

    def observe(self, state: ToTState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {"question": state.question, "epub_path": state.epub_path, "evidence": state.evidence[-8:]}

    def decide(self, state: ToTState, observation: Dict[str, Any]) -> Optional[Decision[Action]]:
        if state.current_step == 0:
            return Decision.act([Action(name="epub.list_chapters", args={"path": state.epub_path})], rationale="bootstrap_catalog")

        raw = self.llm([
            {"role": "system", "content": "Return valid JSON only."},
            {
                "role": "user",
                "content": render_prompt(THOUGHT_PROMPT, {"question": state.question, "epub_path": state.epub_path, "evidence": self._evidence_block(state)}),
            },
        ])
        parsed = self._parse_json(str(raw))
        if not parsed:
            return Decision.act([Action(name="epub.search", args={"path": state.epub_path, "query": state.question, "top_k": 3})], rationale="fallback_search")

        if bool(parsed.get("can_answer")) and str(parsed.get("answer", "")).strip() and len(state.evidence) >= 2:
            return Decision.final(answer=str(parsed["answer"]))

        candidates: List[Decision[Action]] = []
        for item in parsed.get("thoughts", []):
            if not isinstance(item, dict):
                continue
            action = item.get("action") or {}
            name = str(action.get("name", "")).strip()
            args = action.get("args") or {}
            if not name or not isinstance(args, dict):
                continue
            args.setdefault("path", state.epub_path)
            score = float(item.get("score", 0.5))
            candidates.append(Decision.act([Action(name=name, args=args)], rationale=str(item.get("idea", "candidate")), meta={"score": score}))

        if not candidates:
            return Decision.act([Action(name="epub.search", args={"path": state.epub_path, "query": state.question, "top_k": 3})], rationale="fallback_search")
        return Decision.branch(candidates=candidates, rationale="tot_branch")

    def reduce(self, state: ToTState, observation: Dict[str, Any], decision: Decision[Action], action_results: List[Any]) -> ToTState:
        if not action_results:
            return state
        result = action_results[0]
        if isinstance(result, dict):
            if isinstance(result.get("hits"), list):
                for h in result["hits"][:3]:
                    if isinstance(h, dict):
                        state.evidence.append(str(h.get("snippet", "")))
            if isinstance(result.get("content"), str):
                state.evidence.append(result["content"][:320])
        state.evidence = state.evidence[-20:]
        return state

    def _evidence_block(self, state: ToTState) -> str:
        if not state.evidence:
            return "- none"
        return "\n".join(f"- {item}" for item in state.evidence[-8:])

    def _parse_json(self, raw: str) -> Optional[Dict[str, Any]]:
        text = raw.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.add_argument("--task", default="Read EPUB and answer question")
    ap.add_argument("--epub-path", default="book.epub")
    ap.add_argument("--question", default="What is the main argument of chapter 1?")
    ap.add_argument("--max-steps", type=int, default=12)
    args = ap.parse_args()

    root, temp_ctx = setup_workspace(args.workspace)
    model = build_model_from_args(args)
    agent = ToTAgent(llm=model, workspace_root=str(root))
    trace_writer = make_trace_writer(args, "pattern_tot")
    hooks = [] if args.disable_render else [ClaudeStyleHook(output_jsonl=str(root / "render_events.jsonl"), theme=args.theme)]

    engine_kwargs = {"search": DynamicTreeSearch(top_k=2), "env": HostEnv(workspace_root=str(root))}
    if trace_writer is not None:
        engine_kwargs["trace_writer"] = trace_writer

    result = agent.run(
        task=Task(id="pattern_tot", objective=args.task, env_spec=EnvSpec(type="host", config={"workspace_root": str(root)}), budget=TaskBudget(max_steps=args.max_steps)),
        return_state=True,
        hooks=hooks,
        epub_path=args.epub_path,
        question=args.question,
        max_steps=args.max_steps,
        engine_kwargs=engine_kwargs,
    )
    print("workspace:", root)
    print("final_result:", result.state.final_result)
    print("stop_reason:", result.state.stop_reason)
    if trace_writer is not None:
        print("trace_run_dir:", trace_writer.run_dir)
    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()

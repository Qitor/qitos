"""Practical EPUB reader: Tree-of-Thought style branching over chapter evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.planning import DynamicTreeSearch, format_action
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import EpubToolSet
from qitos.render import ClaudeStyleHook

from examples._config import build_model, case_cfg, load_yaml


THOUGHT_PROMPT = """You are reading an EPUB to answer a question.

Question: {question}
EPUB path: {epub_path}
Known evidence snippets:
{evidence}

Propose 2-4 candidate next thoughts as JSON:
{{
  "thoughts": [
    {{
      "idea": "short thought",
      "score": 0.0_to_1.0,
      "action": {{"name": "epub.list_chapters|epub.search|epub.read_chapter", "args": {{...}}}}
    }}
  ],
  "can_answer": true_or_false,
  "answer": "optional draft answer"
}}

Rules:
- If evidence is weak, keep can_answer=false.
- Prefer targeted chapter reads over blind scanning.
- Args must include path for all actions.
"""


@dataclass
class EpubToTState(StateSchema):
    epub_path: str = "book.epub"
    question: str = ""
    thoughts: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    chapter_count: int = 0
    scratchpad: List[str] = field(default_factory=list)


class EpubTreeOfThoughtAgent(AgentModule[EpubToTState, Dict[str, Any], Action]):
    def __init__(self, llm: Any, workspace_root: str):
        registry = ToolRegistry()
        registry.register_toolset(EpubToolSet(workspace_root=workspace_root), namespace="epub")
        super().__init__(tool_registry=registry, llm=llm)

    def init_state(self, task: str, **kwargs: Any) -> EpubToTState:
        return EpubToTState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 14)),
            epub_path=str(kwargs.get("epub_path", "book.epub")),
            question=str(kwargs.get("question", "")),
        )

    def observe(self, state: EpubToTState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "question": state.question,
            "epub_path": state.epub_path,
            "chapter_count": state.chapter_count,
            "evidence": list(state.evidence[-8:]),
            "thoughts": list(state.thoughts[-8:]),
            "scratchpad": list(state.scratchpad[-8:]),
            "memory": env_view.get("memory", {}),
        }

    def decide(self, state: EpubToTState, observation: Dict[str, Any]) -> Optional[Decision[Action]]:
        # Bootstrap with deterministic exploration.
        if state.current_step == 0:
            return Decision.branch(
                candidates=[
                    Decision.act(
                        actions=[Action(name="epub.list_chapters", args={"path": state.epub_path})],
                        rationale="enumerate_chapters",
                        meta={"score": 0.95},
                    ),
                    Decision.act(
                        actions=[Action(name="epub.search", args={"path": state.epub_path, "query": state.question, "top_k": 4})],
                        rationale="keyword_probe",
                        meta={"score": 0.8},
                    ),
                ],
                rationale="tot_bootstrap",
            )

        prompt = render_prompt(
            THOUGHT_PROMPT,
            {
                "question": state.question,
                "epub_path": state.epub_path,
                "evidence": self._evidence_block(state),
            },
        )
        raw = self.llm(
            [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ]
        )

        parsed = self._parse_json(str(raw))
        if not parsed:
            return self._fallback_decision(state)

        can_answer = bool(parsed.get("can_answer", False))
        answer = str(parsed.get("answer", "")).strip()
        if can_answer and answer and len(state.evidence) >= 2:
            return Decision.final(answer=f"Answer: {answer}")

        thoughts = parsed.get("thoughts", [])
        candidates: List[Decision[Action]] = []
        if isinstance(thoughts, list):
            for i, item in enumerate(thoughts):
                if not isinstance(item, dict):
                    continue
                action_payload = item.get("action")
                if not isinstance(action_payload, dict):
                    continue
                name = str(action_payload.get("name", "")).strip()
                args = action_payload.get("args", {})
                if not name or not isinstance(args, dict):
                    continue
                args.setdefault("path", state.epub_path)
                score = item.get("score", 0.5)
                if not isinstance(score, (int, float)):
                    score = 0.5
                idea = str(item.get("idea", "")).strip() or f"candidate_{i}"
                candidates.append(
                    Decision.act(
                        actions=[Action(name=name, args=args)],
                        rationale=idea,
                        meta={"score": float(score), "id": f"tot_{state.current_step}_{i}"},
                    )
                )

        if not candidates:
            return self._fallback_decision(state)
        return Decision.branch(candidates=candidates, rationale="tot_branch")

    def reduce(
        self,
        state: EpubToTState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> EpubToTState:
        if decision.rationale:
            state.thoughts.append(decision.rationale)
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {format_action(decision.actions[0])}")

        if not action_results:
            state.scratchpad = state.scratchpad[-40:]
            state.thoughts = state.thoughts[-40:]
            return state

        result = action_results[0]
        state.scratchpad.append(f"Observation: {result}")

        if isinstance(result, dict):
            if "chapters" in result and isinstance(result.get("chapters"), list):
                state.chapter_count = len(result.get("chapters") or [])
                if result.get("chapters"):
                    first = result["chapters"][0]
                    state.evidence.append(f"chapter_catalog_hint: {first}")
            if "hits" in result and isinstance(result.get("hits"), list):
                for hit in result.get("hits", [])[:3]:
                    if isinstance(hit, dict):
                        state.evidence.append(f"search_hit: {hit.get('snippet', '')}")
            if "content" in result and isinstance(result.get("content"), str):
                text = result["content"].strip()
                if text:
                    state.evidence.append(f"chapter_text: {text[:320]}")

        state.evidence = state.evidence[-20:]
        state.thoughts = state.thoughts[-40:]
        state.scratchpad = state.scratchpad[-40:]
        return state

    def _fallback_decision(self, state: EpubToTState) -> Decision[Action]:
        if state.chapter_count <= 0:
            return Decision.act(
                actions=[Action(name="epub.list_chapters", args={"path": state.epub_path})],
                rationale="fallback_list_chapters",
                meta={"score": 0.6},
            )
        next_idx = min(max(0, len(state.evidence) // 2), max(0, state.chapter_count - 1))
        return Decision.act(
            actions=[
                Action(
                    name="epub.read_chapter",
                    args={"path": state.epub_path, "chapter_index": int(next_idx), "max_chars": 5000},
                )
            ],
            rationale="fallback_read_next",
            meta={"score": 0.55},
        )

    def _evidence_block(self, state: EpubToTState) -> str:
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
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            snippet = text[start : end + 1]
            try:
                return json.loads(snippet)
            except Exception:
                return None
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="examples/config.yaml")
    ap.add_argument("--workspace", default="", help="Optional workspace path")
    args = ap.parse_args()

    cfg = load_yaml(args.config)
    model = build_model(cfg)
    ecfg = case_cfg(cfg, "epub_reader")
    render_cfg = cfg.get("render") or {}

    temp_ctx: Optional[tempfile.TemporaryDirectory] = None
    if args.workspace:
        root = Path(args.workspace)
        root.mkdir(parents=True, exist_ok=True)
    else:
        temp_ctx = tempfile.TemporaryDirectory()
        root = Path(temp_ctx.name)

    epub_path = str(ecfg.get("epub_path", "book.epub"))
    hooks = []
    if bool(render_cfg.get("claude_style", True)):
        output_jsonl = str(root / "render_events.jsonl") if bool(render_cfg.get("save_events_jsonl", True)) else None
        hooks.append(ClaudeStyleHook(output_jsonl=output_jsonl, theme=str(render_cfg.get("theme", "research"))))

    agent = EpubTreeOfThoughtAgent(llm=model, workspace_root=str(root))
    task_obj = Task(
        id="epub_reader_tot_demo",
        objective=str(ecfg.get("task", "Read EPUB and answer question.")),
        env_spec=EnvSpec(type="host", config={"workspace_root": str(root)}),
        budget=TaskBudget(max_steps=int(ecfg.get("max_steps", 14))),
    )
    result = agent.run(
        task=task_obj,
        return_state=True,
        hooks=hooks,
        epub_path=epub_path,
        question=str(ecfg.get("question", "What is the main argument in chapter 1?")),
        max_steps=int(ecfg.get("max_steps", 14)),
        workspace=str(root),
        engine_kwargs={"search": DynamicTreeSearch(top_k=2), "env": HostEnv(workspace_root=str(root))},
    )

    print("workspace:", root)
    print("epub_path:", epub_path)
    print("final_result:", result.state.final_result)
    print("stop_reason:", result.state.stop_reason)
    print("evidence_count:", len(result.state.evidence))

    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()

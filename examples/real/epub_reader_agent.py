"""Practical EPUB reader: Tree-of-Thought style branching over chapter evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.planning import DynamicTreeSearch, format_action
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import EpubToolSet
from qitos.models import OpenAICompatibleModel
from qitos.render import ClaudeStyleHook
from qitos.trace import TraceWriter


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


DEFAULT_MODEL_BASE_URL = "https://api.siliconflow.cn/v1/"
DEFAULT_MODEL_API_KEY = ""
DEFAULT_MODEL_NAME = "Qwen/Qwen3-8B"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048

DEFAULT_MAX_STEPS = 12
DEFAULT_TASK = "Read the EPUB and answer the question with concise evidence."
DEFAULT_EPUB_PATH = "book.epub"
DEFAULT_QUESTION = "What is the main argument of chapter 1?"
DEFAULT_RENDER_THEME = "research"


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
    ap.add_argument("--workspace", default="./playground", help="Optional workspace path")
    ap.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    ap.add_argument("--api-key", default=DEFAULT_MODEL_API_KEY)
    ap.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    ap.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--epub-path", default=DEFAULT_EPUB_PATH)
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    ap.add_argument("--theme", default=DEFAULT_RENDER_THEME)
    ap.add_argument("--trace-logdir", default="./runs")
    ap.add_argument("--trace-prefix", default="qitos")
    ap.add_argument("--disable-trace", action="store_true")
    ap.add_argument("--disable-render", action="store_true")
    args = ap.parse_args()

    api_key = str(args.api_key).strip() or os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("QITOS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing API key. Set --api-key or OPENAI_API_KEY/QITOS_API_KEY environment variable.")

    model = OpenAICompatibleModel(
        model=str(args.model_name),
        api_key=api_key,
        base_url=str(args.model_base_url) or None,
        temperature=float(args.temperature),
        max_tokens=int(args.max_tokens),
    )

    temp_ctx: Optional[tempfile.TemporaryDirectory] = None
    if args.workspace:
        root = Path(args.workspace)
        root.mkdir(parents=True, exist_ok=True)
    else:
        temp_ctx = tempfile.TemporaryDirectory()
        root = Path(temp_ctx.name)

    epub_path = str(args.epub_path)
    hooks = []
    if not args.disable_render:
        output_jsonl = str(root / "render_events.jsonl")
        hooks.append(ClaudeStyleHook(output_jsonl=output_jsonl, theme=str(args.theme)))

    agent = EpubTreeOfThoughtAgent(llm=model, workspace_root=str(root))
    trace_writer = None
    if not args.disable_trace:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        run_id = f"{args.trace_prefix}_epub_reader_{stamp}"
        trace_writer = TraceWriter(
            output_dir=str(Path(args.trace_logdir).expanduser().resolve()),
            run_id=run_id,
            strict_validate=True,
            metadata={"model_id": str(args.model_name)},
        )
    task_obj = Task(
        id="epub_reader_tot_demo",
        objective=str(args.task),
        env_spec=EnvSpec(type="host", config={"workspace_root": str(root)}),
        budget=TaskBudget(max_steps=int(args.max_steps)),
    )
    engine_kwargs = {"search": DynamicTreeSearch(top_k=2), "env": HostEnv(workspace_root=str(root))}
    if trace_writer is not None:
        engine_kwargs["trace_writer"] = trace_writer

    result = agent.run(
        task=task_obj,
        return_state=True,
        hooks=hooks,
        epub_path=epub_path,
        question=str(args.question),
        max_steps=int(args.max_steps),
        workspace=str(root),
        engine_kwargs=engine_kwargs,
    )

    print("workspace:", root)
    print("epub_path:", epub_path)
    print("final_result:", result.state.final_result)
    print("stop_reason:", result.state.stop_reason)
    print("evidence_count:", len(result.state.evidence))
    if trace_writer is not None:
        print("trace_run_dir:", trace_writer.run_dir)

    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()

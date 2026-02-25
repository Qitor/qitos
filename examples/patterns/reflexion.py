"""Pattern: Reflexion (self-critique with citations, missing/superfluous checks, and revision)."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import HTMLExtractText, HTTPGet
from qitos.render import ClaudeStyleHook

from examples.common import add_common_args, build_model_from_args, make_trace_writer, setup_workspace

REFLEXION_PROMPT = """You are a reflexion actor-critic.

Task: {task}
Source URL: {target_url}
Source text:
{text}

Current draft answer:
{draft}

Previous reflections:
{reflections}

Return valid JSON only:
{
  "answer": "revised answer",
  "citations": [{"source": "source_text", "quote": "exact supporting quote"}],
  "critique": {
    "missing": ["missing aspect 1", "..."],
    "superfluous": ["unnecessary claim 1", "..."],
    "grounding": ["claim X is/ is not grounded because ..."],
    "needs_revision": true_or_false
  }
}

Hard constraints:
- Critique must be grounded in source text and must mention evidence quality.
- Always provide at least 2 citations when possible.
- Explicitly list both missing and superfluous aspects.
- No markdown, no extra text, JSON only.
"""


@dataclass
class ReflexionState(StateSchema):
    target_url: str = ""
    page_html: str = ""
    page_text: str = ""
    draft_answer: str = ""
    reflections: List[Dict[str, Any]] = field(default_factory=list)
    max_reflections: int = 2


class ReflexionAgent(AgentModule[ReflexionState, Dict[str, Any], Action]):
    def __init__(self, llm: Any):
        registry = ToolRegistry()
        registry.register(HTTPGet())
        registry.register(HTMLExtractText())
        super().__init__(tool_registry=registry, llm=llm)

    def init_state(self, task: str, **kwargs: Any) -> ReflexionState:
        return ReflexionState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 12)),
            target_url=str(kwargs.get("target_url", "")),
            max_reflections=int(kwargs.get("max_reflections", 2)),
        )

    def decide(self, state: ReflexionState, observation: Dict[str, Any]) -> Optional[Decision[Action]]:
        if not state.page_html:
            return Decision.act([Action(name="http_get", args={"url": state.target_url})], rationale="fetch_source")
        if not state.page_text:
            return Decision.act([Action(name="extract_web_text", args={"html": state.page_html, "max_chars": 12000})], rationale="extract_source_text")

        payload = self._reflect(state)
        if payload is None:
            return Decision.final("Failed to produce valid reflexion JSON output")

        critique = payload.get("critique") if isinstance(payload.get("critique"), dict) else {}
        needs_revision = bool(critique.get("needs_revision", False))
        answer = str(payload.get("answer", "")).strip()

        state.draft_answer = answer
        state.reflections.append(payload)

        if needs_revision and len(state.reflections) <= state.max_reflections:
            return Decision.wait(rationale="reflexion_revision_cycle")

        citations = payload.get("citations") if isinstance(payload.get("citations"), list) else []
        return Decision.final(answer=f"{answer}\n\nCitations: {citations}")

    def reduce(self, state: ReflexionState, observation: Dict[str, Any], decision: Decision[Action]) -> ReflexionState:
        action_results = observation.get("action_results", []) if isinstance(observation, dict) else []
        if action_results:
            first = action_results[0]
            if isinstance(first, dict):
                if "content" in first and decision.actions and decision.actions[0].name == "http_get":
                    state.page_html = str(first.get("content", ""))
                if "content" in first and decision.actions and decision.actions[0].name == "extract_web_text":
                    state.page_text = str(first.get("content", ""))
        return state

    def _reflect(self, state: ReflexionState) -> Optional[Dict[str, Any]]:
        raw = self.llm(
            [
                {"role": "system", "content": "Return valid JSON only."},
                {
                    "role": "user",
                    "content": render_prompt(
                        REFLEXION_PROMPT,
                        {
                            "task": state.task,
                            "target_url": state.target_url,
                            "text": state.page_text[:9000],
                            "draft": state.draft_answer or "<empty>",
                            "reflections": json.dumps(state.reflections[-2:], ensure_ascii=False),
                        },
                    ),
                },
            ]
        )
        text = str(raw).strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
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
    ap.add_argument("--task", default="Summarize key content and provide grounded claims")
    ap.add_argument("--target-url", default="https://www.thepaper.cn/newsDetail_forward_32639776")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--max-reflections", type=int, default=2)
    args = ap.parse_args()

    root, temp_ctx = setup_workspace(args.workspace)
    model = build_model_from_args(args)
    agent = ReflexionAgent(llm=model)
    trace_writer = make_trace_writer(args, "pattern_reflexion")
    hooks = [] if args.disable_render else [ClaudeStyleHook(output_jsonl=str(root / "render_events.jsonl"), theme=args.theme)]

    engine_kwargs = {"env": HostEnv(workspace_root=str(root))}
    if trace_writer is not None:
        engine_kwargs["trace_writer"] = trace_writer

    result = agent.run(
        task=Task(id="pattern_reflexion", objective=args.task, env_spec=EnvSpec(type="host", config={"workspace_root": str(root)}), budget=TaskBudget(max_steps=args.max_steps)),
        return_state=True,
        hooks=hooks,
        target_url=args.target_url,
        max_steps=args.max_steps,
        max_reflections=args.max_reflections,
        engine_kwargs=engine_kwargs,
    )
    print("workspace:", root)
    print("final_result:", result.state.final_result)
    print("reflections:", len(result.state.reflections))
    print("stop_reason:", result.state.stop_reason)
    if trace_writer is not None:
        print("trace_run_dir:", trace_writer.run_dir)
    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()

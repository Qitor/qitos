"""Practical computer-use ReAct agent for web-to-report workflows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.parser import JsonDecisionParser
from qitos.kit.planning import format_action
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import HTMLExtractText, HTTPGet, ReadFile, RunCommand, WriteFile
from qitos.models import OpenAICompatibleModel
from qitos.render import ClaudeStyleHook
from qitos.trace import TraceWriter
from examples.common import recent_rationales_from_scratchpad


SYSTEM_PROMPT = """You are a computer-use research assistant.

Goal:
- Investigate target web pages.
- Extract key facts.
- Produce a concise report file.

Workflow preference:
1) Fetch page via http_get.
2) Convert HTML to readable text via extract_web_text.
3) Draft report.md via write_file.
4) Optionally verify with read_file.
5) End with Final Answer.

Rules:
- One tool call per step.
- Do not fabricate page content.
- Keep report factual and short.

Available tools:
{tool_schema}

Return JSON only, with this schema:
1) Act:
{
  "mode": "act",
  "rationale": "short reasoning",
  "actions": [
    {
      "name": "tool_name",
      "args": {"key": "value"}
    }
  ]
}

2) Final:
{
  "mode": "final",
  "rationale": "short reasoning",
  "final_answer": "what was delivered"
}

3) Wait:
{
  "mode": "wait",
  "rationale": "why waiting"
}

Constraints:
- Return valid JSON only; no markdown, no code block, no extra text.
- Use exactly one action in act mode.
- Put observed values as literal JSON values in args.
"""


DEFAULT_MODEL_BASE_URL = "https://api.siliconflow.cn/v1/"
DEFAULT_MODEL_API_KEY = ""
DEFAULT_MODEL_NAME = "Qwen/Qwen3-8B"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048

DEFAULT_MAX_STEPS = 10
DEFAULT_TASK = "Visit target URL, summarize key content, and write report.md."
DEFAULT_TARGET_URL = "https://www.thepaper.cn/newsDetail_forward_32639776"
DEFAULT_REPORT_FILE = "report.md"
DEFAULT_RENDER_THEME = "research"


@dataclass
class ComputerUseState(StateSchema):
    target_url: str = ""
    report_file: str = "report.md"
    scratchpad: List[str] = field(default_factory=list)


class ComputerUseReActAgent(AgentModule[ComputerUseState, Dict[str, Any], Action]):
    def __init__(self, llm: Any, workspace_root: str):
        registry = ToolRegistry()
        registry.register(HTTPGet())
        registry.register(HTMLExtractText())
        registry.register(RunCommand(cwd=workspace_root))
        registry.register(WriteFile(root_dir=workspace_root))
        registry.register(ReadFile(root_dir=workspace_root))
        super().__init__(tool_registry=registry, llm=llm, model_parser=JsonDecisionParser())

    def init_state(self, task: str, **kwargs: Any) -> ComputerUseState:
        return ComputerUseState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 12)),
            target_url=str(kwargs.get("target_url", "")),
            report_file=str(kwargs.get("report_file", "report.md")),
        )

    def observe(self, state: ComputerUseState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "target_url": state.target_url,
            "report_file": state.report_file,
            "scratchpad": list(state.scratchpad[-16:]),
            "memory": env_view.get("memory", {}),
        }

    def build_system_prompt(self, state: ComputerUseState) -> str | None:
        schema = self.tool_registry.get_tool_descriptions() if self.tool_registry else ""
        return render_prompt(SYSTEM_PROMPT, {"tool_schema": schema})

    def prepare(self, state: ComputerUseState, observation: Dict[str, Any]) -> str:
        lines = [
            f"Task: {state.task}",
            f"Target URL: {state.target_url}",
            f"Report file: {state.report_file}",
            f"Step: {state.current_step}/{state.max_steps}",
        ]
        rationales = recent_rationales_from_scratchpad(state.scratchpad, max_items=6)
        if rationales:
            lines.append("Recent rationale:")
            lines.extend(f"- {x}" for x in rationales)
        if state.scratchpad:
            lines.append("Recent trajectory:")
            lines.extend(state.scratchpad[-8:])
        return "\n".join(lines)

    def reduce(
        self,
        state: ComputerUseState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> ComputerUseState:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {format_action(decision.actions[0])}")
        if action_results:
            first = action_results[0]
            state.scratchpad.append(f"Observation: {first}")

        state.scratchpad = state.scratchpad[-40:]
        return state

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="./playground", help="Optional workspace path")
    ap.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    ap.add_argument("--api-key", default=DEFAULT_MODEL_API_KEY)
    ap.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    ap.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--target-url", default=DEFAULT_TARGET_URL)
    ap.add_argument("--report-file", default=DEFAULT_REPORT_FILE)
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

    hooks = []
    if not args.disable_render:
        output_jsonl = str(root / "render_events.jsonl")
        hooks.append(ClaudeStyleHook(output_jsonl=output_jsonl, theme=str(args.theme)))

    agent = ComputerUseReActAgent(llm=model, workspace_root=str(root))
    trace_writer = None
    if not args.disable_trace:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        run_id = f"{args.trace_prefix}_computer_use_{stamp}"
        trace_writer = TraceWriter(
            output_dir=str(Path(args.trace_logdir).expanduser().resolve()),
            run_id=run_id,
            strict_validate=True,
            metadata={"model_id": str(args.model_name)},
        )
    task_obj = Task(
        id="computer_use_react_demo",
        objective=str(args.task),
        env_spec=EnvSpec(type="host", config={"workspace_root": str(root)}),
        budget=TaskBudget(max_steps=int(args.max_steps)),
    )
    engine_kwargs = {"env": HostEnv(workspace_root=str(root))}
    if trace_writer is not None:
        engine_kwargs["trace_writer"] = trace_writer

    result = agent.run(
        task=task_obj,
        return_state=True,
        hooks=hooks,
        target_url=str(args.target_url),
        report_file=str(args.report_file),
        max_steps=int(args.max_steps),
        workspace=str(root),
        engine_kwargs=engine_kwargs,
    )

    report_path = root / str(args.report_file)
    print("workspace:", root)
    print("final_result:", result.state.final_result)
    print("stop_reason:", result.state.stop_reason)
    if trace_writer is not None:
        print("trace_run_dir:", trace_writer.run_dir)
    if report_path.exists():
        print("report_file:", report_path)
        print("report_preview:\n", report_path.read_text(encoding="utf-8")[:500])
    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()

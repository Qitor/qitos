"""Practical computer-use ReAct agent for web-to-report workflows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.parser import ReActTextParser
from qitos.kit.planning import format_action
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import HTMLExtractText, HTTPGet, ReadFile, RunCommand, WriteFile
from qitos.render import ClaudeStyleHook

from examples._config import build_model, case_cfg, load_yaml


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
- Output must be plain text only (no markdown code block, no JSON wrapper).

STRICT OUTPUT CONTRACT (must follow exactly):
1) Tool call:
Thought: <one short sentence>
Action: tool_name(arg1=value1, arg2=value2)

2) Final:
Thought: <one short sentence>
Final Answer: <final report summary>

Formatting constraints:
- Action line must be function-style only.
- NEVER output dict/object style action.
- NEVER output:
  - Action: {'name': 'http_get', 'args': {...}}
  - Action: {"name":"http_get","args":{...}}
  - Action: [ ... ]
- Use Python-literal arguments for strings/numbers/bools only.
- When passing observed content to a tool, pass the literal text value directly.
  - Correct: Action: extract_web_text(html='<html>...</html>', max_chars=6000)
  - Wrong:   Action: extract_web_text(html=Observation['content'], max_chars=6000)
- Do not add any extra headings.

Self-check before you answer:
- If your Action line is not function-style, rewrite it before sending.

Available tools:
{tool_schema}

Output format:
Thought: <short reasoning>
Action: <tool_name>(arg=value, ...)
or
Final Answer: <what was delivered>
"""


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
        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())

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
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--workspace", default="./playground", help="Optional workspace path")
    args = ap.parse_args()

    cfg = load_yaml(args.config)
    model = build_model(cfg)
    ccfg = case_cfg(cfg, "computer_use")
    render_cfg = cfg.get("render") or {}

    temp_ctx: Optional[tempfile.TemporaryDirectory] = None
    if args.workspace:
        root = Path(args.workspace)
        root.mkdir(parents=True, exist_ok=True)
    else:
        temp_ctx = tempfile.TemporaryDirectory()
        root = Path(temp_ctx.name)

    hooks = []
    if bool(render_cfg.get("claude_style", True)):
        output_jsonl = str(root / "render_events.jsonl") if bool(render_cfg.get("save_events_jsonl", True)) else None
        hooks.append(ClaudeStyleHook(output_jsonl=output_jsonl, theme=str(render_cfg.get("theme", "research"))))

    agent = ComputerUseReActAgent(llm=model, workspace_root=str(root))
    task_obj = Task(
        id="computer_use_react_demo",
        objective=str(ccfg.get("task", "Browse target URL and write report.")),
        env_spec=EnvSpec(type="host", config={"workspace_root": str(root)}),
        budget=TaskBudget(max_steps=int(ccfg.get("max_steps", 12))),
    )
    result = agent.run(
        task=task_obj,
        return_state=True,
        hooks=hooks,
        target_url=str(ccfg.get("target_url", "https://www.thepaper.cn/newsDetail_forward_32639776")),
        report_file=str(ccfg.get("report_file", "report.md")),
        max_steps=int(ccfg.get("max_steps", 12)),
        workspace=str(root),
        engine_kwargs={"env": HostEnv(workspace_root=str(root))},
    )

    report_path = root / str(ccfg.get("report_file", "report.md"))
    print("workspace:", root)
    print("final_result:", result.state.final_result)
    print("stop_reason:", result.state.stop_reason)
    if report_path.exists():
        print("report_file:", report_path)
        print("report_preview:\n", report_path.read_text(encoding="utf-8")[:500])
    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()

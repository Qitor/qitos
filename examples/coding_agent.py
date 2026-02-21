"""Practical coding agent: memory.md-based ReAct + self-reflection."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.critic import ReActSelfReflectionCritic
from qitos.kit.env import HostEnv
from qitos.kit.memory import MarkdownFileMemory
from qitos.kit.parser import ReActTextParser
from qitos.kit.planning import format_action
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import EditorToolSet, RunCommand
from qitos.render import ClaudeStyleHook

from examples._config import build_model, case_cfg, load_yaml


SYSTEM_PROMPT = """You are a production-grade coding agent.

Mission:
- Repair code in the workspace.
- Validate using tests or check commands.
- Keep patches minimal and reversible.

Execution protocol:
1. Start by inspecting the target file.
2. Apply one precise edit per step.
3. Run verification frequently.
4. If a command succeeds and confirms the requirement, end with Final Answer.

Hard constraints:
- Exactly one tool call per step.
- Never invent tool output.
- If the previous attempt failed, explicitly adapt using memory and reflection.

Available tools:
{tool_schema}

Output format:
Thought: <short reasoning>
Action: <tool_name>(arg=value, ...)
or
Final Answer: <what changed + verification proof>
"""


@dataclass
class CodingState(StateSchema):
    scratchpad: List[str] = field(default_factory=list)
    target_file: str = "buggy_module.py"
    test_command: str = ""
    expected_snippet: str = ""


class CodingMemoryReactAgent(AgentModule[CodingState, Dict[str, Any], Action]):
    def __init__(self, llm: Any, workspace_root: str):
        registry = ToolRegistry()
        registry.include(EditorToolSet(workspace_root=workspace_root))
        registry.register(RunCommand(cwd=workspace_root))
        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())

    def init_state(self, task: str, **kwargs: Any) -> CodingState:
        return CodingState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 14)),
            target_file=str(kwargs.get("target_file", "buggy_module.py")),
            test_command=str(kwargs.get("test_command", "")),
            expected_snippet=str(kwargs.get("expected_snippet", "")),
        )

    def build_memory_query(self, state: CodingState, env_view: Dict[str, Any]) -> Dict[str, Any] | None:
        return {"format": "records", "max_items": 12}

    def observe(self, state: CodingState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "target_file": state.target_file,
            "test_command": state.test_command,
            "expected_snippet": state.expected_snippet,
            "scratchpad": list(state.scratchpad[-20:]),
            "memory": env_view.get("memory", {}),
            "current_step": state.current_step,
            "max_steps": state.max_steps,
        }

    def build_system_prompt(self, state: CodingState) -> str | None:
        schema = self.tool_registry.get_tool_descriptions() if self.tool_registry else ""
        return render_prompt(SYSTEM_PROMPT, {"tool_schema": schema})

    def prepare(self, state: CodingState, observation: Dict[str, Any]) -> str:
        lines = [
            f"Task: {state.task}",
            f"Target file: {state.target_file}",
            f"Expected snippet: {state.expected_snippet}",
            f"Verification command: {state.test_command}",
            f"Step: {state.current_step}/{state.max_steps}",
        ]
        memory = observation.get("memory", {})
        if isinstance(memory, dict) and memory.get("summary"):
            lines.append("Memory summary:")
            lines.append(str(memory["summary"]))
        if state.scratchpad:
            lines.append("Recent trajectory:")
            lines.extend(state.scratchpad[-10:])
        return "\n".join(lines)

    def reduce(
        self,
        state: CodingState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> CodingState:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            first_action = decision.actions[0]
            state.scratchpad.append(f"Action: {format_action(first_action)}")

        if action_results:
            first = action_results[0]
            state.scratchpad.append(f"Observation: {first}")

            action_name = ""
            if decision.actions:
                raw = decision.actions[0]
                if isinstance(raw, Action):
                    action_name = raw.name
                elif isinstance(raw, dict):
                    action_name = str(raw.get("name", ""))

            if (
                action_name == "run_command"
                and isinstance(first, dict)
                and int(first.get("returncode", 1)) == 0
            ):
                state.final_result = (
                    "Verification command succeeded. "
                    f"Requirement met for {state.target_file}."
                )

        state.scratchpad = state.scratchpad[-40:]
        return state


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--workspace", default="./playground", help="Optional workspace path. Uses temp workspace when empty.")
    args = ap.parse_args()

    cfg = load_yaml(args.config)
    model = build_model(cfg)
    ccfg = case_cfg(cfg, "coding")
    render_cfg = cfg.get("render") or {}

    temp_ctx: Optional[tempfile.TemporaryDirectory] = None
    if args.workspace:
        root = Path(args.workspace)
        root.mkdir(parents=True, exist_ok=True)
    else:
        temp_ctx = tempfile.TemporaryDirectory()
        root = Path(temp_ctx.name)

    target = root / str(ccfg.get("file", "buggy_module.py"))
    if not target.exists():
        target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    memory_path = root / "memory.md"
    hooks = []
    if bool(render_cfg.get("claude_style", True)):
        output_jsonl = str(root / "render_events.jsonl") if bool(render_cfg.get("save_events_jsonl", True)) else None
        hooks.append(ClaudeStyleHook(output_jsonl=output_jsonl, theme=str(render_cfg.get("theme", "research"))))

    agent = CodingMemoryReactAgent(llm=model, workspace_root=str(root))
    task_obj = Task(
        id="coding_react_reflection_demo",
        objective=str(ccfg.get("task", "Fix the bug and pass tests.")),
        env_spec=EnvSpec(type="host", config={"workspace_root": str(root)}),
        budget=TaskBudget(max_steps=int(ccfg.get("max_steps", 14))),
    )
    result = agent.run(
        task=task_obj,
        return_state=True,
        hooks=hooks,
        target_file=str(ccfg.get("file", "buggy_module.py")),
        test_command=str(ccfg.get("test_command", "")),
        expected_snippet=str(ccfg.get("expected_snippet", "")),
        max_steps=int(ccfg.get("max_steps", 14)),
        workspace=str(root),
        engine_kwargs={
            "memory": MarkdownFileMemory(path=str(memory_path)),
            "critics": [ReActSelfReflectionCritic(max_retries=2)],
            "env": HostEnv(workspace_root=str(root)),
        },
    )

    print("workspace:", root)
    print("final_result:", result.state.final_result)
    print("stop_reason:", result.state.stop_reason)
    print("memory_md:", memory_path)
    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()

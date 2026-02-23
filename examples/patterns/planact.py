"""Pattern: Plan-Act (first make plan, then execute one step at a time)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.parser import ReActTextParser
from qitos.kit.planning import format_action, parse_numbered_plan
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import EditorToolSet, RunCommand
from qitos.render import ClaudeStyleHook

from examples.common import (
    add_common_args,
    build_model_from_args,
    make_trace_writer,
    recent_rationales_from_scratchpad,
    setup_workspace,
)

PLAN_PROMPT = """Task: {task}\nTarget file: {target_file}\nReturn a numbered plan (3-5 steps), last step must run tests."""

EXEC_PROMPT = """You execute one plan step each turn.
Current plan step: {current_step}
Tools:\n{tool_schema}

Output:
Thought: <short reasoning>
Action: <tool_name>(arg=value, ...)
or
Final Answer: <result>
"""


@dataclass
class PlanActState(StateSchema):
    plan_steps: List[str] = field(default_factory=list)
    cursor: int = 0
    target_file: str = "buggy_module.py"
    test_command: str = 'python -c "import buggy_module; assert buggy_module.add(20, 22) == 42"'
    scratchpad: List[str] = field(default_factory=list)


class PlanActAgent(AgentModule[PlanActState, Dict[str, Any], Action]):
    def __init__(self, llm: Any, workspace_root: str):
        registry = ToolRegistry()
        registry.include(EditorToolSet(workspace_root=workspace_root))
        registry.register(RunCommand(cwd=workspace_root))
        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())

    def init_state(self, task: str, **kwargs: Any) -> PlanActState:
        return PlanActState(task=task, max_steps=int(kwargs.get("max_steps", 10)))

    def observe(self, state: PlanActState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "plan_steps": state.plan_steps,
            "cursor": state.cursor,
            "current_step": self._current_step_text(state),
            "scratchpad": state.scratchpad[-8:],
        }

    def build_system_prompt(self, state: PlanActState) -> str | None:
        return render_prompt(EXEC_PROMPT, {"current_step": self._current_step_text(state), "tool_schema": self.tool_registry.get_tool_descriptions()})

    def prepare(self, state: PlanActState, observation: Dict[str, Any]) -> str:
        lines = [
            f"Task: {state.task}",
            f"Plan cursor: {state.cursor}/{len(state.plan_steps)}",
            f"Current step: {self._current_step_text(state)}",
            f"Step: {state.current_step}/{state.max_steps}",
        ]
        if state.plan_steps:
            lines.append("Plan:")
            for i, item in enumerate(state.plan_steps):
                marker = "->" if i == state.cursor else "  "
                lines.append(f"{marker} [{i}] {item}")
        rationales = recent_rationales_from_scratchpad(state.scratchpad, max_items=5)
        if rationales:
            lines.append("Recent rationale:")
            lines.extend(f"- {x}" for x in rationales)
        if state.scratchpad:
            lines.append("Recent trajectory:")
            lines.extend(state.scratchpad[-8:])
        return "\n".join(lines)

    def decide(self, state: PlanActState, observation: Dict[str, Any]) -> Optional[Decision[Action]]:
        if not state.plan_steps or state.cursor >= len(state.plan_steps):
            if not self._plan(state):
                return Decision.final("Failed to build a valid plan")
            return Decision.wait("plan_ready")
        return None

    def reduce(self, state: PlanActState, observation: Dict[str, Any], decision: Decision[Action], action_results: List[Any]) -> PlanActState:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {format_action(decision.actions[0])}")
        if action_results:
            result = action_results[0]
            state.scratchpad.append(f"Observation: {result}")
            if isinstance(result, dict) and result.get("status") == "success":
                state.cursor += 1
            if isinstance(result, dict) and int(result.get("returncode", 1)) == 0:
                state.final_result = "Verification passed"
                state.cursor = len(state.plan_steps)
        state.scratchpad = state.scratchpad[-40:]
        return state

    def _plan(self, state: PlanActState) -> bool:
        prompt = render_prompt(PLAN_PROMPT, {"task": state.task, "target_file": state.target_file})
        raw = self.llm([
            {"role": "system", "content": "Return numbered plan only."},
            {"role": "user", "content": prompt},
        ])
        plan = parse_numbered_plan(str(raw))
        if not plan:
            return False
        state.plan_steps = plan
        state.cursor = 0
        state.scratchpad.append("Plan: " + " | ".join(plan))
        return True

    def _current_step_text(self, state: PlanActState) -> str:
        if state.cursor < 0 or state.cursor >= len(state.plan_steps):
            return "none"
        return state.plan_steps[state.cursor]


def main() -> None:
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.add_argument("--task", default="Fix buggy_module.py and verify with tests")
    ap.add_argument("--max-steps", type=int, default=10)
    args = ap.parse_args()

    root, temp_ctx = setup_workspace(args.workspace)
    target = root / "buggy_module.py"
    if not target.exists():
        target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    model = build_model_from_args(args)
    agent = PlanActAgent(llm=model, workspace_root=str(root))
    trace_writer = make_trace_writer(args, "pattern_planact")
    hooks = [] if args.disable_render else [ClaudeStyleHook(output_jsonl=str(root / "render_events.jsonl"), theme=args.theme)]

    engine_kwargs = {"env": HostEnv(workspace_root=str(root))}
    if trace_writer is not None:
        engine_kwargs["trace_writer"] = trace_writer

    result = agent.run(
        task=Task(id="pattern_planact", objective=args.task, env_spec=EnvSpec(type="host", config={"workspace_root": str(root)}), budget=TaskBudget(max_steps=args.max_steps)),
        return_state=True,
        hooks=hooks,
        max_steps=args.max_steps,
        engine_kwargs=engine_kwargs,
    )
    print("workspace:", root)
    print("plan:", result.state.plan_steps)
    print("final_result:", result.state.final_result)
    print("stop_reason:", result.state.stop_reason)
    if trace_writer is not None:
        print("trace_run_dir:", trace_writer.run_dir)
    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()

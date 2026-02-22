"""Pattern: ReAct (single-step think-act loop with function-style actions)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Dict, List

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.parser import ReActTextParser
from qitos.kit.planning import format_action
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import EditorToolSet, RunCommand
from qitos.render import ClaudeStyleHook

from examples.common import add_common_args, build_model_from_args, make_trace_writer, setup_workspace

SYSTEM_PROMPT = """You are a concise ReAct agent.

Rules:
- Exactly one tool call per step.
- Use function-style action only.

Tools:
{tool_schema}

Output:
Thought: <short reasoning>
Action: <tool_name>(arg=value, ...)
or
Final Answer: <result>
"""


@dataclass
class ReactState(StateSchema):
    scratchpad: List[str] = field(default_factory=list)


class ReactAgent(AgentModule[ReactState, Dict[str, Any], Action]):
    def __init__(self, llm: Any, workspace_root: str):
        registry = ToolRegistry()
        registry.include(EditorToolSet(workspace_root=workspace_root))
        registry.register(RunCommand(cwd=workspace_root))
        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())

    def init_state(self, task: str, **kwargs: Any) -> ReactState:
        return ReactState(task=task, max_steps=int(kwargs.get("max_steps", 8)))

    def observe(self, state: ReactState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {"task": state.task, "scratchpad": state.scratchpad[-8:]}

    def build_system_prompt(self, state: ReactState) -> str | None:
        return render_prompt(SYSTEM_PROMPT, {"tool_schema": self.tool_registry.get_tool_descriptions()})

    def prepare(self, state: ReactState, observation: Dict[str, Any]) -> str:
        parts = [f"Task: {state.task}", f"Step: {state.current_step}/{state.max_steps}"]
        if state.scratchpad:
            parts.extend(["Recent:", *state.scratchpad[-6:]])
        return "\n".join(parts)

    def reduce(self, state: ReactState, observation: Dict[str, Any], decision: Decision[Action], action_results: List[Any]) -> ReactState:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {format_action(decision.actions[0])}")
        if action_results:
            state.scratchpad.append(f"Observation: {action_results[0]}")
        state.scratchpad = state.scratchpad[-30:]
        return state


def main() -> None:
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.add_argument("--task", default="Open buggy_module.py and fix add(a,b) to return a+b, then run tests")
    ap.add_argument("--max-steps", type=int, default=8)
    args = ap.parse_args()

    root, temp_ctx = setup_workspace(args.workspace)
    target = root / "buggy_module.py"
    if not target.exists():
        target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    model = build_model_from_args(args)
    agent = ReactAgent(llm=model, workspace_root=str(root))
    trace_writer = make_trace_writer(args, "pattern_react")
    hooks = [] if args.disable_render else [ClaudeStyleHook(output_jsonl=str(root / "render_events.jsonl"), theme=args.theme)]

    engine_kwargs = {"env": HostEnv(workspace_root=str(root))}
    if trace_writer is not None:
        engine_kwargs["trace_writer"] = trace_writer

    result = agent.run(
        task=Task(id="pattern_react", objective=args.task, env_spec=EnvSpec(type="host", config={"workspace_root": str(root)}), budget=TaskBudget(max_steps=args.max_steps)),
        return_state=True,
        hooks=hooks,
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

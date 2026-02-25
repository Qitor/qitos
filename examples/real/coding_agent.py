"""Practical coding agent: memory.md-based ReAct + self-reflection."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
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
from qitos.models import OpenAICompatibleModel
from qitos.render import ClaudeStyleHook
from qitos.trace import TraceWriter
from examples.common import recent_rationales_from_scratchpad


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


DEFAULT_MODEL_BASE_URL = "https://api.siliconflow.cn/v1/"
DEFAULT_MODEL_API_KEY = ""
DEFAULT_MODEL_NAME = "Qwen/Qwen3-8B"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048

DEFAULT_MAX_STEPS = 14
DEFAULT_TASK = "Fix the bug in buggy_module.py and make tests pass."
DEFAULT_FILE = "buggy_module.py"
DEFAULT_TEST_COMMAND = 'python -c "import buggy_module; assert buggy_module.add(20, 22) == 42"'
DEFAULT_EXPECTED_SNIPPET = "return a + b"
DEFAULT_RENDER_THEME = "research"


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

    def build_system_prompt(self, state: CodingState) -> str | None:
        schema = self.tool_registry.get_tool_descriptions() if self.tool_registry else ""
        return render_prompt(SYSTEM_PROMPT, {"tool_schema": schema})

    def prepare(self, state: CodingState) -> str:
        lines = [
            f"Task: {state.task}",
            f"Target file: {state.target_file}",
            f"Expected snippet: {state.expected_snippet}",
            f"Verification command: {state.test_command}",
            f"Step: {state.current_step}/{state.max_steps}",
        ]
        rationales = recent_rationales_from_scratchpad(state.scratchpad, max_items=6)
        if rationales:
            lines.append("Recent rationale:")
            lines.extend(f"- {x}" for x in rationales)
        if state.scratchpad:
            lines.append("Recent trajectory:")
            lines.extend(state.scratchpad[-10:])
        return "\n".join(lines)

    def reduce(
        self,
        state: CodingState,
        observation: Dict[str, Any],
        decision: Decision[Action],
            ) -> CodingState:
        action_results = observation.get("action_results", []) if isinstance(observation, dict) else []
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
    ap.add_argument("--workspace", default="./playground", help="Optional workspace path")
    ap.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    ap.add_argument("--api-key", default=DEFAULT_MODEL_API_KEY)
    ap.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    ap.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--test-command", default=DEFAULT_TEST_COMMAND)
    ap.add_argument("--expected-snippet", default=DEFAULT_EXPECTED_SNIPPET)
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

    target = root / str(args.file)
    if not target.exists():
        target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    memory_path = root / "memory.md"
    hooks = []
    if not args.disable_render:
        output_jsonl = str(root / "render_events.jsonl")
        hooks.append(ClaudeStyleHook(output_jsonl=output_jsonl, theme=str(args.theme)))

    agent = CodingMemoryReactAgent(llm=model, workspace_root=str(root))
    trace_writer = None
    if not args.disable_trace:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        run_id = f"{args.trace_prefix}_coding_{stamp}"
        trace_writer = TraceWriter(
            output_dir=str(Path(args.trace_logdir).expanduser().resolve()),
            run_id=run_id,
            strict_validate=True,
            metadata={"model_id": str(args.model_name)},
        )
    task_obj = Task(
        id="coding_react_reflection_demo",
        objective=str(args.task),
        env_spec=EnvSpec(type="host", config={"workspace_root": str(root)}),
        budget=TaskBudget(max_steps=int(args.max_steps)),
    )
    engine_kwargs = {
        "memory": MarkdownFileMemory(path=str(memory_path)),
        "critics": [ReActSelfReflectionCritic(max_retries=2)],
        "env": HostEnv(workspace_root=str(root)),
    }
    if trace_writer is not None:
        engine_kwargs["trace_writer"] = trace_writer

    result = agent.run(
        task=task_obj,
        return_state=True,
        hooks=hooks,
        target_file=str(args.file),
        test_command=str(args.test_command),
        expected_snippet=str(args.expected_snippet),
        max_steps=int(args.max_steps),
        workspace=str(root),
        engine_kwargs=engine_kwargs,
    )

    print("workspace:", root)
    print("final_result:", result.state.final_result)
    print("stop_reason:", result.state.stop_reason)
    print("memory_md:", memory_path)
    if trace_writer is not None:
        print("trace_run_dir:", trace_writer.run_dir)
    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()

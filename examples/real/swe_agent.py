"""Practical SWE agent: dynamic planning + branch search + execution loop."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, TaskResource, ToolRegistry
from qitos.kit.env import RepoEnv
from qitos.kit.parser import XmlDecisionParser
from qitos.kit.planning import DynamicTreeSearch, format_action, parse_numbered_plan
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import EditorToolSet, RunCommand
from qitos.models import OpenAICompatibleModel
from qitos.render import ClaudeStyleHook
from qitos.trace import TraceWriter
from examples.common import recent_rationales_from_scratchpad


PLAN_PROMPT = """You are planning a software bug-fix workflow.

Task: {task}
Target file: {file}
Verification command: {test_command}

Return a numbered plan with 3-6 short steps.
The final step must run verification command.
Output only numbered lines.
"""

EXEC_PROMPT = """You are a SWE execution agent.

Current plan step: {current_plan_step}

Rules:
- Exactly one tool call per step.
- Prefer smallest correct edit.
- Run verification when code is changed.
- Use final answer only when issue is resolved.

Available tools:
{tool_schema}

Output must be valid XML, exactly one <decision> root:

Act mode:
<decision mode="act">
  <action name="tool_name">
    <arg name="key">value</arg>
  </action>
</decision>

Final mode:
<decision mode="final">
  <final_answer>summary + proof</final_answer>
</decision>

Wait mode:
<decision mode="wait"></decision>

Constraints:
- Return XML only; no markdown, no code fences, no extra commentary.
- For args, use plain text values inside <arg>.
"""


DEFAULT_MODEL_BASE_URL = "https://api.siliconflow.cn/v1/"
DEFAULT_MODEL_API_KEY = ""
DEFAULT_MODEL_NAME = "Qwen/Qwen3-8B"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048

DEFAULT_MAX_STEPS = 18
DEFAULT_TASK = "Patch buggy_module.py and verify with tests."
DEFAULT_FILE = "buggy_module.py"
DEFAULT_TEST_COMMAND = 'python -c "import buggy_module; assert buggy_module.add(20, 22) == 42"'
DEFAULT_RENDER_THEME = "research"


@dataclass
class SWEPlanState(StateSchema):
    plan_steps: List[str] = field(default_factory=list)
    cursor: int = 0
    scratchpad: List[str] = field(default_factory=list)
    target_file: str = "buggy_module.py"
    test_command: str = ""
    replan_count: int = 0


class SWEDynamicPlanningAgent(AgentModule[SWEPlanState, Dict[str, Any], Action]):
    def __init__(self, llm: Any, workspace_root: str):
        registry = ToolRegistry()
        registry.include(EditorToolSet(workspace_root=workspace_root))
        registry.register(RunCommand(cwd=workspace_root))
        super().__init__(tool_registry=registry, llm=llm, model_parser=XmlDecisionParser())

    def init_state(self, task: str, **kwargs: Any) -> SWEPlanState:
        return SWEPlanState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 18)),
            target_file=str(kwargs.get("target_file", "buggy_module.py")),
            test_command=str(kwargs.get("test_command", "")),
        )

    def build_system_prompt(self, state: SWEPlanState) -> str | None:
        schema = self.tool_registry.get_tool_descriptions() if self.tool_registry else ""
        current = self._current_step_text(state)
        return render_prompt(
            EXEC_PROMPT,
            {"tool_schema": schema, "current_plan_step": current},
        )

    def prepare(self, state: SWEPlanState) -> str:
        current = self._current_step_text(state)
        lines = [
            f"Task: {state.task}",
            f"Target file: {state.target_file}",
            f"Verification: {state.test_command}",
            f"Plan cursor: {state.cursor}/{len(state.plan_steps)}",
            f"Current step: {current}",
            f"Replan count: {state.replan_count}",
        ]
        if state.plan_steps:
            lines.append("Full plan:")
            for i, item in enumerate(state.plan_steps):
                marker = "->" if i == state.cursor else "  "
                lines.append(f"{marker} [{i}] {item}")
        rationales = recent_rationales_from_scratchpad(state.scratchpad, max_items=6)
        if rationales:
            lines.append("Recent rationale:")
            lines.extend(f"- {x}" for x in rationales)
        if state.scratchpad:
            lines.append("Recent execution trace:")
            lines.extend(state.scratchpad[-10:])
        return "\n".join(lines)

    def decide(self, state: SWEPlanState, observation: Dict[str, Any]) -> Optional[Decision[Action]]:
        if not state.plan_steps or state.cursor >= len(state.plan_steps):
            planned = self._make_or_refresh_plan(state)
            if not planned:
                return Decision.final("Failed to generate valid plan.")
            return Decision.wait("plan_ready")

        step_text = self._current_step_text(state).lower()
        candidates: List[Decision[Action]] = []

        # Candidate 1: LLM-proposed action for this plan step.
        llm_decision = self._llm_step_action(state)
        if llm_decision is not None and llm_decision.mode == "act":
            llm_decision.meta = dict(llm_decision.meta or {})
            llm_decision.meta.setdefault("score", 0.92)
            llm_decision.rationale = llm_decision.rationale or "llm_step_action"
            candidates.append(llm_decision)

        # Candidate 2+: deterministic fallbacks for robustness.
        if any(k in step_text for k in ["inspect", "read", "check"]):
            candidates.append(
                Decision.act(
                    actions=[Action(name="view", args={"path": state.target_file})],
                    rationale="inspect_target_file",
                    meta={"score": 0.8},
                )
            )
        if any(k in step_text for k in ["fix", "patch", "edit", "replace"]):
            candidates.append(
                Decision.act(
                    actions=[
                        Action(
                            name="replace_lines",
                            args={
                                "path": state.target_file,
                                "start_line": 2,
                                "end_line": 2,
                                "replacement": "    return a + b",
                            },
                        )
                    ],
                    rationale="fallback_minimal_patch",
                    meta={"score": 0.76},
                )
            )
        if any(k in step_text for k in ["test", "verify", "validation"]):
            candidates.append(
                Decision.act(
                    actions=[Action(name="run_command", args={"command": state.test_command})],
                    rationale="run_verification",
                    meta={"score": 0.95},
                )
            )

        if not candidates:
            return None
        return Decision.branch(candidates=candidates, rationale=f"dynamic_plan_step_{state.cursor}")

    def reduce(
        self,
        state: SWEPlanState,
        observation: Dict[str, Any],
        decision: Decision[Action],
            ) -> SWEPlanState:
        action_results = observation.get("action_results", []) if isinstance(observation, dict) else []
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {format_action(decision.actions[0])}")

        should_advance = False
        if action_results:
            first = action_results[0]
            state.scratchpad.append(f"Observation: {first}")
            if isinstance(first, dict):
                if first.get("status") == "success":
                    should_advance = True
                if "returncode" in first:
                    if int(first.get("returncode", 1)) == 0:
                        should_advance = True
                        state.final_result = "Verification passed. Patch looks correct."
                    else:
                        # Failed verification triggers quick replan on next turn.
                        state.replan_count += 1
                        state.cursor = len(state.plan_steps)

        if should_advance and state.cursor < len(state.plan_steps):
            state.cursor += 1

        state.scratchpad = state.scratchpad[-50:]
        return state

    def _current_step_text(self, state: SWEPlanState) -> str:
        if state.cursor < 0 or state.cursor >= len(state.plan_steps):
            return "none"
        return state.plan_steps[state.cursor]

    def _make_or_refresh_plan(self, state: SWEPlanState) -> bool:
        prompt = render_prompt(
            PLAN_PROMPT,
            {"task": state.task, "file": state.target_file, "test_command": state.test_command},
        )
        raw = self.llm(
            [
                {"role": "system", "content": "Return a numbered plan only."},
                {"role": "user", "content": prompt},
            ]
        )
        plan = parse_numbered_plan(str(raw))
        if not plan:
            return False
        state.plan_steps = plan
        state.cursor = 0
        state.scratchpad.append(f"Plan: {plan}")
        return True

    def _llm_step_action(self, state: SWEPlanState) -> Optional[Decision[Action]]:
        step_text = self._current_step_text(state)
        if step_text == "none":
            return None
        prompt = (
            f"Task: {state.task}\n"
            f"Current plan step: {step_text}\n"
            f"Target file: {state.target_file}\n"
            f"Verification command: {state.test_command}\n"
            "Return exactly one XML <decision> object."
        )
        raw = self.llm(
            [
                {"role": "system", "content": self.build_system_prompt(state) or ""},
                {"role": "user", "content": prompt},
            ]
        )
        try:
            return self.model_parser.parse(str(raw))
        except Exception:
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
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--test-command", default=DEFAULT_TEST_COMMAND)
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

    target_file = str(args.file)
    target = root / target_file
    if not target.exists():
        target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    hooks = []
    if not args.disable_render:
        output_jsonl = str(root / "render_events.jsonl")
        hooks.append(ClaudeStyleHook(output_jsonl=output_jsonl, theme=str(args.theme)))

    task_obj = Task(
        id="swe_dynamic_planning_demo",
        objective=str(args.task),
        resources=[TaskResource(kind="file", path=target_file, required=True)],
        env_spec=EnvSpec(type="repo", config={"workspace_root": str(root)}),
        success_criteria=["verification command returns code 0"],
        budget=TaskBudget(max_steps=int(args.max_steps)),
    )

    agent = SWEDynamicPlanningAgent(llm=model, workspace_root=str(root))
    trace_writer = None
    if not args.disable_trace:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        run_id = f"{args.trace_prefix}_swe_{stamp}"
        trace_writer = TraceWriter(
            output_dir=str(Path(args.trace_logdir).expanduser().resolve()),
            run_id=run_id,
            strict_validate=True,
            metadata={"model_id": str(args.model_name)},
        )
    engine_kwargs = {
        "search": DynamicTreeSearch(top_k=2),
        "env": RepoEnv(workspace_root=str(root)),
    }
    if trace_writer is not None:
        engine_kwargs["trace_writer"] = trace_writer

    result = agent.run(
        task=task_obj,
        return_state=True,
        hooks=hooks,
        target_file=target_file,
        test_command=str(args.test_command),
        max_steps=int(args.max_steps),
        workspace=str(root),
        engine_kwargs=engine_kwargs,
    )

    print("workspace:", root)
    print("final_result:", result.state.final_result)
    print("stop_reason:", result.state.stop_reason)
    print("replan_count:", result.state.replan_count)
    print("patched_file:\n", target.read_text(encoding="utf-8"))
    if trace_writer is not None:
        print("trace_run_dir:", trace_writer.run_dir)
    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()

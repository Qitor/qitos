"""SWE-Agent minimal closed-loop template."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry
from qitos.skills.editor import EditorSkill
from qitos.skills.shell import RunCommand


@dataclass
class SWEState(StateSchema):
    file_path: str = "buggy_module.py"
    expected_snippet: str = "return a + b"
    test_command: str = ""
    phase: str = "view"  # view -> edit -> test -> submit
    last_view: Optional[Dict[str, Any]] = None
    last_edit: Optional[Dict[str, Any]] = None
    last_test: Optional[Dict[str, Any]] = None
    patch_log: List[str] = field(default_factory=list)


class SWEAgentMini(AgentModule[SWEState, Dict[str, Any], Action]):
    def __init__(self, workspace_root: str):
        registry = ToolRegistry()
        registry.include(EditorSkill(workspace_root=workspace_root))
        registry.register(RunCommand(cwd=workspace_root))
        super().__init__(toolkit=registry)

    def init_state(self, task: str, **kwargs: Any) -> SWEState:
        return SWEState(
            task=task,
            file_path=kwargs.get("file_path", "buggy_module.py"),
            expected_snippet=kwargs.get("expected_snippet", "return a + b"),
            test_command=kwargs.get(
                "test_command",
                "python -c \"import buggy_module; assert buggy_module.add(20, 22) == 42\"",
            ),
            max_steps=int(kwargs.get("max_steps", 10)),
        )

    def observe(self, state: SWEState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "phase": state.phase,
            "file_path": state.file_path,
            "last_test": state.last_test,
            "patch_log": list(state.patch_log),
        }

    def decide(self, state: SWEState, observation: Dict[str, Any]) -> Decision[Action]:
        if state.phase == "view":
            return Decision.act(actions=[Action(name="view", args={"path": state.file_path})])

        if state.phase == "edit":
            # deterministic patch for mini scenario
            return Decision.act(
                actions=[
                    Action(
                        name="replace_lines",
                        args={
                            "path": state.file_path,
                            "start_line": 2,
                            "end_line": 2,
                            "replacement": f"    {state.expected_snippet}",
                        },
                    )
                ]
            )

        if state.phase == "test":
            return Decision.act(actions=[Action(name="run_command", args={"command": state.test_command})])

        if state.phase == "submit":
            test = state.last_test or {}
            rc = int(test.get("returncode", 1))
            if rc == 0:
                return Decision.final(f"patch_valid:{state.file_path}")
            return Decision.final("patch_invalid")

        return Decision.final("unsupported_phase")

    def reduce(
        self,
        state: SWEState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> SWEState:
        if not action_results:
            return state

        first = action_results[0]
        if state.phase == "view":
            state.last_view = first if isinstance(first, dict) else {"raw": first}
            state.phase = "edit"
            return state

        if state.phase == "edit":
            state.last_edit = first if isinstance(first, dict) else {"raw": first}
            state.patch_log.append(str(first))
            state.phase = "test"
            return state

        if state.phase == "test":
            state.last_test = first if isinstance(first, dict) else {"raw": first}
            state.phase = "submit"
            return state

        return state

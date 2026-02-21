from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from qitos import Action, AgentModule, Decision, Engine, RuntimeBudget, StateSchema, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.tool import WriteFile


def test_host_env_replace_lines_and_command(tmp_path: Path):
    target = tmp_path / "m.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    env = HostEnv(workspace_root=str(tmp_path))

    out = env.execute_action(
        Action(
            name="replace_lines",
            args={"path": "m.py", "start_line": 2, "end_line": 2, "replacement": "    return a + b"},
        )
    )
    assert isinstance(out, dict) and out.get("status") == "success"
    assert "return a + b" in target.read_text(encoding="utf-8")

    run = env.execute_action(Action(name="run_command", args={"command": "python -c \"print(42)\""}))
    assert isinstance(run, dict)
    assert int(run.get("returncode", 1)) == 0


@dataclass
class _State(StateSchema):
    done: bool = False


class _EnvOnlyAgent(AgentModule[_State, Dict[str, Any], Action]):
    def __init__(self):
        super().__init__(tool_registry=None)

    def init_state(self, task: str, **kwargs: Any) -> _State:
        return _State(task=task, max_steps=2)

    def observe(self, state: _State, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {"task": state.task, "env": env_view.get("env", {})}

    def decide(self, state: _State, observation: Dict[str, Any]):
        if state.current_step == 0:
            return Decision.act(
                actions=[
                    Action(
                        name="write_file",
                        args={"filename": "x.txt", "content": "hello"},
                    )
                ]
            )
        return Decision.final("done")

    def reduce(self, state: _State, observation: Dict[str, Any], decision: Decision[Action], action_results: List[Any]) -> _State:
        if decision.mode == "final":
            state.done = True
        return state


def test_engine_executes_ops_aware_tool_with_env(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(WriteFile(root_dir=str(tmp_path)))

    class _EnvOpsAgent(_EnvOnlyAgent):
        def __init__(self):
            super().__init__()
            self.tool_registry = registry

    env = HostEnv(workspace_root=str(tmp_path))
    engine = Engine(agent=_EnvOpsAgent(), env=env, budget=RuntimeBudget(max_steps=3))
    result = engine.run("write file")
    assert result.state.final_result == "done"
    assert (tmp_path / "x.txt").exists()
    assert (tmp_path / "x.txt").read_text(encoding="utf-8") == "hello"


def test_engine_fails_when_required_ops_missing_env(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(WriteFile(root_dir=str(tmp_path)))

    class _NoEnvAgent(_EnvOnlyAgent):
        def __init__(self):
            super().__init__()
            self.tool_registry = registry

    result = Engine(agent=_NoEnvAgent(), budget=RuntimeBudget(max_steps=2)).run("write file")
    assert result.records
    first_results = result.records[0].action_results
    assert first_results and isinstance(first_results[0], dict)
    assert "error" in first_results[0]
    assert "requires ops" in str(first_results[0]["error"])

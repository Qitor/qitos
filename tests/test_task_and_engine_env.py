from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from qitos import (
    Action,
    AgentModule,
    Decision,
    Engine,
    Env,
    EnvObservation,
    EnvSpec,
    EnvStepResult,
    RuntimeBudget,
    StateSchema,
    StopReason,
    Task,
    TaskBudget,
    TaskResource,
    ToolRegistry,
    tool,
)


class _TerminalAfterOneStepEnv(Env):
    def __init__(self):
        self.reset_count = 0
        self.step_count = 0

    def reset(self, task=None, workspace=None, **kwargs):
        self.reset_count += 1
        return EnvObservation(data={"task": getattr(task, "id", str(task)), "workspace": workspace})

    def observe(self, state=None):
        return EnvObservation(data={"step_count": self.step_count})

    def step(self, action, state=None):
        self.step_count += 1
        return EnvStepResult(observation=self.observe(state=state), done=self.step_count >= 1)


@dataclass
class _DemoState(StateSchema):
    logs: List[str] = None

    def __post_init__(self):
        if self.logs is None:
            self.logs = []


class _DemoAgent(AgentModule[_DemoState, Dict[str, Any], Action]):
    def __init__(self):
        registry = ToolRegistry()

        @tool(name="noop")
        def noop() -> Dict[str, Any]:
            return {"ok": True}

        registry.register(noop)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> _DemoState:
        return _DemoState(task=task, max_steps=int(kwargs.get("max_steps", 4)))

    def observe(self, state: _DemoState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        state.logs.append(f"env_enabled={env_view.get('env', {}).get('enabled')}")
        return {"task": state.task, "env": env_view.get("env", {})}

    def decide(self, state: _DemoState, observation: Dict[str, Any]):
        return Decision.act(actions=[Action(name="noop")])

    def reduce(self, state: _DemoState, observation: Dict[str, Any], decision: Decision[Action], action_results: List[Any]) -> _DemoState:
        state.logs.append(f"results={len(action_results)}")
        return state


def test_task_dataclass_roundtrip():
    task = Task(
        id="swe_1",
        objective="Fix bug in module",
        resources=[TaskResource(kind="file", path="buggy_module.py")],
        env_spec=EnvSpec(type="repo", config={"workspace_root": "/tmp/x"}),
        budget=TaskBudget(max_steps=12),
    )
    payload = task.to_dict()
    loaded = Task.from_dict(payload)
    assert loaded.id == "swe_1"
    assert loaded.objective == "Fix bug in module"
    assert loaded.resources[0].path == "buggy_module.py"
    assert loaded.env_spec is not None and loaded.env_spec.type == "repo"


def test_engine_accepts_task_and_env_terminal_stop():
    env = _TerminalAfterOneStepEnv()
    agent = _DemoAgent()
    task = Task(id="t1", objective="do one noop", budget=TaskBudget(max_steps=3))

    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=3), env=env).run(task, workspace="/tmp")
    assert result.state.task == "do one noop"
    assert result.state.stop_reason == StopReason.ENV_TERMINAL.value
    assert env.reset_count == 1
    assert env.step_count >= 1


def test_task_budget_overrides_engine_budget():
    agent = _DemoAgent()
    task = Task(id="t_budget", objective="budgeted noop", budget=TaskBudget(max_steps=1))

    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=5)).run(task)
    assert result.state.stop_reason == StopReason.MAX_STEPS.value
    assert result.step_count == 1


def test_agent_run_accepts_task_object():
    agent = _DemoAgent()
    task = Task(id="t_run", objective="run noop", budget=TaskBudget(max_steps=1))
    output = agent.run(task)
    assert output is None

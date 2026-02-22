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
from qitos.kit.parser import ReActTextParser


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
    assert loaded.resolve_resources(workspace="/tmp/x")[0].target == "buggy_module.py"


def test_engine_accepts_task_and_env_terminal_stop():
    env = _TerminalAfterOneStepEnv()
    agent = _DemoAgent()
    task = Task(id="t1", objective="do one noop", budget=TaskBudget(max_steps=3))

    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=3), env=env).run(task, workspace="/tmp")
    assert result.state.task == "do one noop"
    assert result.state.stop_reason == StopReason.ENV_TERMINAL.value
    assert result.task_result is not None
    assert result.task_result.stop_reason == StopReason.ENV_TERMINAL.value
    assert env.reset_count == 1
    assert env.step_count >= 1


def test_task_budget_overrides_engine_budget():
    agent = _DemoAgent()
    task = Task(id="t_budget", objective="budgeted noop", budget=TaskBudget(max_steps=1))

    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=5)).run(task)
    assert result.state.stop_reason == StopReason.BUDGET_STEPS.value
    assert result.step_count == 1


def test_agent_run_accepts_task_object():
    agent = _DemoAgent()
    task = Task(id="t_run", objective="run noop", budget=TaskBudget(max_steps=1))
    output = agent.run(task)
    assert output is None


def test_task_preflight_reports_missing_resource(tmp_path):
    agent = _DemoAgent()
    task = Task(
        id="t_missing",
        objective="noop",
        resources=[TaskResource(kind="file", path="missing.txt", required=True)],
    )
    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=3)).run(task, workspace=str(tmp_path))
    assert result.state.stop_reason == StopReason.TASK_VALIDATION_FAILED.value
    assert result.step_count == 0
    end_events = [e for e in result.events if e.phase.value == "END"]
    assert end_events
    issues = end_events[-1].payload.get("issues", [])
    assert issues and issues[0].get("code") == "TASK_RESOURCE_MISSING"


def test_task_mount_to_validation_issue():
    task = Task(
        id="t_mount",
        objective="noop",
        resources=[TaskResource(kind="file", path="a.txt", mount_to="")],
    )
    issues = task.validate_structured()
    assert any(i.code == "TASK_RESOURCE_MOUNT_INVALID" for i in issues)


def test_engine_respects_max_tokens_budget():
    @dataclass
    class _LLMState(StateSchema):
        pass

    class _LLMAgent(AgentModule[_LLMState, Dict[str, Any], Action]):
        def __init__(self):
            super().__init__(tool_registry=ToolRegistry())
            self.model_parser = ReActTextParser()
            self.llm = lambda messages: "Action: noop()"

        def init_state(self, task: str, **kwargs: Any) -> _LLMState:
            return _LLMState(task=task, max_steps=10)

        def observe(self, state: _LLMState, env_view: Dict[str, Any]) -> Dict[str, Any]:
            return {"task": state.task}

        def decide(self, state: _LLMState, observation: Dict[str, Any]):
            if state.current_step < 3:
                return None
            return Decision.final("done")

        def reduce(self, state: _LLMState, observation: Dict[str, Any], decision: Decision[Action], action_results: List[Any]) -> _LLMState:
            return state

    task = Task(id="t_token", objective="token limited", budget=TaskBudget(max_steps=10, max_tokens=5))
    result = Engine(agent=_LLMAgent(), budget=RuntimeBudget(max_steps=10)).run(task)
    assert result.state.stop_reason == StopReason.BUDGET_TOKENS.value

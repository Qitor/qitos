from dataclasses import dataclass
from typing import Any

from qitos import Action, AgentModule, Decision, Engine, RuntimeBudget, StateSchema, ToolRegistry
from qitos.engine.hooks import EngineHook
from qitos.kit.critic import PassThroughCritic
from qitos.kit.parser import ReActTextParser
from qitos.render import RenderStreamHook


@dataclass
class _S(StateSchema):
    pass


class _LLMAgent(AgentModule[_S, dict[str, Any], Action]):
    def __init__(self):
        super().__init__(tool_registry=ToolRegistry(), llm=self._llm, model_parser=ReActTextParser())

    def _llm(self, messages):
        return "Final Answer: ok"

    def init_state(self, task: str, **kwargs: Any) -> _S:
        return _S(task=task, max_steps=2)

    def observe(self, state: _S, env_view: dict[str, Any]) -> dict[str, Any]:
        return {"task": state.task, "step": state.current_step, "memory": env_view.get("memory", {})}

    def prepare(self, state: _S, observation: dict[str, Any]) -> str:
        return f"task={observation['task']} step={observation['step']}"

    def decide(self, state: _S, observation: dict[str, Any]):
        return None

    def reduce(
        self,
        state: _S,
        observation: dict[str, Any],
        decision: Decision[Action],
        action_results: list[Any],
    ) -> _S:
        return state


class _CaptureHook(EngineHook):
    def __init__(self):
        self.events: list[tuple[str, str]] = []
        self.run_start = 0
        self.run_end = 0

    def on_run_start(self, task: str, state: StateSchema, engine: Engine) -> None:
        self.run_start += 1

    def on_event(self, event, state, record, engine) -> None:
        stage = str((event.payload or {}).get("stage", ""))
        self.events.append((event.phase.value, stage))

    def on_run_end(self, result, engine) -> None:
        self.run_end += 1


def test_engine_hook_register_unregister():
    hook = _CaptureHook()
    engine = Engine(agent=_LLMAgent(), budget=RuntimeBudget(max_steps=2), critics=[PassThroughCritic()])
    engine.register_hook(hook)
    result = engine.run("x")
    assert result.state.final_result == "ok"
    assert hook.run_start == 1
    assert hook.run_end == 1

    phases = {p for p, _ in hook.events}
    assert "OBSERVE" in phases
    assert "DECIDE" in phases
    assert "CRITIC" in phases
    assert "CHECK_STOP" in phases

    stages = {s for _, s in hook.events}
    assert "observation_ready" in stages
    assert "model_input" in stages
    assert "model_output" in stages
    assert "decision_ready" in stages

    engine.unregister_hook(hook)
    hook.events.clear()
    engine.run("y")
    assert hook.events == []


def test_phase_hooks_are_triggered():
    marks: list[str] = []

    class _PhaseHook(EngineHook):
        def on_before_observe(self, ctx, engine):
            marks.append("before_observe")

        def on_after_observe(self, ctx, engine):
            marks.append("after_observe")

        def on_before_decide(self, ctx, engine):
            marks.append("before_decide")

        def on_after_decide(self, ctx, engine):
            marks.append("after_decide")

        def on_before_act(self, ctx, engine):
            marks.append("before_act")

        def on_after_act(self, ctx, engine):
            marks.append("after_act")

        def on_before_reduce(self, ctx, engine):
            marks.append("before_reduce")

        def on_after_reduce(self, ctx, engine):
            marks.append("after_reduce")

        def on_before_check_stop(self, ctx, engine):
            marks.append("before_check_stop")

        def on_after_check_stop(self, ctx, engine):
            marks.append("after_check_stop")

    engine = Engine(agent=_LLMAgent(), budget=RuntimeBudget(max_steps=2), hooks=[_PhaseHook()])
    result = engine.run("x")
    assert result.state.final_result == "ok"
    assert "before_observe" in marks
    assert "after_decide" in marks
    assert "before_check_stop" in marks
    assert "after_check_stop" in marks


def test_render_stream_hook_outputs_structured_events(tmp_path):
    out = tmp_path / "render_events.jsonl"
    hook = RenderStreamHook(output_jsonl=str(out))
    result = Engine(agent=_LLMAgent(), budget=RuntimeBudget(max_steps=2), critics=[PassThroughCritic()], hooks=[hook]).run("x")
    assert result.state.final_result == "ok"
    assert out.exists()
    assert len(hook.events) > 0
    nodes = {evt.node for evt in hook.events}
    assert "run_start" in nodes
    assert "observation" in nodes
    assert "decision" in nodes
    assert "done" in nodes

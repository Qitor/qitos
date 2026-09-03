from dataclasses import dataclass
from typing import Any

from qitos import Action, AgentModule, Decision, Engine, StateSchema, ToolRegistry, tool
from qitos.core.env import EnvObservation
from qitos.core.tool_result import ToolResult
from qitos.engine._action_runtime import _ActionRuntime
from qitos.engine._env_runtime import _EnvRuntime
from qitos.engine.hooks import EngineHook, HookContext
from qitos.engine.states import RuntimeBudget
from qitos.kit.env import HostEnv
from qitos.kit.toolset.env_coding import EnvCodingToolSet


def _summary_payload() -> dict[str, str]:
    return {
        "model_summary": "## STATIC_ROUTE · partial\n- answer: entry -> target",
        "artifact_path": ".agent/evidence/static/raw.json",
    }


def test_action_history_projects_model_summary_without_losing_raw_result() -> None:
    runtime = _ActionRuntime.__new__(_ActionRuntime)
    result = ToolResult(
        output=_summary_payload(), metadata={"tool_name": "STATIC_ROUTE"}
    )

    assert runtime._model_visible_tool_output("STATIC_ROUTE", result.output) == result.output["model_summary"]
    visible = runtime._model_visible_tool_result_dict(result, "STATIC_ROUTE")
    assert visible["model_output"] == result.output["model_summary"]
    assert "output" not in visible
    assert "artifact_path" not in str(visible)
    assert result.output["artifact_path"].endswith("raw.json")


def test_env_observation_projects_model_summary() -> None:
    runtime = _EnvRuntime.__new__(_EnvRuntime)
    result = ToolResult(
        output=_summary_payload(), metadata={"tool_name": "gdb_debug"}
    )
    visible = runtime._model_visible_tool_result_dict(result)
    assert visible["model_output"] == result.output["model_summary"]
    assert "artifact_path" not in str(visible)


def test_projection_is_tool_agnostic_after_special_case_removal() -> None:
    """The submit_poc special-case is gone; every tool owns its summary."""
    runtime = _ActionRuntime.__new__(_ActionRuntime)
    payload = {
        "model_summary": "expose exactly this",
        "status": "success",
        "raw_output": "bulky raw payload",
        "fixed_side_verdict": "private-to-the-tool",
    }
    visible = runtime._model_visible_tool_output("submit_poc", payload)
    assert visible == "expose exactly this"

    no_summary = {"status": "success", "raw_output": "passthrough"}
    assert runtime._model_visible_tool_output("submit_poc", no_summary) == (
        '{"raw_output":"passthrough","status":"success"}'
    )


@dataclass
class _ProjectionState(StateSchema):
    pass


class _ProjectionAgent(AgentModule[_ProjectionState, dict[str, Any], Action]):
    def __init__(self) -> None:
        registry = ToolRegistry()

        @tool(name="gdb_debug")
        def gdb_debug() -> dict[str, str]:
            return {
                "raw_artifact_path": ".agent/evidence/gdb/raw.txt",
                "model_summary": "## gdb_debug · route_trace\n- Target hit: `True`",
            }

        registry.register(gdb_debug)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> _ProjectionState:
        _ = kwargs
        return _ProjectionState(task=task, max_steps=2)

    def decide(
        self, state: _ProjectionState, observation: dict[str, Any]
    ) -> Decision[Action]:
        _ = observation
        if state.current_step == 0:
            return Decision.act(actions=[Action(name="gdb_debug", args={})])
        return Decision.final("done")

    def reduce(
        self,
        state: _ProjectionState,
        observation: dict[str, Any],
        decision: Decision[Action],
    ) -> _ProjectionState:
        _ = observation, decision
        return state


class _AfterActCapture(EngineHook):
    def __init__(self) -> None:
        self.results: list[Any] = []

    def on_after_act(self, ctx: HookContext, engine: Any) -> None:
        _ = engine
        self.results = list(ctx.action_results or [])


def test_after_act_hook_uses_same_gdb_projection_as_provider_history() -> None:
    hook = _AfterActCapture()
    Engine(
        agent=_ProjectionAgent(),
        budget=RuntimeBudget(max_steps=2),
        hooks=[hook],
    ).run("task")

    assert len(hook.results) == 1
    visible = hook.results[0]
    assert visible["model_output"] == "## gdb_debug · route_trace\n- Target hit: `True`"
    assert "raw_artifact_path" not in str(visible)


def test_environment_projection_redacts_location_and_omits_repeated_inventory(
    tmp_path: Any,
) -> None:
    (tmp_path / "visible.txt").write_text("content", encoding="utf-8")
    env = HostEnv(workspace_root=str(tmp_path))
    engine = Engine(
        agent=_ProjectionAgent(),
        env=env,
        budget=RuntimeBudget(max_steps=2),
    )
    engine._last_env_observation = env.reset()
    runtime = _EnvRuntime(engine)

    first = runtime.env_payload()
    second = runtime.env_payload()

    assert first["observation"]["value"]["data"]["files"] == ["visible.txt"]
    assert str(tmp_path) not in str(first)
    assert second["observation"] == {
        "unchanged": True,
        "projection_digest": first["observation"]["projection_digest"],
        "loss_receipt": {
            "unchanged_observation_omitted": True,
            "omitted_characters": first["observation"]["loss_receipt"][
                "input_characters"
            ],
        },
    }


def test_builtin_coding_tool_keeps_canonical_output_but_bounds_model_projection(
    tmp_path: Any,
) -> None:
    body = "x" * 1_000_000
    (tmp_path / "large.txt").write_text(body, encoding="utf-8")
    env = HostEnv(workspace_root=str(tmp_path))
    tools = {item.name: item for item in EnvCodingToolSet().tools()}
    result = tools["read_file"].run(
        path="large.txt",
        runtime_context={"env": env, "ops": {"file": env.fs}},
    )

    assert isinstance(result, ToolResult)
    assert result.output["content"] == body
    projection = result.to_model_dict(max_chars=20_000)
    assert len(projection["model_output"]) < 17_000
    receipt = result.model_output["selection_receipt"]
    assert receipt["omitted_characters"] > 0
    assert result.artifact_refs[0].byte_length == len(body)
    assert projection["projection_loss"]["truncated"] is False


def test_large_environment_observation_is_bounded_without_losing_canonical_fact(
    tmp_path: Any,
) -> None:
    env = HostEnv(workspace_root=str(tmp_path))
    engine = Engine(
        agent=_ProjectionAgent(),
        env=env,
        budget=RuntimeBudget(max_steps=2),
    )
    body = "z" * 10_000_000
    engine._last_env_observation = EnvObservation(data={"body": body})

    projected = _EnvRuntime(engine).env_payload()["observation"]

    assert engine._last_env_observation.data["body"] == body
    assert len(projected["value"]) <= 50_000
    assert projected["loss_receipt"]["truncated"] is True
    assert projected["loss_receipt"]["omitted_characters"] > 9_000_000

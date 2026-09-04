"""Public composition resolves and invokes caller-owned context extensions."""
from dataclasses import replace
import json

import pytest

from qitos.config import TrajectoryConfig, build_agent_composition
from qitos.config.errors import CompositionError
from qitos.core.context import PriorityContextSelectionPolicy, StaticContextContributor
from test_s4_lane_a_public_authoring import _config, _FinalModel


def test_configured_context_memory_and_selector_reach_the_provider(tmp_path):
    selected = []
    calls = []

    class Selector(PriorityContextSelectionPolicy):
        def select(self, contributions, **kwargs):
            values = tuple(contributions)
            selected.extend(item.contribution_id for item in values)
            return super().select(values, **kwargs)

    class Model(_FinalModel):
        def call_raw(self, messages, **options):
            calls.append(json.dumps(messages))
            return super().call_raw(messages, **options)

    config = replace(_config(tmp_path), context={"contributors": ["project"], "selector": "selector"},
                     memory={"sources": ["memory"]})
    with build_agent_composition(config, model_override=Model(), extensions={
        "project": lambda: StaticContextContributor("project", "project", "PROJECT_SENTINEL"),
        "memory": lambda: StaticContextContributor("memory", "memory", "MEMORY_SENTINEL"),
        "selector": Selector,
    }) as composition:
        result = composition.session().run()
    assert result.state.final_result == "done"
    assert {"project", "memory"} <= set(selected)
    assert len(calls) == 1
    assert "PROJECT_SENTINEL" in calls[0] and "MEMORY_SENTINEL" in calls[0]


@pytest.mark.parametrize("values", [
    {"context": {"unused": 1}}, {"memory": {"policy": "automatic"}},
    {"compaction": {"threshold": 1}}, {"lifecycle": {"background": True}},
    {"failure_policy": {"provider": "resend"}}, {"tool_options": {"max_concurrency": 0}},
    {"tool_options": {"safe_tools_by_name": ["read_file"]}},
])
def test_unimplemented_configuration_rejects_before_model_construction(tmp_path, values, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("model was constructed before configuration admission")
    monkeypatch.setattr("qitos.config.builder.build_model", forbidden)
    with pytest.raises(CompositionError):
        build_agent_composition(replace(_config(tmp_path), **values))


def test_explicit_codec_loss_retains_reasoning_and_accounts_requests(tmp_path):
    from qitos.core.function_tool_decorator import function_tool

    calls = []
    class ReasoningModel(_FinalModel):
        qitos_protocol = "json_decision_multi_v1"

        def call_raw(self, messages, **options):
            calls.append(messages)
            if len(calls) == 1:
                return {"choices": [{"message": {"content": None, "reasoning_content": "PRIVATE_REASONING_FIXTURE",
                    "tool_calls": [{"id": "reasoning-call", "type": "function", "function": {"name": "sample", "arguments": "{}"}}]}}]}
            return {"choices": [{"message": {"content": "done"}}]}

    @function_tool(read_only=True)
    def sample():
        return {"mean": 5}

    base = _config(tmp_path)
    config = replace(base, protocol="json_decision_multi_v1", context={"allow_codec_loss": True}, runtime=replace(base.runtime,
        trajectory=TrajectoryConfig(enabled=True, output=str(tmp_path / "trajectory.journal"))))
    with build_agent_composition(config, model_override=ReasoningModel()) as composition:
        composition.tool_registry.register(sample)
        session = composition.session("sample with an explicit lossy projection")
        result = session.run()
        assert result.state.final_result == "done"
        assert len(calls) == 2
        assert result.tool_calls_by_name["sample"] == 1
        assert "PRIVATE_REASONING_FIXTURE" not in json.dumps(calls[1])
        from qitos.qita.reader import candidate_file_reader
        from qitos.tracing.trajectory import PrivacyView
        records = candidate_file_reader(composition.trajectory_path).read_run(result.run_id, view=PrivacyView.RAW_PRIVATE).records
        text = json.dumps([item.to_dict() for item in records])
        snapshot = composition.runtime.checkpoint_store.get_session_snapshot(session.current_head.snapshot_id.value)
        assert "PRIVATE_REASONING_FIXTURE" in json.dumps(snapshot.payload)
        assert "assistant.reasoning" in text


def test_native_work_adapter_uses_real_durable_child_head(tmp_path):
    from qitos.engine.work_runtime import DurableWorkRuntime, WorkRuntimePolicy
    from qitos.kit.tool.agent.durable_adapter import SpawnTool
    from qitos.core.work_graph import WorkGraph
    from engine.test_work_runtime import IndependentSchedulerFake

    class Model(_FinalModel):
        qitos_protocol = "json_decision_multi_v1"
        calls = 0

        def call_raw(self, messages, **options):
            self.calls += 1
            if self.calls == 1:
                return {"choices": [{"message": {"content": None, "tool_calls": [
                    {"id": "spawn-native", "type": "function", "function": {"name": "spawn", "arguments": json.dumps({"agent": "public-authoring-fixture", "task": "child"})}}]}}]}
            return {"choices": [{"message": {"content": "done"}}]}

    base = _config(tmp_path)
    config = replace(base, name="public-authoring-fixture", protocol="json_decision_multi_v1",
                     tool_options={"native_tool_calls_required": True})
    scheduler = IndependentSchedulerFake()
    with build_agent_composition(config, model_override=Model()) as current:
        current.runtime.work_runtime = DurableWorkRuntime(scheduler, policy=WorkRuntimePolicy(budget_ceiling={"model_requests": 2}))
        current.tool_registry.register(SpawnTool())
        session = current.session("native child")
        result = session.run()
        assert result.records[0].action_results[0].status == "success", result.records[0].action_results
        assert result.state.final_result == "done"
        graph = WorkGraph.from_canonical_dict(session.inspect().work_graph)
        assert len(graph.work_items) == 2 and len(scheduler.requests) == 1
        identity = scheduler.requests[0].descriptor.child_session_ids[0]
        assert current.runtime.checkpoint_store.get_session_head(identity).lifecycle == "paused"

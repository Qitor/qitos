from __future__ import annotations

from pathlib import Path
from typing import Any

from qitos.config.builder import build_agent_composition
from qitos.config.credentials import CredentialRef
from qitos.config.loader import (
    AgentConfig,
    EnvironmentConfig,
    ModelConfig,
    RuntimeConfig,
    SessionConfig,
    TrajectoryConfig,
)
from qitos.qita.reader import candidate_file_reader, load_session_payload
from qitos.core.session import PauseSafety, SafeBoundaryKind
from qitos.engine.work_runtime import DurableWorkRuntime, WorkRuntimePolicy
from qitos.tracing.trajectory import RecordKind
from qitos.tracing.work_graph_reader import GraphSelector, WorkGraphReader


class _ToolThenFinalModel:
    model = "offline-tool-model"
    context_window = 8192
    max_tokens = 256
    qitos_harness_metadata = {
        "tool_policy": {"native_tool_call_preferred": True},
        "parser": "ReActTextParser",
        "protocol": "react_text_v1",
    }

    def __init__(self) -> None:
        self.calls = 0
        self.options: list[dict[str, Any]] = []

    def call_raw(self, messages: object, **options: Any) -> dict[str, Any]:
        _ = messages
        self.options.append(dict(options))
        self.calls += 1
        if self.calls == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_read_input",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path":"input.txt"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "Final Answer: observed"}}]}


class _PauseAfterFirstStep:
    policy_id = "tests.configured.pause_after_first_step"
    supports_pause = True

    def should_pause(self, context: Any) -> bool:
        return context.step_id == 0

    def pause_safety(self, context: Any) -> PauseSafety:
        _ = context
        return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)


class _HoldHandle:
    def __init__(self, worker_ref: str) -> None:
        self.worker_ref = worker_ref

    def add_terminal_callback(self, callback: Any) -> None:
        self.callback = callback

    def request_cancel(self) -> bool:
        return False


class _HoldScheduler:
    scheduler_id = "tests.configured.hold"

    def dispatch(self, request: Any) -> _HoldHandle:
        return _HoldHandle(f"hold:{request.operation_id}:{request.attempt}")

    def reattach(self, request: Any, worker_ref: str) -> None:
        _ = request, worker_ref
        return None

    def close(self) -> None:
        return None


def _config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(
        name="trajectory-agent",
        max_steps=3,
        model=ModelConfig(
            provider="openai-compatible",
            model="offline-tool-model",
            credential=CredentialRef("offline-fixture"),
        ),
        tool_preset="env_coding",
        tool_use_policy="required_before_final",
        protocol="react_text_v1",
        parser="auto",
        runtime=RuntimeConfig(
            environment=EnvironmentConfig(
                type="unsafe_host",
                image="",
                workspace=str(tmp_path),
                container_workspace="",
                network="host",
                read_only_root=False,
                cap_drop=False,
                no_new_privileges=False,
                pids_limit=None,
                memory_mb=None,
                cpus=None,
                cleanup_required=False,
            ),
            session=SessionConfig(enabled=True, store="memory"),
            trajectory=TrajectoryConfig(
                enabled=True,
                output=str(tmp_path / "trajectory.json"),
                privacy="private",
                failure_policy="required",
            ),
        ),
    )


def test_configured_session_writes_one_qita_and_graph_readable_trajectory(
    tmp_path: Path,
) -> None:
    (tmp_path / "input.txt").write_text("truth", encoding="utf-8")
    model = _ToolThenFinalModel()
    config = _config(tmp_path)
    composition = build_agent_composition(config, model_override=model)
    try:
        session = composition.engine.session("read the declared file")
        result = session.run()
        session_id = session.session_id.value
    finally:
        composition.close()

    assert result.state.final_result == "observed"
    assert result.tool_calls_by_name == {"read_file": 1}
    assert model.options[0]["tool_choice"] == "required"
    assert "tool_choice" not in model.options[-1]

    reader = candidate_file_reader(tmp_path / "trajectory.json")
    trajectory = reader.read_session(session_id)
    kinds = {record.kind for record in trajectory.records}
    assert {RecordKind.MODEL_REQUEST, RecordKind.MODEL_RESPONSE, RecordKind.TOOL_SLOT} <= kinds
    assert trajectory.records
    for record in trajectory.records:
        launch = record.record_provenance["launch"]
        assert launch["config_digest"] == config.digest()
        assert launch["protocol"] == "react_text_v1"
        assert launch["tool_use_policy"] == "required_before_final"
        assert launch["sandbox"]["safety"] == "unisolated_host_execution"

    qita_payload = load_session_payload(reader, session_id)
    assert qita_payload["trajectory_meta"]["session_id"] == session_id
    graph = WorkGraphReader(reader).read(GraphSelector("session", session_id))
    assert graph.session_summary["session_ids"] == [session_id]
    assert graph.timeline


def test_candidate_file_reader_preserves_exact_record_bytes(tmp_path: Path) -> None:
    from qitos.tracing.store import JsonTrajectoryStore
    from qitos.tracing.trajectory import (
        PrivacyView,
        TrajectoryQuery,
        TrajectoryRecord,
    )

    source = tmp_path / "exact.json"
    store = JsonTrajectoryStore(source)
    store.append(
        TrajectoryRecord.create(
            RecordKind.RUN,
            run_id="run-exact",
            occurred_at="2026-09-04T00:00:00+00:00",
            recorded_at="2026-09-04T00:00:01+00:00",
            payload={"status": "complete"},
        )
    )
    expected = store.query(TrajectoryQuery(run_id="run-exact"))[0]
    store.close()

    observed = candidate_file_reader(source).read_run(
        "run-exact", view=PrivacyView.RAW_PRIVATE
    ).records[0]
    assert observed.to_dict() == expected.to_dict()


def test_configured_multi_agent_facts_use_the_real_trajectory_sink(
    tmp_path: Path,
) -> None:
    (tmp_path / "input.txt").write_text("truth", encoding="utf-8")
    config = _config(tmp_path)
    composition = build_agent_composition(
        config, model_override=_ToolThenFinalModel()
    )
    composition.runtime.lifecycle_policy = _PauseAfterFirstStep()
    composition.runtime.work_runtime = DurableWorkRuntime(
        _HoldScheduler(),
        policy=WorkRuntimePolicy(
            maximum_children_per_operation=2,
            maximum_graph_depth=2,
            maximum_concurrent_children=2,
            queue_capacity=2,
            capability_ceiling=frozenset({"read"}),
            budget_ceiling={"model_requests": 1},
        ),
    )
    try:
        parent = composition.engine.session("read before dispatch")
        parent.run()
        fan_out = parent.fan_out(
            [
                {
                    "agent": config.name,
                    "task": "child zero",
                    "capabilities": ["read"],
                    "budget": {"model_requests": 1},
                },
                {
                    "agent": config.name,
                    "task": "child one",
                    "capabilities": ["read"],
                    "budget": {"model_requests": 1},
                },
            ],
            operation_id="configured-fan-out",
        )
        parent.join(
            [fan_out.operation_id],
            policy="all",
            operation_id="configured-join",
        )
        session_id = parent.session_id.value
    finally:
        composition.close()
        composition.runtime.work_runtime.close()

    reader = candidate_file_reader(tmp_path / "trajectory.json")
    graph = WorkGraphReader(reader).read(GraphSelector("session", session_id))
    event_types = {entry.event_type for entry in graph.timeline}
    assert graph.session_summary["work_item_count"] == 3
    assert len(graph.fan_out_groups) >= 1
    assert len(graph.joins) >= 1
    assert {"work_declared", "fan_out_declared", "join_declared", "context_transferred"} <= event_types

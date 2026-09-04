"""Public composition fork, durable location, and read-only storage gates."""

from dataclasses import replace

import pytest

from qitos.config import SessionConfig, TrajectoryConfig, build_agent_composition
from qitos.config.errors import CompositionError
from qitos.core.session import SessionContractError
from qitos.kit.env.host_env import HostEnv
from test_g5_audit_regressions import _persisted_config
from test_s4_lane_a_public_authoring import _ActionModel, _FinalModel, _PauseAfterFirstStep


@pytest.mark.parametrize("terminal", [False, True])
def test_public_fork_keeps_source_identity_and_duplicate_operation(tmp_path, terminal):
    config = _persisted_config(tmp_path)
    model = _FinalModel() if terminal else _ActionModel()
    with build_agent_composition(config, model_override=model,
                                 env_override=HostEnv(workspace_root=str(tmp_path))) as composition:
        if not terminal:
            composition.runtime.lifecycle_policy = _PauseAfterFirstStep()
        parent = composition.session("persist source")
        parent.run()
        before = parent.current_head
        child = composition.fork(parent.session_id, operation_id="fork_1234567890abcdef1234567890abcdef")
        with pytest.raises(SessionContractError) as duplicate:
            composition.fork(parent.session_id, before.snapshot_id,
                             operation_id="fork_1234567890abcdef1234567890abcdef")
        assert duplicate.value.error_code.value == "duplicate_fork_operation"
        assert child.session_id != parent.session_id
        assert child.current_head.owner_run_id != before.owner_run_id
        assert parent.current_head == before


def test_historical_fork_does_not_claim_concurrent_source_owner(tmp_path):
    config = _persisted_config(tmp_path)
    def composed():
        return build_agent_composition(config, model_override=_ActionModel(),
                                       env_override=HostEnv(workspace_root=str(tmp_path)))
    with composed() as first, composed() as second:
        first.runtime.lifecycle_policy = _PauseAfterFirstStep()
        parent = first.session("pause")
        parent.run()
        historical = parent.current_head.snapshot_id
        owner = second.restore(parent.session_id)
        before = owner.current_head
        child = first.fork(parent.session_id, historical)
        assert child.fork_receipt.source_snapshot_id == historical.value
        assert owner.current_head == before


def test_public_fork_persistence_failure_preserves_source(tmp_path, monkeypatch):
    config = _persisted_config(tmp_path)
    with build_agent_composition(config, model_override=_FinalModel(),
                                 env_override=HostEnv(workspace_root=str(tmp_path))) as composition:
        parent = composition.session("finish")
        parent.run()
        before = parent.current_head
        from qitos.checkpoint.session import CheckpointPersistenceError

        def fail(request):
            raise CheckpointPersistenceError("injected failure")
        monkeypatch.setattr(composition.runtime.checkpoint_store, "fork_session_snapshot", fail)
        with pytest.raises((SessionContractError, CheckpointPersistenceError)):
            composition.fork(parent.session_id)
        assert parent.current_head == before


def test_default_sqlite_location_is_derived_and_unwritable_location_fails_before_model(tmp_path, monkeypatch):
    import qitos.config.builder as module
    config = _persisted_config(tmp_path)
    config = replace(config, runtime=replace(config.runtime, session=SessionConfig(),
                                              data_root=str(tmp_path / "data")))
    with build_agent_composition(config, model_override=_FinalModel(),
                                 env_override=HostEnv(workspace_root=str(tmp_path))) as composition:
        parent = composition.session("durable by default")
        parent.run()
        identity = parent.session_id.value
    from qitos.checkpoint import SqliteCheckpointStore
    path = tmp_path / "data" / "sessions.sqlite3"
    with SqliteCheckpointStore(str(path), read_only=True) as store:
        assert store.get_session_head(identity) is not None
    blocked = tmp_path / "file-not-directory"
    blocked.write_text("input")
    invalid = replace(config, runtime=replace(config.runtime, data_root=str(blocked)))

    def forbidden(*args, **kwargs):
        pytest.fail("model built before persistence rejection")
    monkeypatch.setattr(module, "build_model", forbidden)
    with pytest.raises(CompositionError):
        build_agent_composition(invalid)
    assert blocked.read_text() == "input"


def test_restore_keeps_explicit_tool_approval_and_execution_policy(tmp_path):
    from qitos.core.function_tool_decorator import function_tool
    from qitos.engine.runtime import LifecyclePolicy

    effects = []
    @function_tool(needs_approval=True)
    def approved_output():
        effects.append("explicitly authorized")
        return "published"

    class Model(_FinalModel):
        def __init__(self, phase):
            self.phase = phase

        def call_raw(self, messages, **options):
            self.phase += 1
            if self.phase == 1:
                return {"choices": [{"message": {"content": 'Thought: pause\nAction: approved_output()'}}]}
            if self.phase == 2:
                return {"choices": [{"message": {"content": 'Thought: authorized\nAction: approved_output()'}}]}
            return super().call_raw(messages, **options)

    base = _persisted_config(tmp_path)
    config = replace(base, runtime=replace(base.runtime, trajectory=TrajectoryConfig(
        enabled=True, output=str(tmp_path / "trajectory.journal"))), tool_options={"auto_approve": True, "max_concurrency": 2},
                     failure_policy={"tool": "fail_closed"}, context={"conversation_max_rounds": 20})
    with build_agent_composition(config, model_override=Model(0)) as first:
        first.tool_registry.register(approved_output)
        first.runtime.lifecycle_policy = _PauseAfterFirstStep()
        parent = first.session("approved output")
        parent.run()
        identity = parent.session_id
        assert effects == ["explicitly authorized"]
    with build_agent_composition(config, model_override=Model(1)) as second:
        second.tool_registry.register(approved_output)
        second.runtime.lifecycle_policy = LifecyclePolicy()
        result = second.restore(identity).run(steering="preserve the authorized selection")
        assert result.state.final_result == "done"
        assert effects == ["explicitly authorized", "explicitly authorized"]
        from qitos.qita.reader import candidate_file_reader
        from qitos.tracing.trajectory import PrivacyView, RecordKind
        reader = candidate_file_reader(second.trajectory_path)
        records = reader.read_session(identity.value, view=PrivacyView.RAW_PRIVATE).records
        steering = [item for item in records if item.kind == RecordKind.STEERING]
        assert len(steering) == 1
        assert steering[0].payload["payload"]["steering_receipt"]["applied_once"] is True

"""Required Docker Session continuity keeps workspace truth in private artifacts."""
from dataclasses import replace

from qitos.config import EnvironmentConfig, SessionConfig, build_agent_composition
from test_s4_lane_a_public_authoring import _config, _FinalModel, _PauseAfterFirstStep


class WriteModel(_FinalModel):
    def call_raw(self, messages, **options):
        return {"choices": [{"message": {"content": 'Action: write_file(path="code.py", content="sandbox")'}}]}


def config_for(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "code.py").write_bytes(b"original")
    config = _config(source)
    return replace(config, tool_preset="env_coding", runtime=replace(
        config.runtime, data_root=str(tmp_path / "runtime"), session=SessionConfig(),
        environment=EnvironmentConfig(workspace=str(source), image="qitos-s3-g4-qualification:pytest-debian",
                                      cpus=.5, memory_mb=256, pids_limit=32),
    )), source


def test_docker_session_restores_unpublished_workspace_without_source_changes(tmp_path):
    config, source = config_for(tmp_path)
    with build_agent_composition(config, model_override=WriteModel()) as first:
        first.runtime.lifecycle_policy = _PauseAfterFirstStep()
        session = first.session()
        session.run()
        assert session.lifecycle.value == "paused"
        identity = session.session_id
        parent_head = session.current_head
        child = first.fork(identity, operation_id="fork_5555555555555555")
        assert session.current_head == parent_head
    assert (source / "code.py").read_bytes() == b"original"
    with build_agent_composition(config, model_override=_FinalModel()) as second:
        restored = second.restore(identity)
        assert second.env.fs.read_text("code.py") == "sandbox"
        assert restored.run(steering="keep unpublished output").state.final_result == "done"
    with build_agent_composition(config, model_override=_FinalModel()) as third:
        sibling = third.restore(child.session_id)
        assert third.env.fs.read_text("code.py") == "sandbox"
        assert sibling.session_id != identity
        assert sibling.run().state.final_result == "done"
    assert (source / "code.py").read_bytes() == b"original"


def test_restore_fences_old_sandbox_and_child_allocations_are_isolated(tmp_path):
    import json
    import subprocess
    import pytest
    from qitos.core.env import EnvCapabilityError
    config, source = config_for(tmp_path)
    with build_agent_composition(config, model_override=WriteModel()) as first:
        first.runtime.lifecycle_policy = _PauseAfterFirstStep()
        parent = first.session()
        parent.run()
        old_env = first.env
        original_head = parent.current_head
        child = first.fork(parent.session_id, operation_id="fork_6666666666666666")
        assert parent.current_head == original_head
        with build_agent_composition(config, model_override=_FinalModel()) as second:
            resumed = second.restore(parent.session_id)
            with pytest.raises(EnvCapabilityError) as stale:
                old_env.cmd.run("printf forbidden > code.py")
            assert stale.value.code == "stale_sandbox_owner"
            with build_agent_composition(config, model_override=_FinalModel()) as third:
                restored_child = third.restore(child.session_id)
                assert second.env.container != third.env.container
                second.env.fs.write_text("code.py", "parent")
                third.env.fs.write_text("code.py", "child")
                assert second.env.fs.read_text("code.py") == "parent"
                assert third.env.fs.read_text("code.py") == "child"
                for composition, session in ((second, resumed), (third, restored_child)):
                    facts = json.loads(subprocess.check_output(["docker", "inspect", composition.env.container]))[0]
                    labels = facts["Config"]["Labels"]
                    assert labels["qitos.sandbox.session_id"] == session.session_id.value
                    assert labels["qitos.sandbox.run_id"] == session.run_id.value
                    assert labels["qitos.sandbox.work_item_id"] == session.work_item_id.value
                    assert labels["qitos.sandbox.attempt_id"] == session.attempt_id.value
    assert (source / "code.py").read_bytes() == b"original"


def test_missing_workspace_artifact_rejects_before_claiming_session(tmp_path):
    import pytest
    from qitos.core.env import EnvCapabilityError
    config, source = config_for(tmp_path)
    with build_agent_composition(config, model_override=WriteModel()) as first:
        first.runtime.lifecycle_policy = _PauseAfterFirstStep()
        parent = first.session()
        parent.run()
        head = parent.current_head
        artifact = first.env.output_artifact
    (tmp_path / "runtime" / "artifacts" / artifact.sha256).unlink()
    with build_agent_composition(config, model_override=_FinalModel()) as second:
        with pytest.raises(EnvCapabilityError) as missing:
            second.restore(parent.session_id)
        assert missing.value.code == "sandbox_artifact_unavailable"
        persisted = second.runtime.checkpoint_store.get_session_head(parent.session_id.value)
        assert persisted.generation == head.generation.value
        assert persisted.owner_run_id == head.owner_run_id.value
    assert (source / "code.py").read_bytes() == b"original"

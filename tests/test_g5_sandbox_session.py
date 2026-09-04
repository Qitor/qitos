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

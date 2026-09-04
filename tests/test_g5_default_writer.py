"""Canonical public paths select one authoritative journal writer."""
from dataclasses import replace
from pathlib import Path

from qitos.config import TrajectoryConfig, build_agent_composition
from qitos.qita.reader import candidate_file_reader
from qitos.tracing.trajectory import PrivacyView
from test_s4_lane_a_public_authoring import _config, _FinalModel
from test_engine_core_flow import DemoAgent


def test_declarative_default_writes_complete_journal(tmp_path):
    base = _config(tmp_path)
    config = replace(base, runtime=replace(base.runtime,
        trajectory=TrajectoryConfig(output=str(tmp_path / 'runs'))))
    with build_agent_composition(config, model_override=_FinalModel()) as composition:
        result = composition.session('default writer').run()
        assert composition.engine.trace_writer is None
    path = tmp_path / 'runs/trajectory.journal'
    assert path.is_file()
    records = candidate_file_reader(path).read_run(result.run_id, view=PrivacyView.RAW_PRIVATE).records
    assert records and any(record.phase == 'CHECK_STOP' for record in records)
    assert not list(tmp_path.rglob('manifest.json'))


def test_agent_run_default_uses_journal_without_legacy_writer(tmp_path):
    result = DemoAgent().run('calculate', render=False, trace_logdir=str(tmp_path), return_state=True,
                             engine_kwargs={'auto_approve': True})
    assert result.state.final_result == '42'
    path = tmp_path / 'trajectory.journal'
    assert path.is_file()
    assert candidate_file_reader(path).read_run(result.run_id).records
    assert not list(tmp_path.rglob('manifest.json'))


def test_explicit_trace_false_disables_default_writer(tmp_path):
    DemoAgent().run('calculate', render=False, trace=False, trace_logdir=str(tmp_path),
                   engine_kwargs={'auto_approve': True})
    assert list(Path(tmp_path).iterdir()) == []

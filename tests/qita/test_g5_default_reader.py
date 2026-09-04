"""Default reader selection and non-destructive compatibility rollback."""
import hashlib
from pathlib import Path

from qitos.qita.reader import default_reader, candidate_file_reader, load_run_payload
from qitos.qita._cli_app import _resolve_run
from qitos.tracing.journal_store import JournalTrajectoryStore
from qitos.tracing.trajectory import RecordKind, TrajectoryRecord
from test_reader_parity import _trace_run


def test_default_reads_mixed_sources_and_rollback_preserves_bytes(tmp_path):
    _trace_run(tmp_path)
    path = tmp_path / 'trajectory.journal'
    store = JournalTrajectoryStore(path)
    try:
        store.append(TrajectoryRecord.create(RecordKind.RUN, run_id='new-run',
            payload={'run_id': 'new-run', 'status': 'completed', 'summary': {'final_result': 'new'}}))
    finally:
        store.close()
    before = {str(p.relative_to(tmp_path)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in tmp_path.rglob('*') if p.is_file()}
    reader = default_reader(tmp_path)
    assert {r.run_id for r in reader.discover_runs()} == {'new-run', 'compat-run'}
    assert reader.capabilities.default_qualified
    assert load_run_payload(reader, 'new-run')['manifest']['summary']['final_result'] == 'new'
    assert reader.read_run('compat-run').records
    assert _resolve_run(tmp_path, 'new-run') == tmp_path / 'new-run'
    rollback = default_reader(tmp_path, selector='trace')
    assert [r.run_id for r in rollback.discover_runs()] == ['compat-run']
    assert candidate_file_reader(path).read_run('new-run').records
    after = {str(p.relative_to(tmp_path)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in tmp_path.rglob('*') if p.is_file()}
    assert before == after


def test_default_discovery_consumes_all_query_pages(tmp_path):
    path = tmp_path / 'trajectory.journal'
    store = JournalTrajectoryStore(path)
    try:
        store.append_batch(TrajectoryRecord.create(RecordKind.STEP,
            run_id='large-run' if i < 10_001 else 'last-run', payload={'ordinal': i}) for i in range(10_003))
    finally:
        store.close()
    summaries = default_reader(tmp_path).discover_runs()
    assert {r.run_id: r.event_count for r in summaries} == {'large-run': 10_001, 'last-run': 2}


def test_default_reader_projects_real_stop_without_cleanup_overwrite(tmp_path):
    from test_engine_core_flow import DemoAgent
    result = DemoAgent().run('calculate', render=False, trace_logdir=str(tmp_path), return_state=True,
                             engine_kwargs={'auto_approve': True})
    reader = default_reader(tmp_path)
    summary = next(item for item in reader.discover_runs() if item.run_id == result.run_id)
    assert summary.status == 'completed'
    assert summary.stop_reason == 'final'
    assert summary.final_result == '42'
    assert load_run_payload(reader, result.run_id)['manifest']['summary']['final_result'] == '42'
    assert _resolve_run(tmp_path, 'absent-run') is None


def test_default_reader_rejects_conflicting_authorities_and_corrupt_journal(tmp_path):
    import pytest
    from qitos.tracing.store import StoreIntegrityError
    _trace_run(tmp_path)
    path = tmp_path / 'trajectory.journal'
    store = JournalTrajectoryStore(path)
    store.append(TrajectoryRecord.create(RecordKind.RUN, run_id='compat-run'))
    store.close()
    reader = default_reader(tmp_path)
    with pytest.raises(ValueError, match='trajectory_source_identity_conflict'):
        reader.discover_runs()
    with pytest.raises(ValueError, match='trajectory_source_identity_conflict'):
        reader.read_run('compat-run')
    path.write_bytes(b'corrupt\n')
    with pytest.raises(StoreIntegrityError):
        default_reader(tmp_path)
    assert default_reader(tmp_path, selector='trace').read_run('compat-run').records

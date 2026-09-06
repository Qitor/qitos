"""Procedural documents and executable programs consume one durable library."""
import json
import subprocess
import sys

import pytest

from qitos.kit.tool.library.base import ToolArtifact


def library_type():
    from qitos.kit.tool.library.sqlite_store import SqliteToolLibrary
    return SqliteToolLibrary


@pytest.mark.parametrize('kind,source', [('procedure', 'Read evidence.\n' * 400),
                                      ('program', 'def normalize(x):\n    return x.strip()\n')])
def test_two_consumers_reopen_and_load_full_source(tmp_path, kind, source):
    path = tmp_path / 'skills.db'
    with library_type()(path, namespace=kind) as store:
        added = store.add_or_update(ToolArtifact('normalize', 'normalize evidence', source,
                                                metadata={'kind': kind, 'verified': True}))
        assert added.version == 1
        added.metadata['verified'] = False
        assert store.get('normalize').metadata['verified'] is True
        catalog = store.catalog('normalize')
        assert catalog[0]['name'] == 'normalize'
        assert 'source' not in catalog[0] and 'metadata' not in catalog[0]
    with library_type()(path, namespace=kind) as reopened:
        assert reopened.get('normalize').source == source
        changed = reopened.add_or_update(ToolArtifact('normalize', 'new description', source + '\n'))
        assert changed.version == 2
        assert reopened.get_version('normalize', 1).source == source
        assert reopened.deprecate('normalize') is True
        assert reopened.catalog() == []
        assert reopened.get_version('normalize', 1).active
    with library_type()(path, namespace='other') as other:
        assert other.get('normalize') is None


def test_clean_process_reads_committed_skill(tmp_path):
    path = tmp_path / 'skills.db'
    with library_type()(path, namespace='research') as store:
        store.add_or_update(ToolArtifact('verify', 'check input', 'COMPLETE_PROGRAM'))
    command = ('from qitos.kit.tool.library.sqlite_store import SqliteToolLibrary; '
               'import sys,json; '
               's=SqliteToolLibrary(sys.argv[1],namespace="research"); '
               'print(json.dumps(s.get("verify").source)); s.close()')
    result = subprocess.run([sys.executable, '-c', command, str(path)], check=True,
                            text=True, capture_output=True)
    assert json.loads(result.stdout) == 'COMPLETE_PROGRAM'


def test_invalid_values_do_not_commit_or_echo(tmp_path):
    from qitos.kit.tool.library.sqlite_store import ToolLibraryError
    with library_type()(tmp_path / 'skills.db', namespace='test') as store:
        with pytest.raises(ToolLibraryError) as error:
            store.add_or_update(ToolArtifact('private-name', 'x', 'y', metadata={'x': float('nan')}))
        assert 'private-name' not in str(error.value)
        assert store.catalog() == []


def test_stale_update_is_atomic_and_close_idempotent(tmp_path):
    from qitos.kit.tool.library.sqlite_store import ToolLibraryError
    path = tmp_path / 'skills.db'
    with library_type()(path, namespace='test') as first, library_type()(path, namespace='test') as second:
        first.add_or_update(ToolArtifact('a', 'a', 'one'))
        second.add_or_update(ToolArtifact('a', 'a', 'two'), expected_version=1)
        with pytest.raises(ToolLibraryError, match='version_conflict'):
            first.add_or_update(ToolArtifact('a', 'a', 'stale'), expected_version=1)
        assert first.get('a').source == 'two'
    first.close()
    with pytest.raises(ToolLibraryError, match='closed'):
        first.get('a')

"""Text persistence, borrowed lifecycle and snapshot-safe recall regression."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from qitos.core.context import ContextPolicyError, RequiredContextMissingError
from qitos.core.memory import MemoryRecord, MemoryResourceError, MemorySource
from qitos.kit.memory.adapter import MemorySourceAdapter
from qitos.kit.memory.markdown_file_memory import MarkdownFileMemory
from qitos.kit.memory.memdir_memory import MemdirMemory


def test_two_process_recall_identity_namespace_and_no_host_path(tmp_path):
    root = tmp_path / "project"
    memory = MemdirMemory(str(root), create=True)
    memory.append(MemoryRecord("user", "remembered-value=17", 0))
    source = MemorySourceAdapter(memory, namespace="project", required=True, priority=7)
    first = [item.to_dict() for item in source.contribute(None)]
    script = '''
import json, sys
from qitos.kit.memory.memdir_memory import MemdirMemory
from qitos.kit.memory.adapter import MemorySourceAdapter
source = MemorySourceAdapter(MemdirMemory(sys.argv[1]), namespace="project", required=True, priority=7)
print(json.dumps([item.to_dict() for item in source.contribute(None)]))
'''
    result = subprocess.run([sys.executable, "-c", script, str(root)], check=True,
                            text=True, capture_output=True, cwd=Path(__file__).resolve().parents[1])
    assert json.loads(result.stdout) == first
    assert len(first) == 1
    assert "remembered-value=17" in json.dumps(first)
    assert str(tmp_path) not in json.dumps(first)
    assert first[0]["requested_placement"] == "user"
    assert first[0]["priority"] == 7
    assert isinstance(source, MemorySource)
    other = MemdirMemory(str(tmp_path / "other"), create=True)
    assert MemorySourceAdapter(other, namespace="other").contribute(None) == ()


def test_independent_equal_records_and_revision_edits_are_not_stale(tmp_path):
    memory = MemdirMemory(str(tmp_path), create=True)
    memory.append(MemoryRecord("user", "same", 1))
    memory.append(MemoryRecord("user", "same", 1))
    source = MemorySourceAdapter(memory, namespace="project")
    before = {item.contribution_id: item for item in source.contribute(None)}
    assert len(before) == len(memory.retrieve()) == 2
    assert len({item.revision for item in before.values()}) == 1
    path = next((tmp_path / "user").glob("*.md"))
    path.write_text(path.read_text().replace("\nsame", "\nchanged"))
    after = {item.contribution_id: item for item in source.contribute(None)}
    assert set(before) == set(after)
    assert sum(before[key].revision != after[key].revision for key in before) == 1
    assert "changed" in memory.summarize()
    path.unlink()
    assert "changed" not in memory.summarize()
    assert len(source.contribute(None)) == 1
    memory.reset()
    assert len(source.contribute(None)) == 1


def test_restore_missing_and_removed_root_fail_without_initialization(tmp_path):
    root = tmp_path / "missing"
    with pytest.raises(MemoryResourceError):
        MemdirMemory(str(root))
    assert not root.exists()
    memory = MemdirMemory(str(root), create=True)
    for child in root.iterdir():
        child.rmdir() if child.is_dir() else child.unlink()
    root.rmdir()
    with pytest.raises(MemoryResourceError) as error:
        MemorySourceAdapter(memory, namespace="project").contribute(None)
    assert str(tmp_path) not in str(error.value)
    assert not root.exists()


def test_borrowed_lifecycle_query_and_output_snapshot(tmp_path):
    class Borrowed(MarkdownFileMemory):
        def close(self):
            raise AssertionError("borrowed close")

        def reset(self, run_id=None):
            raise AssertionError("borrowed reset")

    memory = Borrowed(str(tmp_path / "memory.md"))
    record = MemoryRecord("user", {"items": [17]}, 1)
    memory.append(record)
    memory.append(MemoryRecord("assistant", "excluded", 2))
    query = {"roles": ["user"]}
    source = MemorySourceAdapter(memory, namespace="run", query=query)
    query["roles"].clear()
    snapshot = source.contribute(None)
    record.content["items"].append(18)
    snapshot[0].content_value["items"].append(19)
    assert snapshot[0].content_value == {"items": [17]}
    assert source.contribute(None)[0].content_value == {"items": [17, 18]}
    source.reset("next")
    source.close()
    assert len(memory.retrieve()) == 2
    assert (tmp_path / "memory.md").exists()


def test_markdown_fresh_instance_does_not_restore_logged_records(tmp_path):
    path = tmp_path / "memory.md"
    memory = MarkdownFileMemory(str(path))
    memory.append(MemoryRecord("user", "run-only", 1, {"literal": "__import__('os')"}))
    assert MemorySourceAdapter(memory, namespace="run").contribute(None)[0].content_value == "run-only"
    fresh = MemorySourceAdapter(MarkdownFileMemory(str(path)), namespace="run")
    assert fresh.contribute(None) == ()
    with pytest.raises(RequiredContextMissingError):
        MemorySourceAdapter(fresh.memory, namespace="run", required=True).contribute(None)


def test_memdir_query_applies_to_written_records_and_cache_evict_is_not_delete(tmp_path):
    memory = MemdirMemory(str(tmp_path), create=True, max_index_entries=10)
    for index in range(12):
        memory.append(MemoryRecord("user", f"value={index}", index))
    memory.append(MemoryRecord("assistant", "no", 12))
    source = MemorySourceAdapter(memory, namespace="project", query={"contains": "value=1", "roles": ["user"]})
    assert {item.content_value for item in source.contribute(None)} == {"value=1", "value=10", "value=11"}
    assert memory.evict() == 3
    memory.reset()
    assert len(memory.retrieve()) == 13


def test_text_only_and_global_opt_in(tmp_path):
    local = MemdirMemory(str(tmp_path / "local"), create=True)
    global_memory = MemdirMemory(str(tmp_path / "global"), create=True)
    global_memory.append(MemoryRecord("user", "global-secret", 1))
    assert local.retrieve() == []
    with pytest.raises(TypeError, match="text records only"):
        local.append(MemoryRecord("user", {"arbitrary": 17}, 1))
    with pytest.raises(ContextPolicyError):
        MemorySourceAdapter(local, namespace=str(tmp_path))
    assert len(list((tmp_path / "local").rglob("*.md"))) == 1


def test_legacy_text_identity_and_whitespace_round_trip(tmp_path):
    memory = MemdirMemory(str(tmp_path), create=True)
    legacy = tmp_path / "project" / "old.md"
    legacy.write_text("---\nrole: user\nstep_id: 0\n---\nlegacy\n")
    memory.append(MemoryRecord("user", "  text\n\n", 1))
    records = memory.retrieve()
    assert records[1].content == "  text\n\n"
    reconstructed = MemdirMemory(str(tmp_path)).retrieve()
    assert [r.record_id for r in reconstructed] == [r.record_id for r in records]
    assert "path" not in records[0].metadata


def test_reappend_same_identity_updates_one_record_even_if_bucket_changes(tmp_path):
    memory = MemdirMemory(str(tmp_path), create=True)
    record = MemoryRecord("user", "before", 0)
    memory.append(record)
    record.content = "after"
    record.metadata["type"] = "reference"
    memory.append(record)
    assert len(memory.retrieve()) == 1
    assert memory.retrieve()[0].content == "after"
    assert memory.retrieve()[0].record_id == record.record_id


# Reuse the repository's installed-wheel fixture; it checks every shipped source
# file and creates a separate venv without access to editable source imports.
from test_docs_golden_paths import installed  # noqa: E402,F401


def test_installed_configured_two_process_consumer(installed, tmp_path):
    import shutil

    _, python, _ = installed
    source = Path(__file__).resolve().parents[1] / "examples/v5/r1_b_memory_context"
    for filename in ("consumer.py", "agent.yaml"):
        shutil.copy2(source / filename, tmp_path / filename)
    root = tmp_path / "run"
    for mode in ("seed", "run"):
        subprocess.run([str(python), "-I", str(tmp_path / "consumer.py"), mode,
                        "--root", str(root)], cwd=tmp_path, check=True,
                       capture_output=True, text=True, timeout=90)
    report = json.loads((root / "report.json").read_text())
    assert report["requests"] == 10 and report["budget_compactions"] >= 2
    assert report["memory_records"] == 1 and report["namespace_isolated"]
    assert report["namespace_requests"] == 1
    assert "site-packages" in report["qitos_source"]

"""Explicit publication attacks target temporary task-owned trees only."""

import hashlib
import os

import pytest

from qitos.core.env import EnvCapabilityError
from qitos.kit.env._publication import publish_files


def digest(value):
    return hashlib.sha256(value).hexdigest()


def test_explicit_selected_file_publication(tmp_path):
    (tmp_path / "code.py").write_bytes(b"before")
    result = publish_files(tmp_path, {"code.py": digest(b"before")}, {"code.py": b"after"})
    assert result["status"] == "published"
    assert (tmp_path / "code.py").read_bytes() == b"after"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["code.py"]


@pytest.mark.parametrize("path", [
    "../outside", "/absolute", "link/code.py", ".git/config", ".ssh/authorized_keys",
    "credentials.yaml", "secret.txt", ".env.local", "id.key",
])
def test_publication_denies_unselected_or_protected_paths(tmp_path, path):
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    (source / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(EnvCapabilityError):
        publish_files(source, {}, {path: b"untrusted"})
    assert list(outside.iterdir()) == []
    assert sorted(p.name for p in source.iterdir()) == ["link"]


def test_publication_target_ancestor_symlink_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(EnvCapabilityError, match="publication"):
        publish_files(link, {}, {"code.py": b"untrusted"})
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_publication_special_files_are_rejected(tmp_path, kind):
    original = tmp_path / "original"
    original.write_bytes(b"input")
    target = tmp_path / "code.py"
    if kind == "symlink":
        target.symlink_to(original)
    elif kind == "hardlink":
        os.link(original, target)
    else:
        os.mkfifo(target)
    with pytest.raises(EnvCapabilityError):
        publish_files(tmp_path, {"code.py": digest(b"input")}, {"code.py": b"untrusted"})
    assert original.read_bytes() == b"input"


def test_source_conflict_keeps_concurrent_user_bytes(tmp_path):
    (tmp_path / "code.py").write_bytes(b"concurrent")
    with pytest.raises(EnvCapabilityError):
        publish_files(tmp_path, {"code.py": digest(b"original")}, {"code.py": b"sandbox"})
    assert (tmp_path / "code.py").read_bytes() == b"concurrent"


def test_mid_publication_failure_rolls_back_prior_files(tmp_path, monkeypatch):
    import qitos.kit.env._publication as module
    for name in ("first.py", "second.py"):
        (tmp_path / name).write_bytes(b"input")
    original = module._exchange
    calls = 0

    def exchange(directory, source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected exchange failure")
        return original(directory, source, target)
    monkeypatch.setattr(module, "_exchange", exchange)
    with pytest.raises(EnvCapabilityError):
        publish_files(tmp_path, {name: digest(b"input") for name in ("first.py", "second.py")},
                      {"first.py": b"one", "second.py": b"two"})
    assert (tmp_path / "first.py").read_bytes() == b"input"
    assert (tmp_path / "second.py").read_bytes() == b"input"
    assert len(list(tmp_path.iterdir())) == 2


def test_new_file_is_removed_when_later_publication_fails(tmp_path, monkeypatch):
    import qitos.kit.env._publication as module
    (tmp_path / "existing.py").write_bytes(b"original")
    monkeypatch.setattr(module, "_exchange", lambda *args: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(EnvCapabilityError):
        publish_files(tmp_path, {"existing.py": digest(b"original")},
                      {"new.py": b"new", "existing.py": b"changed"})
    assert not (tmp_path / "new.py").exists()
    assert (tmp_path / "existing.py").read_bytes() == b"original"


def test_concurrent_change_between_check_and_exchange_survives_rollback(tmp_path, monkeypatch):
    import qitos.kit.env._publication as module
    target = tmp_path / "code.py"
    target.write_bytes(b"original")
    exchange = module._exchange
    calls = 0

    def change_then_exchange(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            target.write_bytes(b"concurrent")
        exchange(*args)
    monkeypatch.setattr(module, "_exchange", change_then_exchange)
    with pytest.raises(EnvCapabilityError):
        publish_files(tmp_path, {"code.py": digest(b"original")}, {"code.py": b"sandbox"})
    assert target.read_bytes() == b"concurrent"


def test_publication_preserves_executable_mode(tmp_path):
    target = tmp_path / "script.py"
    target.write_bytes(b"original")
    target.chmod(0o755)
    publish_files(tmp_path, {"script.py": digest(b"original")}, {"script.py": b"changed"})
    assert target.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize("original", [b"", b"bounded-hash-input" * 100000], ids=["empty", "multi-chunk"])
def test_publication_hashing_works_without_python_311_file_digest(tmp_path, monkeypatch, original):
    """Exercise existing-file exchange with the Python 3.10 hashlib surface."""
    monkeypatch.delattr(hashlib, "file_digest", raising=False)
    target = tmp_path / "data.bin"
    target.write_bytes(original)
    result = publish_files(tmp_path, {"data.bin": digest(original)}, {"data.bin": b"published"})
    assert result["output_digests"] == {"data.bin": digest(b"published")}
    assert target.read_bytes() == b"published"
    assert [path.name for path in tmp_path.iterdir()] == ["data.bin"]

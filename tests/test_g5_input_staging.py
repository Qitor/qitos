"""Staging attacks use only this test's temporary input and outside directory."""
import builtins
import os
from pathlib import Path
import subprocess

import pytest

from qitos.core.env import EnvCapabilityError
from qitos.kit.env.docker_env import DockerEnv
from qitos.kit.env.sandbox import SandboxPolicy


def test_source_leaf_swap_cannot_import_bytes_outside_input(tmp_path, monkeypatch):
    import qitos.kit.env.docker_env as module

    source = tmp_path / "source"
    source.mkdir()
    leaf = source / "input.txt"
    leaf.write_bytes(b"selected input")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"OUTSIDE_INPUT_BYTES")
    staging = tmp_path / "staging"
    staging.mkdir()
    env = DockerEnv(container="owned-staging-fixture", host_workspace=str(source),
                    policy=SandboxPolicy(image="fixture"))
    monkeypatch.setattr(module.tempfile, "mkdtemp", lambda **kw: str(staging))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, b"", b""))
    actual_open, actual_os_open = builtins.open, os.open
    attacked = []

    def swap():
        if not attacked:
            leaf.unlink()
            leaf.symlink_to(outside)
            attacked.append(True)

    def file_open(path, mode="r", *args, **kwargs):
        if not isinstance(path, int) and Path(path) == leaf and mode == "rb":
            swap()
        return actual_open(path, mode, *args, **kwargs)

    def descriptor_open(path, flags, *args, **kwargs):
        if path == leaf.name and "dir_fd" in kwargs:
            swap()
        return actual_os_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", file_open)
    monkeypatch.setattr(os, "open", descriptor_open)
    with pytest.raises(EnvCapabilityError):
        env._stage_private_workspace()
    assert attacked
    assert outside.read_bytes() == b"OUTSIDE_INPUT_BYTES"
    for item in staging.rglob("*"):
        if item.is_file() and not item.is_symlink():
            assert b"OUTSIDE_INPUT_BYTES" not in item.read_bytes()


@pytest.mark.parametrize("kind", ["fifo", "hardlink", "oversize"])
def test_staging_special_files_and_size_fail_closed(tmp_path, kind):
    from qitos.kit.env._input_staging import _stage_input

    source = tmp_path / "source"
    source.mkdir()
    if kind == "fifo":
        os.mkfifo(source / "pipe")
    elif kind == "hardlink":
        (tmp_path / "outside").write_bytes(b"outside")
        os.link(tmp_path / "outside", source / "alias")
    else:
        (source / "big").write_bytes(b"x" * 17)
    with pytest.raises(EnvCapabilityError):
        _stage_input(source, tmp_path / "stage", byte_limit=16)


def test_staging_omits_protected_names_and_links_without_reading_them(tmp_path):
    from qitos.kit.env._input_staging import _stage_input

    source = tmp_path / "source"
    source.mkdir()
    (source / "safe").write_bytes(b"safe")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "unselected").write_bytes(b"unselected")
    (source / "link").symlink_to(outside, target_is_directory=True)
    for name in (".git", ".ssh", ".env", "credentials.json", "secret.txt", "key.pem"):
        (source / name).write_bytes(b"PRIVATE_FIXTURE")
    digests = _stage_input(source, tmp_path / "stage", byte_limit=100)
    assert set(digests) == {"safe"}
    assert [item.name for item in (tmp_path / "stage").iterdir()] == ["safe"]

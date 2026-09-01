"""Credential resolver security and non-disclosure tests."""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest

from qitos.config.credentials import (
    CredentialRef,
    EnvironmentCredentialResolver,
    FakeCredentialResolver,
    LocalCredentialFileResolver,
)
from qitos.config.errors import (
    CredentialFileSecurityError,
    CredentialNotFoundError,
)


def _credential_file(
    tmp_path: Path, text: str = "credentials:\n  demo: private-value\n"
) -> Path:
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "credentials.yaml"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def test_fake_resolution_receipt_never_contains_value() -> None:
    resolution = FakeCredentialResolver({"demo": "private-value"}).resolve(
        CredentialRef("demo")
    )
    assert resolution.secret.reveal_for_composition() == "private-value"
    assert "private-value" not in repr(resolution)
    assert "private-value" not in repr(resolution.receipt())
    with pytest.raises(TypeError):
        pickle.dumps(resolution.secret)


def test_local_file_resolver_enforces_shape_mode_and_requested_ref(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    path = _credential_file(
        tmp_path,
        "credentials:\n  one: first-private\n  two: second-private\n",
    )
    resolver = LocalCredentialFileResolver(path, repository_root=repository)

    resolution = resolver.resolve(CredentialRef("two"))

    assert resolution.secret.reveal_for_composition() == "second-private"
    assert resolution.receipt()["resolver"] == "local_file"
    assert "second-private" not in repr(resolution.receipt())


def test_local_file_resolver_rejects_missing_ref_without_echoing_values(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    path = _credential_file(tmp_path)
    resolver = LocalCredentialFileResolver(path, repository_root=repository)

    with pytest.raises(CredentialNotFoundError) as captured:
        resolver.resolve(CredentialRef("absent"))
    assert "private-value" not in str(captured.value)


def test_local_file_resolver_rejects_mode_and_symlink(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    path = _credential_file(tmp_path)
    path.chmod(0o644)
    with pytest.raises(CredentialFileSecurityError, match="0600"):
        LocalCredentialFileResolver(path, repository_root=repository).resolve(
            CredentialRef("demo")
        )
    path.chmod(0o600)
    link = path.parent / "linked.yaml"
    link.symlink_to(path)
    with pytest.raises(CredentialFileSecurityError, match="non-symlink"):
        LocalCredentialFileResolver(link, repository_root=repository).resolve(
            CredentialRef("demo")
        )


def test_local_file_resolver_rejects_repository_path(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir(mode=0o700)
    path = repository / "credentials.yaml"
    path.write_text("credentials:\n  demo: value\n", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(CredentialFileSecurityError, match="outside"):
        LocalCredentialFileResolver(path, repository_root=repository).resolve(
            CredentialRef("demo")
        )


def test_environment_resolver_is_explicit_and_receipted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QITOS_COMPAT_DEMO", "private-value")
    resolution = EnvironmentCredentialResolver().resolve(
        CredentialRef("env:QITOS_COMPAT_DEMO")
    )
    assert resolution.compatibility is True
    assert resolution.receipt()["warnings"] == [
        "ambient_environment_credential_compatibility"
    ]
    monkeypatch.delenv("QITOS_COMPAT_DEMO")
    with pytest.raises(CredentialNotFoundError):
        EnvironmentCredentialResolver().resolve(
            CredentialRef("env:QITOS_COMPAT_DEMO")
        )


def test_parent_directory_must_not_be_group_or_world_writable(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    path = _credential_file(tmp_path)
    path.parent.chmod(0o722)
    try:
        with pytest.raises(CredentialFileSecurityError, match="group/world"):
            LocalCredentialFileResolver(path, repository_root=repository).resolve(
                CredentialRef("demo")
            )
    finally:
        path.parent.chmod(0o700)


def test_parent_directory_must_not_be_group_or_world_readable(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    path = _credential_file(tmp_path)
    path.parent.chmod(0o750)
    try:
        with pytest.raises(CredentialFileSecurityError, match="group/world"):
            LocalCredentialFileResolver(path, repository_root=repository).resolve(
                CredentialRef("demo")
            )
    finally:
        path.parent.chmod(0o700)

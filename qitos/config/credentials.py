"""Credential-reference boundaries for canonical agent composition.

Resolvers return an intentionally non-serializable secret wrapper. Callers may
reveal it only at the model-client construction boundary.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Protocol

import yaml

from .errors import (
    CredentialFileSecurityError,
    CredentialNotFoundError,
    CredentialResolutionError,
)


@dataclass(frozen=True)
class CredentialRef:
    """Serializable logical identity of one credential."""

    ref: str

    def __post_init__(self) -> None:
        value = self.ref.strip() if isinstance(self.ref, str) else ""
        if not value or any(character.isspace() for character in value):
            raise CredentialResolutionError(
                "credential reference must be a non-empty token",
                field="model.credential.ref",
            )
        object.__setattr__(self, "ref", value)

    def to_dict(self) -> Dict[str, str]:
        return {"ref": self.ref}


class SecretValue:
    """A non-serializable resolved secret scoped to composition."""

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not value:
            raise CredentialResolutionError("resolved credential is empty")
        self.__value = value

    def reveal_for_composition(self) -> str:
        return self.__value

    def __repr__(self) -> str:
        return "SecretValue(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"

    def __reduce__(self) -> Any:
        raise TypeError("resolved credentials cannot be serialized")


@dataclass(frozen=True)
class CredentialResolution:
    """A secret plus its safe, deterministic resolution receipt."""

    secret: SecretValue
    ref: CredentialRef
    resolver: str
    compatibility: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def receipt(self) -> Dict[str, Any]:
        return {
            "ref": self.ref.ref,
            "resolver": self.resolver,
            "compatibility": self.compatibility,
            "warnings": list(self.warnings),
        }


class CredentialResolver(Protocol):
    """Replaceable authority used at model composition time."""

    def resolve(self, ref: CredentialRef) -> CredentialResolution:
        ...


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: yaml.SafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> Dict[Any, Any]:
    mapping: Dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise CredentialResolutionError("credential file contains a duplicate key")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


class LocalCredentialFileResolver:
    """Resolve one logical credential from a hardened local YAML file."""

    def __init__(self, path: str | Path, *, repository_root: str | Path) -> None:
        self._path = Path(path).expanduser()
        self._repository_root = Path(repository_root).expanduser().resolve()

    def _validate_path(self) -> Path:
        try:
            path_stat = self._path.lstat()
        except FileNotFoundError as exc:
            raise CredentialFileSecurityError("credential file does not exist") from exc
        if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            raise CredentialFileSecurityError(
                "credential file must be a regular non-symlink file"
            )
        if path_stat.st_uid != os.getuid():
            raise CredentialFileSecurityError(
                "credential file must be owned by the current user"
            )
        if stat.S_IMODE(path_stat.st_mode) != 0o600:
            raise CredentialFileSecurityError("credential file mode must be 0600")
        path = self._path.resolve(strict=True)
        try:
            path.relative_to(self._repository_root)
        except ValueError:
            pass
        else:
            raise CredentialFileSecurityError(
                "credential file must live outside the repository"
            )
        parent_stat = path.parent.stat()
        if parent_stat.st_uid != os.getuid():
            raise CredentialFileSecurityError(
                "credential directory must be owned by the current user"
            )
        if stat.S_IMODE(parent_stat.st_mode) & 0o077:
            raise CredentialFileSecurityError(
                "credential directory must not grant group/world permissions"
            )
        return path

    def resolve(self, ref: CredentialRef) -> CredentialResolution:
        path = self._validate_path()
        try:
            payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
        except CredentialResolutionError:
            raise
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise CredentialResolutionError(
                "credential file is not a valid strict YAML mapping"
            ) from exc
        if not isinstance(payload, dict) or set(payload) != {"credentials"}:
            raise CredentialResolutionError(
                "credential file root must contain only a credentials mapping"
            )
        credentials = payload.get("credentials")
        if not isinstance(credentials, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in credentials.items()
        ):
            raise CredentialResolutionError(
                "credentials must map string references to string values"
            )
        value = credentials.get(ref.ref)
        if value is None:
            raise CredentialNotFoundError(
                "requested credential reference is not present",
                field="model.credential.ref",
            )
        if not value:
            raise CredentialResolutionError(
                "requested credential reference resolves to an empty value",
                field="model.credential.ref",
            )
        return CredentialResolution(
            secret=SecretValue(value),
            ref=ref,
            resolver="local_file",
        )


class FakeCredentialResolver:
    """Deterministic resolver for tests and offline qualification."""

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self._values = dict(values or {})

    def resolve(self, ref: CredentialRef) -> CredentialResolution:
        value = self._values.get(ref.ref, f"fake::{ref.ref}")
        return CredentialResolution(
            secret=SecretValue(value),
            ref=ref,
            resolver="fake",
        )


class EnvironmentCredentialResolver:
    """Explicit compatibility adapter for ambient environment credentials."""

    def resolve(self, ref: CredentialRef) -> CredentialResolution:
        variable = ref.ref[4:] if ref.ref.startswith("env:") else ref.ref
        value = os.environ.get(variable)
        if not value:
            raise CredentialNotFoundError(
                "requested environment credential is missing",
                field="model.credential.ref",
                remediation="configure a local credential-file resolver",
            )
        return CredentialResolution(
            secret=SecretValue(value),
            ref=ref,
            resolver="environment_compatibility",
            compatibility=True,
            warnings=("ambient_environment_credential_compatibility",),
        )


__all__ = [
    "CredentialRef",
    "CredentialResolution",
    "CredentialResolver",
    "EnvironmentCredentialResolver",
    "FakeCredentialResolver",
    "LocalCredentialFileResolver",
    "SecretValue",
]

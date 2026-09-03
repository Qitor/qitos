"""Canonical artifact reference shared by stable core contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Dict, Mapping, Optional, Protocol, runtime_checkable

from .diagnostics import diagnostic_string_is_sensitive


ARTIFACT_REF_SCHEMA_VERSION = "qitos.artifact_ref/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LOGICAL_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,255}$")
_MEDIA_TYPE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+\-]{0,126}/"
    r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+\-]{0,126}$"
)
_SENSITIVITY = frozenset({"public", "internal", "confidential", "restricted"})


class ArtifactContractError(ValueError):
    """Typed failure that never reflects a rejected artifact value."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _fail(code: str, message: str) -> ArtifactContractError:
    return ArtifactContractError(code, message)


def _safe_token(value: Any, field: str) -> str:
    pattern = _MEDIA_TYPE if field == "media_type" else _LOGICAL_TOKEN
    if (
        not isinstance(value, str)
        or pattern.fullmatch(value) is None
        or diagnostic_string_is_sensitive(value)
    ):
        raise _fail("invalid_artifact_reference", f"{field} is invalid")
    return value


@dataclass(frozen=True)
class ResolvedArtifact:
    """Ephemeral verified artifact body; never a snapshot representation."""

    reference: "ArtifactRef"
    body: bytes = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ArtifactRef):
            raise _fail("invalid_artifact_resolution", "artifact reference is invalid")
        if not isinstance(self.body, bytes):
            raise _fail("invalid_artifact_resolution", "artifact body must be bytes")
        if len(self.body) != self.reference.byte_length:
            raise _fail("artifact_integrity_mismatch", "artifact length does not match")
        if hashlib.sha256(self.body).hexdigest() != self.reference.sha256:
            raise _fail("artifact_integrity_mismatch", "artifact digest does not match")


@runtime_checkable
class ArtifactResolver(Protocol):
    """Injected content resolver with no host-path or global-registry contract."""

    resolver_key: str

    def probe(self, reference: "ArtifactRef") -> bool:
        """Return whether the exact content-addressed reference is available."""

    def resolve(self, reference: "ArtifactRef") -> ResolvedArtifact:
        """Return a verified ephemeral body for an explicitly requested ref."""


@dataclass(frozen=True)
class ArtifactRef:
    """Portable content-addressed pointer; never an artifact body or host path."""

    artifact_id: str
    resolver_key: str
    sha256: str
    media_type: str
    byte_length: int
    encoding: str = "binary"
    sensitivity: str = "internal"
    provenance_digest: Optional[str] = None
    model_summary: Optional[str] = None
    required: bool = True
    schema_version: str = ARTIFACT_REF_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ARTIFACT_REF_SCHEMA_VERSION:
            raise _fail("unsupported_artifact_schema", "artifact schema is unsupported")
        for field_name in ("artifact_id", "resolver_key", "media_type", "encoding"):
            object.__setattr__(
                self,
                field_name,
                _safe_token(getattr(self, field_name), field_name),
            )
        if not isinstance(self.sha256, str) or _SHA256.fullmatch(self.sha256) is None:
            raise _fail("invalid_artifact_digest", "artifact digest must be lowercase SHA-256")
        if (
            not isinstance(self.byte_length, int)
            or isinstance(self.byte_length, bool)
            or self.byte_length < 0
        ):
            raise _fail("invalid_artifact_size", "artifact byte_length must be non-negative")
        if self.sensitivity not in _SENSITIVITY:
            raise _fail("invalid_artifact_sensitivity", "artifact sensitivity is unsupported")
        if self.provenance_digest is not None and (
            not isinstance(self.provenance_digest, str)
            or _SHA256.fullmatch(self.provenance_digest) is None
        ):
            raise _fail("invalid_artifact_digest", "artifact provenance digest is invalid")
        if self.model_summary is not None:
            if (
                not isinstance(self.model_summary, str)
                or not self.model_summary.strip()
                or len(self.model_summary) > 1024
                or diagnostic_string_is_sensitive(self.model_summary)
            ):
                raise _fail("unsafe_model_projection", "artifact model summary is unsafe")
            object.__setattr__(self, "model_summary", self.model_summary.strip())
        if not isinstance(self.required, bool):
            raise _fail("invalid_artifact_reference", "artifact required flag must be boolean")

    def to_dict(self) -> Dict[str, Any]:
        self.__post_init__()
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "resolver_key": self.resolver_key,
            "sha256": self.sha256,
            "media_type": self.media_type,
            "byte_length": self.byte_length,
            "encoding": self.encoding,
            "sensitivity": self.sensitivity,
            "provenance_digest": self.provenance_digest,
            "model_summary": self.model_summary,
            "required": self.required,
        }

    def to_model_projection(self) -> Dict[str, Any]:
        """Return the allowlisted model-facing reference facts."""

        self.__post_init__()
        return {
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "media_type": self.media_type,
            "byte_length": self.byte_length,
            "model_summary": self.model_summary,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ArtifactRef":
        fields = {
            "schema_version",
            "artifact_id",
            "resolver_key",
            "sha256",
            "media_type",
            "byte_length",
            "encoding",
            "sensitivity",
            "provenance_digest",
            "model_summary",
            "required",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise _fail("invalid_artifact_reference", "artifact reference shape is invalid")
        return cls(**dict(value))


def require_artifact(
    reference: ArtifactRef,
    resolver: Optional[ArtifactResolver],
) -> None:
    """Fail closed for required references without loading artifact bodies."""

    if resolver is None or not isinstance(resolver, ArtifactResolver):
        if reference.required:
            raise _fail(
                "missing_required_artifact",
                "required artifact resolver is unavailable",
            )
        return
    if resolver.resolver_key != reference.resolver_key:
        if reference.required:
            raise _fail(
                "missing_required_artifact",
                "required artifact resolver identity does not match",
            )
        return
    try:
        available = resolver.probe(reference)
    except Exception as exc:
        raise _fail(
            "artifact_resolution_failed",
            "artifact availability could not be checked safely",
        ) from exc
    if not isinstance(available, bool):
        raise _fail(
            "invalid_artifact_resolution",
            "artifact resolver probe must return boolean",
        )
    if reference.required and not available:
        raise _fail("missing_required_artifact", "required artifact is unavailable")


__all__ = [
    "ARTIFACT_REF_SCHEMA_VERSION",
    "ArtifactContractError",
    "ArtifactResolver",
    "ResolvedArtifact",
    "ArtifactRef",
    "require_artifact",
]

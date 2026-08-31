"""Privacy, portability and bounded diagnostic projections for trajectories."""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from enum import Enum
from itertools import islice
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .trajectory import LossEntry, LossReport, PrivacyView


REDACTED = "__redacted__"
OMITTED = "__omitted__"

_SENSITIVE_KEY_PARTS = frozenset(
    {
        "apikey",
        "authorization",
        "cookie",
        "credentials",
        "password",
        "privatekey",
        "refreshtoken",
        "secret",
        "setcookie",
        "token",
    }
)
_PROVIDER_RAW_KEY_PARTS = frozenset(
    {
        "providerraw",
        "providerresponse",
        "rawprovider",
        "rawresponse",
    }
)
_ARTIFACT_BODY_KEY_PARTS = frozenset(
    {"artifactbody", "artifactcontent", "artifactpayload", "blobbody"}
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(?:authorization|cookie|set-cookie)\s*:\s*\S+"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret)\s*[=:]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)
_HOST_PATH_PATTERNS = (
    re.compile(
        r"(?:^|[\s\"'=])/(?:Applications|Library|System|Users|Volumes|etc|"
        r"home|mnt|opt|private|root|srv|tmp|usr|var|workspace)(?:/|$)"
    ),
    re.compile(r"(?:^|[\s\"'=])[A-Za-z]:[\\/]"),
    re.compile(r"(?:^|[\s\"'=])\\\\[^\\]+\\[^\\]+"),
    re.compile(r"(?:^|[\s\"'=])file://", re.IGNORECASE),
    re.compile(r"(?:^|[\s\"'=])~[/\\]"),
    re.compile(r"(?:^|[\s\"'=])/(?:[A-Za-z0-9._-]+/)+[A-Za-z0-9._-]*"),
)
_LOCAL_ENDPOINT_PATTERNS = (
    re.compile(r"(?i)\b(?:localhost|127\.0\.0\.1)(?::\d+)?\b"),
    re.compile(r"(?i)https?://\[::1\](?::\d+)?"),
    re.compile(
        r"(?i)\b(?:https?://)?(?:10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])"
        r"(?:\.\d{1,3}){2}|169\.254(?:\.\d{1,3}){2}|0\.0\.0\.0)"
        r"(?::\d+)?\b"
    ),
    re.compile(r"(?i)\bhttps?://[^\s/]+\.local(?::\d+)?\b"),
)


class ProviderRawPolicy(str, Enum):
    """Treatment of provider-owned raw payloads in a projection."""

    PRESERVE_PRIVATE = "preserve_private"
    REFERENCE_ONLY = "reference_only"
    OMIT = "omit"


@dataclass(frozen=True)
class ProjectionLimits:
    """Hard bounds for public and diagnostic log material."""

    max_depth: int = 12
    max_mapping_items: int = 256
    max_sequence_items: int = 256
    max_string_chars: int = 16_384
    max_total_nodes: int = 20_000

    def __post_init__(self) -> None:
        if min(
            self.max_depth,
            self.max_mapping_items,
            self.max_sequence_items,
            self.max_string_chars,
            self.max_total_nodes,
        ) < 0:
            raise ValueError("projection limits must be non-negative")


@dataclass(frozen=True)
class ProjectionFinding:
    """Non-echoing projection finding."""

    code: str
    location: str
    action: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "location": self.location,
            "action": self.action,
        }


@dataclass(frozen=True)
class ProjectionResult:
    """Projected data and its machine-readable fidelity report."""

    data: Any
    view: PrivacyView
    findings: Tuple[ProjectionFinding, ...]
    loss: LossReport


def _normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _sensitive_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    if normalized in _SENSITIVE_KEY_PARTS:
        return True
    for part in _SENSITIVE_KEY_PARTS - {"token"}:
        if part in normalized:
            return True
    return normalized.endswith("token") and not normalized.endswith("tokens")


def _provider_raw_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    return any(part in normalized for part in _PROVIDER_RAW_KEY_PARTS)


def _artifact_body_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    return any(part in normalized for part in _ARTIFACT_BODY_KEY_PARTS)


def _unsafe_string_code(value: str) -> Optional[str]:
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        return "secret_value"
    if any(pattern.search(value) for pattern in _HOST_PATH_PATTERNS):
        return "host_path"
    if any(pattern.search(value) for pattern in _LOCAL_ENDPOINT_PATTERNS):
        return "local_endpoint"
    return None


def _json_ready(value: Any, *, private: bool) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value) if private else {"type": type(value).__name__}
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item, private=private) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_ready(item, private=private) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if private:
        return repr(value)
    return {"type": type(value).__name__, "value": OMITTED}


class _Projector:
    def __init__(
        self,
        view: PrivacyView,
        limits: ProjectionLimits,
        provider_raw_policy: ProviderRawPolicy,
    ) -> None:
        self.view = view
        self.limits = limits
        self.provider_raw_policy = provider_raw_policy
        self.findings: List[ProjectionFinding] = []
        self.loss_entries: List[LossEntry] = []
        self.nodes = 0
        self.active_container_ids: set[int] = set()

    def finding(self, code: str, location: str, action: str) -> None:
        self.findings.append(
            ProjectionFinding(code=code, location=location, action=action)
        )
        self.loss_entries.append(
            LossEntry(
                code=code,
                scope=location,
                consequence="projection_not_exact",
            )
        )

    def project(self, value: Any, *, depth: int = 0, location: str = "$") -> Any:
        self.nodes += 1
        if self.nodes > self.limits.max_total_nodes:
            self.finding("total_node_limit", location, "omitted")
            return OMITTED
        if depth > self.limits.max_depth:
            self.finding("depth_limit", location, "omitted")
            return OMITTED

        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            value = {
                item.name: getattr(value, item.name)
                for item in dataclasses.fields(value)
            }
        elif isinstance(value, Enum):
            return self.project(value.value, depth=depth, location=location)
        elif isinstance(value, Path):
            self.finding("host_path", location, "redacted")
            return REDACTED

        if isinstance(value, Mapping):
            container_id = id(value)
            if container_id in self.active_container_ids:
                self.finding("cyclic_object", location, "omitted")
                self.finding("depth_limit", location, "omitted")
                return OMITTED
            self.active_container_ids.add(container_id)
            output: Dict[str, Any] = {}
            items = list(
                islice(value.items(), self.limits.max_mapping_items + 1)
            )
            if len(items) > self.limits.max_mapping_items:
                self.finding("mapping_item_limit", location, "truncated")
                items = items[: self.limits.max_mapping_items]
            for index, (key, item) in enumerate(items):
                safe_location = f"{location}.field[{index}]"
                key_text = str(key)
                if self.view != PrivacyView.RAW_PRIVATE:
                    unsafe_key_code = _unsafe_string_code(key_text)
                    if unsafe_key_code is not None:
                        key_text = f"__redacted_field_{index}__"
                        self.finding(
                            unsafe_key_code,
                            safe_location,
                            "key_redacted",
                        )
                if self.view != PrivacyView.RAW_PRIVATE and _sensitive_key(key):
                    output[key_text] = REDACTED
                    self.finding("sensitive_key", safe_location, "redacted")
                    continue
                if self.view != PrivacyView.RAW_PRIVATE and _provider_raw_key(key):
                    if self.provider_raw_policy == ProviderRawPolicy.OMIT:
                        output[key_text] = OMITTED
                        self.finding(
                            "provider_raw_payload", safe_location, "omitted"
                        )
                        continue
                    if self.provider_raw_policy == ProviderRawPolicy.REFERENCE_ONLY:
                        output[key_text] = {"type": "provider_raw", "value": OMITTED}
                        self.finding(
                            "provider_raw_payload", safe_location, "reference_required"
                        )
                        continue
                if self.view != PrivacyView.RAW_PRIVATE and _artifact_body_key(key):
                    output[key_text] = OMITTED
                    self.finding("artifact_body", safe_location, "omitted")
                    continue
                output[key_text] = self.project(
                    item,
                    depth=depth + 1,
                    location=safe_location,
                )
            self.active_container_ids.discard(container_id)
            return output

        if isinstance(value, (list, tuple, set, frozenset)):
            container_id = id(value)
            if container_id in self.active_container_ids:
                self.finding("cyclic_object", location, "omitted")
                self.finding("depth_limit", location, "omitted")
                return OMITTED
            self.active_container_ids.add(container_id)
            items = list(islice(iter(value), self.limits.max_sequence_items + 1))
            if len(items) > self.limits.max_sequence_items:
                self.finding("sequence_item_limit", location, "truncated")
                items = items[: self.limits.max_sequence_items]
            sequence_output = [
                self.project(
                    item,
                    depth=depth + 1,
                    location=f"{location}.item[{index}]",
                )
                for index, item in enumerate(items)
            ]
            self.active_container_ids.discard(container_id)
            return sequence_output

        if isinstance(value, str):
            if self.view != PrivacyView.RAW_PRIVATE:
                unsafe_code = _unsafe_string_code(value)
                if unsafe_code is not None:
                    self.finding(unsafe_code, location, "redacted")
                    return REDACTED
            if (
                self.view != PrivacyView.RAW_PRIVATE
                and len(value) > self.limits.max_string_chars
            ):
                self.finding("string_length_limit", location, "truncated")
                return value[: self.limits.max_string_chars] + "…"
            return value

        if isinstance(value, (int, float, bool)) or value is None:
            return value

        if self.view == PrivacyView.RAW_PRIVATE:
            return _json_ready(value, private=True)
        self.finding("unsupported_object", location, "omitted")
        return _json_ready(value, private=False)


def project_data(
    value: Any,
    *,
    view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    limits: Optional[ProjectionLimits] = None,
    provider_raw_policy: Optional[ProviderRawPolicy] = None,
) -> ProjectionResult:
    """Project data without mutating the canonical input.

    Findings contain only low-cardinality codes and positional locations.  A
    rejected key or value is never echoed into diagnostics.
    """
    effective_limits = limits or (
        ProjectionLimits(
            max_depth=6,
            max_mapping_items=64,
            max_sequence_items=64,
            max_string_chars=2_048,
            max_total_nodes=4_096,
        )
        if view == PrivacyView.SAFE_DIAGNOSTIC
        else ProjectionLimits()
    )
    effective_raw_policy = provider_raw_policy or (
        ProviderRawPolicy.OMIT
        if view == PrivacyView.SAFE_DIAGNOSTIC
        else ProviderRawPolicy.REFERENCE_ONLY
    )
    projector = _Projector(view, effective_limits, effective_raw_policy)
    data = projector.project(value)
    return ProjectionResult(
        data=data,
        view=view,
        findings=tuple(projector.findings),
        loss=LossReport(
            policy_id=f"qitos.projection/{view.value}",
            entries=tuple(projector.loss_entries),
        ),
    )


def portability_finding_codes(value: Any) -> Tuple[str, ...]:
    """Return non-echoing portability/privacy finding codes for public data."""
    result = project_data(value, view=PrivacyView.REDACTED_PUBLIC)
    return tuple(dict.fromkeys(finding.code for finding in result.findings))


__all__ = [
    "OMITTED",
    "REDACTED",
    "ProjectionFinding",
    "ProjectionLimits",
    "ProjectionResult",
    "ProviderRawPolicy",
    "portability_finding_codes",
    "project_data",
]

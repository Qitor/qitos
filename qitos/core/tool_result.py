"""Canonical action/tool outcome and its explicitly separated projections."""

from __future__ import annotations

import json
import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Mapping, TYPE_CHECKING

from .artifact import ArtifactContractError, ArtifactRef
from .diagnostics import (
    _diagnostic_key_is_secret,
    _diagnostic_key_is_sensitive,
    _diagnostic_string_categories,
)
from .session import AttemptIdentity, SnapshotComponentCodec

if TYPE_CHECKING:
    from .action import ActionResult

ToolResultStatus = Literal["success", "error", "skipped", "timed_out", "cancelled"]
ToolErrorKind = Literal["semantic", "execution", "policy"]
EffectState = Literal[
    "no_effect_declared",
    "not_started",
    "started",
    "committed",
    "rejected",
    "unknown",
    "reconciliation_required",
]
RetryDisposition = Literal[
    "not_evaluated",
    "retryable",
    "non_retryable",
    "blocked_worker_running",
    "requires_reconciliation",
]
_ProjectionRole = Literal["content", "omission_counts"]

HISTORICAL_TOOL_RESULT_SCHEMA_VERSION = "qitos.tool_result/v1"
TOOL_RESULT_SCHEMA_VERSION = "qitos.tool_result/v2"
TOOL_RESULT_MODEL_VIEW_VERSION = "qitos.tool_result.model_view/v1"
TOOL_RESULT_TRACE_SAFE_VERSION = "qitos.tool_result.trace_safe/v1"
TOOL_BATCH_CLOSURE_SCHEMA_VERSION = "qitos.tool_batch_closure/v1"
TOOL_EFFECTS_COMPONENT_SCHEMA_VERSION = "qitos.tool_effects_component/v1"

_STATUSES = frozenset({"success", "error", "skipped", "timed_out", "cancelled"})
_ERROR_KINDS = frozenset({"semantic", "execution", "policy"})
_EFFECT_STATES = frozenset(
    {
        "no_effect_declared",
        "not_started",
        "started",
        "committed",
        "rejected",
        "unknown",
        "reconciliation_required",
    }
)
_RETRY_DISPOSITIONS = frozenset(
    {
        "not_evaluated",
        "retryable",
        "non_retryable",
        "blocked_worker_running",
        "requires_reconciliation",
    }
)
_HISTORICAL_FIELDS = frozenset(
    {
        "schema_version", "status", "success", "tool_name", "action_id",
        "output", "model_output", "error", "error_kind", "error_code",
        "recoverable", "recovery_hint", "next_action", "complete", "truncated",
        "omitted", "attempts", "latency_ms", "declared_effects",
        "filesystem_changes", "artifact_refs", "normalized_request", "provenance",
        "worker_still_running", "metadata",
    }
)
_CURRENT_FIELDS = frozenset(
    {
        "schema_version", "status", "success", "tool_name", "action_id",
        "output", "model_output", "error", "error_kind", "error_code",
        "recoverable", "recovery_hint", "next_action", "complete", "truncated",
        "omitted", "attempts", "latency_ms", "declared_effects",
        "filesystem_changes", "artifact_refs", "normalized_request", "provenance",
        "worker_still_running", "metadata",
        "attempt_id", "effect_ref", "effect_state", "idempotency_ref",
        "retry_disposition", "reconciliation_required", "outcome_unknown",
        "late_result", "owner_generation", "stale_owner", "batch_closure",
    }
)
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BATCH_SLOT_STATES = frozenset(
    {"open", "success", "error", "skipped", "timed_out", "cancelled"}
)


class ToolResultContractError(ValueError):
    """Typed canonical serialization/parse boundary failure."""

    def __init__(self, code: str, message: str):
        self.code = str(code)
        super().__init__(f"{self.code}: {message}")


def _fail(code: str, message: str) -> ToolResultContractError:
    return ToolResultContractError(code, message)


def _legacy_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _legacy_dict_list(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _legacy_optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _legacy_non_negative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _legacy_effect_state(value: Any) -> EffectState:
    return value if isinstance(value, str) and value in _EFFECT_STATES else "no_effect_declared"  # type: ignore[return-value]


def _legacy_retry_disposition(
    value: Any,
    *,
    status: Any,
    recoverable: bool,
    worker_still_running: bool,
) -> RetryDisposition:
    _ = status, recoverable, worker_still_running
    if isinstance(value, str) and value in _RETRY_DISPOSITIONS:
        return value  # type: ignore[return-value]
    return "not_evaluated"


def _model_projection(output: Any, explicit: Any = None) -> Any:
    if explicit is not None:
        return explicit
    if isinstance(output, Mapping):
        summary = output.get("model_summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    return None


def _require_json(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _fail("non_serializable_value", f"{path} must be finite")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _fail("non_serializable_value", f"{path} keys must be strings")
            _require_json(item, f"{path}.{key}")
        return
    raise _fail(
        "non_serializable_value",
        f"{path} contains non-JSON value {type(value).__name__}",
    )


def _clone_json(value: Any, path: str) -> Any:
    """Validate and recursively detach one JSON tree from caller ownership."""

    _require_json(value, path)
    if isinstance(value, list):
        return [_clone_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        return {
            key: _clone_json(item, f"{path}.{key}")
            for key, item in value.items()
        }
    return value


def _require_optional_string(value: Any, path: str) -> None:
    if value is not None and not isinstance(value, str):
        raise _fail("invalid_canonical_field", f"{path} must be a string or null")


def _validate_next_action(value: Any) -> Dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _fail("invalid_canonical_field", "next_action must be an object")
    unknown = sorted(set(value) - {"name", "args", "action_id"})
    if unknown:
        raise _fail("invalid_canonical_field", f"next_action has unknown field {unknown[0]!r}")
    name, args, action_id = value.get("name"), value.get("args", {}), value.get("action_id")
    if not isinstance(name, str) or not name.strip():
        raise _fail("invalid_canonical_field", "next_action.name must be a non-empty string")
    if not isinstance(args, dict):
        raise _fail("invalid_canonical_field", "next_action.args must be an object")
    if action_id is not None and not isinstance(action_id, str):
        raise _fail("invalid_canonical_field", "next_action.action_id must be a string")
    result: Dict[str, Any] = {"name": name.strip(), "args": args}
    if action_id is not None:
        result["action_id"] = action_id
    return _clone_json(result, "next_action")


def _validate_dict(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail("invalid_canonical_field", f"{path} must be an object")
    return _clone_json(value, path)


def _validate_dict_list(value: Any, path: str) -> list[Dict[str, Any]]:
    if not isinstance(value, list):
        raise _fail("invalid_canonical_field", f"{path} must be an array")
    result: list[Dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _fail("invalid_canonical_field", f"{path}[{index}] must be an object")
        result.append(_validate_dict(item, f"{path}[{index}]"))
    return result


def _validate_artifacts(value: Any) -> tuple[ArtifactRef, ...]:
    if not isinstance(value, (list, tuple)):
        raise _fail("invalid_artifact_ref", "artifact_refs must be an array")
    if any(not isinstance(item, ArtifactRef) for item in value):
        raise _fail("invalid_artifact_ref", "artifact_refs must use canonical ArtifactRef values")
    refs = tuple(value)
    if len({item.artifact_id for item in refs}) != len(refs):
        raise _fail("invalid_artifact_ref", "artifact_refs must be unique")
    return refs


def _legacy_artifact_ref(value: Any) -> ArtifactRef:
    if not isinstance(value, Mapping):
        raise _fail("invalid_artifact_ref", "historical artifact reference must be an object")
    raw_id = value.get("artifact_id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise _fail("invalid_artifact_ref", "historical artifact identity is invalid")
    fingerprint = hashlib.sha256(
        json.dumps(dict(value), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    declared_digest = raw_id.removeprefix("sha256:")
    sha256 = declared_digest if re.fullmatch(r"[0-9a-f]{64}", declared_digest) else fingerprint
    try:
        return ArtifactRef(
            artifact_id=raw_id,
            resolver_key=f"legacy-artifact:{fingerprint[:32]}",
            sha256=sha256,
            media_type=str(value.get("media_type") or "application/octet-stream"),
            byte_length=(
                value["byte_length"]
                if isinstance(value.get("byte_length"), int)
                and not isinstance(value.get("byte_length"), bool)
                and value["byte_length"] >= 0
                else 0
            ),
            encoding=str(value.get("encoding") or "binary"),
            sensitivity=str(value.get("sensitivity") or "internal"),
            required=False,
        )
    except ArtifactContractError as exc:
        raise _fail("invalid_artifact_ref", "historical artifact reference is unsafe") from exc


def _legacy_artifact_refs(value: Any) -> tuple[ArtifactRef, ...]:
    if value in (None, []):
        return ()
    if not isinstance(value, list):
        raise _fail("invalid_artifact_ref", "historical artifact_refs must be an array")
    return tuple(_legacy_artifact_ref(item) for item in value)


def _legacy_attempt_identity(value: Any) -> AttemptIdentity | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        try:
            return AttemptIdentity.from_dict(value)
        except Exception as exc:
            raise _fail("invalid_attempt_identity", "attempt identity is invalid") from exc
    if not isinstance(value, str) or not value:
        raise _fail("invalid_attempt_identity", "attempt identity is invalid")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return AttemptIdentity(f"attempt_{digest}")


def _validate_batch_closure(value: Any) -> Dict[str, Any]:
    closure = _validate_dict(value, "batch_closure")
    if not closure:
        return {}
    allowed = {"schema_version", "batch_id", "slots"}
    unknown = sorted(set(closure) - allowed)
    if unknown:
        raise _fail(
            "invalid_batch_closure",
            f"batch_closure has unknown field {unknown[0]!r}",
        )
    if closure.get("schema_version") != TOOL_BATCH_CLOSURE_SCHEMA_VERSION:
        raise _fail(
            "invalid_batch_closure",
            "batch_closure has an unsupported schema_version",
        )
    batch_id = closure.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise _fail("invalid_batch_closure", "batch_closure.batch_id must be non-empty")
    slots = closure.get("slots")
    if not isinstance(slots, list) or not slots:
        raise _fail("invalid_batch_closure", "batch_closure.slots must be non-empty")
    seen: set[str] = set()
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            raise _fail(
                "invalid_batch_closure",
                f"batch_closure.slots[{index}] must be an object",
            )
        unknown_slot = sorted(set(slot) - {"action_id", "state", "result_ref", "attempt_id"})
        if unknown_slot:
            raise _fail(
                "invalid_batch_closure",
                f"batch_closure.slots[{index}] has unknown field {unknown_slot[0]!r}",
            )
        action_id = slot.get("action_id")
        state = slot.get("state")
        if not isinstance(action_id, str) or not action_id.strip():
            raise _fail(
                "invalid_batch_closure",
                f"batch_closure.slots[{index}].action_id must be non-empty",
            )
        if action_id in seen:
            raise _fail("invalid_batch_closure", f"duplicate batch action_id {action_id!r}")
        seen.add(action_id)
        if not isinstance(state, str) or state not in _BATCH_SLOT_STATES:
            raise _fail(
                "invalid_batch_closure",
                f"batch_closure.slots[{index}].state is invalid",
            )
        if "result_ref" in slot and not isinstance(slot["result_ref"], str):
            raise _fail(
                "invalid_batch_closure",
                f"batch_closure.slots[{index}].result_ref must be a string",
            )
        if "attempt_id" in slot:
            try:
                attempt = AttemptIdentity.from_dict(slot["attempt_id"])
            except Exception as exc:
                raise _fail(
                    "invalid_batch_closure",
                    f"batch_closure.slots[{index}].attempt_id must be a typed identity",
                ) from exc
            slot["attempt_id"] = attempt.to_dict()
    return closure


def _new_facts() -> Dict[str, int]:
    return {
        "secret_values": 0,
        "host_paths": 0,
        "non_json_values": 0,
        "redacted_identifiers": 0,
        "redacted_keys": 0,
        "omitted_characters": 0,
        "omitted_fields": 0,
    }


def _merge_facts(target: Dict[str, int], source: Dict[str, int]) -> None:
    for key in target:
        target[key] += source.get(key, 0)


def _redact_text(value: str, facts: Dict[str, int]) -> str:
    categories = _diagnostic_string_categories(value)
    has_path = bool(categories & {
        "absolute_posix_path",
        "windows_path",
        "windows_unc_path",
        "file_uri",
        "home_path",
        "local_endpoint",
    })
    if has_path:
        facts["host_paths"] += 1
    if "secret" in categories:
        facts["secret_values"] += 1
    if has_path:
        return "[REDACTED_PATH]"
    if categories:
        return "[REDACTED]"
    return value


def _safe_identifier(value: str | None, facts: Dict[str, int]) -> str | None:
    if value is None:
        return None
    redacted = _redact_text(value, facts)
    if redacted == value and _SAFE_IDENTIFIER.fullmatch(value):
        return value
    facts["redacted_identifiers"] += 1
    return "[REDACTED_IDENTIFIER]"


def _mapping_key_is_sensitive(value: str) -> bool:
    return _diagnostic_key_is_sensitive(value)


def _redact_value(
    value: Any,
    facts: Dict[str, int],
    *,
    force_secret: bool = False,
    role: _ProjectionRole = "content",
) -> Any:
    if isinstance(value, str):
        redacted = _redact_text(value, facts)
        if force_secret and redacted == value:
            facts["secret_values"] += 1
            return "[REDACTED]"
        return redacted
    if isinstance(value, list):
        return [
            _redact_value(
                item,
                facts,
                force_secret=force_secret,
                role=role,
            )
            for item in value
        ]
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        reserved = {str(key) for key in value}
        sensitive_keys = sorted(
            key for key in reserved if _mapping_key_is_sensitive(key)
        )
        placeholders: Dict[str, str] = {}
        placeholder_index = 1
        for key in sensitive_keys:
            while True:
                candidate = f"[REDACTED_KEY_{placeholder_index}]"
                placeholder_index += 1
                if candidate not in reserved and candidate not in placeholders.values():
                    placeholders[key] = candidate
                    break
        for raw_key, item in value.items():
            key = str(raw_key)
            secret_count = facts["secret_values"]
            redacted_key_text = _redact_text(key, facts)
            sensitive_name = _diagnostic_key_is_secret(key)
            sensitive_key = sensitive_name or redacted_key_text != key
            if sensitive_key:
                if sensitive_name and facts["secret_values"] == secret_count:
                    facts["secret_values"] += 1
                facts["redacted_keys"] += 1
                safe_key = placeholders[key]
            else:
                safe_key = key
            result[safe_key] = _redact_value(
                item,
                facts,
                force_secret=force_secret or sensitive_name,
                role=role,
            )
        return result
    if value is None or isinstance(value, (bool, int, float)):
        if force_secret and role == "content":
            facts["secret_values"] += 1
            return "[REDACTED]"
        return value
    facts["non_json_values"] += 1
    return f"[REDACTED_{type(value).__name__.upper()}]"


def _projection_text(value: Any, facts: Dict[str, int]) -> str:
    safe = _redact_value(value, facts)
    if isinstance(safe, str):
        return safe
    return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bounded_text(value: str, max_chars: int, facts: Dict[str, int]) -> str:
    budget = max(0, int(max_chars))
    if len(value) <= budget:
        return value
    facts["omitted_characters"] += len(value) - budget
    marker = "...[TRUNCATED]"
    if budget <= len(marker):
        return marker[:budget]
    return value[: budget - len(marker)] + marker


def _bounded_mapping(
    value: Mapping[str, Any], max_chars: int, facts: Dict[str, int]
) -> Dict[str, Any]:
    """Redact a mapping and retain entries that fit one deterministic budget."""

    safe = _redact_value(dict(value), facts, role="omission_counts")
    if not isinstance(safe, dict):  # Defensive: callers provide a mapping.
        facts["omitted_fields"] += 1
        return {}
    budget = max(0, int(max_chars))
    result: Dict[str, Any] = {}
    for key in sorted(safe):
        item = safe[key]
        candidate = dict(result)
        candidate[key] = item
        rendered = json.dumps(
            candidate,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if budget > 0 and len(rendered) <= budget:
            result = candidate
            continue
        facts["omitted_fields"] += 1
        entry_text = json.dumps(
            {key: item},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        facts["omitted_characters"] += max(0, len(entry_text) - 2)
    return result


@dataclass
class ToolResult:
    """Lossless terminal outcome for one declared action/tool slot."""

    status: ToolResultStatus = "success"
    output: Any = None
    error: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_name: str | None = None
    action_id: str | None = None
    model_output: Any = None
    error_kind: ToolErrorKind | None = None
    error_code: str | None = None
    recoverable: bool = False
    recovery_hint: str | None = None
    next_action: Dict[str, Any] | None = None
    complete: bool = True
    truncated: bool = False
    omitted: Dict[str, int] = field(default_factory=dict)
    attempts: int = 1
    latency_ms: float = 0.0
    declared_effects: list[Dict[str, Any]] = field(default_factory=list)
    filesystem_changes: list[Dict[str, Any]] = field(default_factory=list)
    artifact_refs: tuple[ArtifactRef, ...] = ()
    normalized_request: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    worker_still_running: bool = False
    attempt_id: AttemptIdentity | None = None
    effect_ref: str | None = None
    effect_state: EffectState = "no_effect_declared"
    idempotency_ref: str | None = None
    retry_disposition: RetryDisposition = "not_evaluated"
    reconciliation_required: bool = False
    outcome_unknown: bool = False
    late_result: bool = False
    owner_generation: int | None = None
    stale_owner: bool = False
    batch_closure: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = TOOL_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOL_RESULT_SCHEMA_VERSION:
            raise _fail("unknown_schema_version", f"unsupported schema version: {self.schema_version!r}")
        if not isinstance(self.status, str) or self.status not in _STATUSES:
            raise _fail("invalid_terminal_status", f"unsupported status: {self.status!r}")
        if self.error_kind is not None and self.error_kind not in _ERROR_KINDS:
            raise _fail("invalid_error_kind", f"unsupported error_kind: {self.error_kind!r}")
        if not isinstance(self.effect_state, str) or self.effect_state not in _EFFECT_STATES:
            raise _fail("invalid_effect_state", f"unsupported effect_state: {self.effect_state!r}")
        if (
            not isinstance(self.retry_disposition, str)
            or self.retry_disposition not in _RETRY_DISPOSITIONS
        ):
            raise _fail(
                "invalid_retry_disposition",
                f"unsupported retry_disposition: {self.retry_disposition!r}",
            )
        for path, value in (
            ("tool_name", self.tool_name), ("action_id", self.action_id),
            ("error", self.error), ("error_code", self.error_code),
            ("recovery_hint", self.recovery_hint),
            ("effect_ref", self.effect_ref),
            ("idempotency_ref", self.idempotency_ref),
        ):
            _require_optional_string(value, path)
        if self.attempt_id is not None and not isinstance(
            self.attempt_id, AttemptIdentity
        ):
            raise _fail(
                "invalid_attempt_identity",
                "attempt_id must use the canonical AttemptIdentity type",
            )
        for bool_path, bool_value in (
            ("recoverable", self.recoverable), ("complete", self.complete),
            ("truncated", self.truncated), ("worker_still_running", self.worker_still_running),
            ("reconciliation_required", self.reconciliation_required),
            ("outcome_unknown", self.outcome_unknown),
            ("late_result", self.late_result), ("stale_owner", self.stale_owner),
        ):
            if not isinstance(bool_value, bool):
                raise _fail("invalid_canonical_field", f"{bool_path} must be boolean")
        if not isinstance(self.attempts, int) or isinstance(self.attempts, bool) or self.attempts < 0:
            raise _fail("invalid_canonical_field", "attempts must be a non-negative integer")
        if (
            not isinstance(self.latency_ms, (int, float)) or isinstance(self.latency_ms, bool)
            or not math.isfinite(float(self.latency_ms)) or self.latency_ms < 0
        ):
            raise _fail("invalid_canonical_field", "latency_ms must be a finite non-negative number")
        if self.owner_generation is not None and (
            not isinstance(self.owner_generation, int)
            or isinstance(self.owner_generation, bool)
            or self.owner_generation < 0
        ):
            raise _fail(
                "invalid_canonical_field",
                "owner_generation must be a non-negative integer or null",
            )
        if not isinstance(self.omitted, dict):
            raise _fail("invalid_canonical_field", "omitted must be an object")
        for key, count in self.omitted.items():
            if not isinstance(key, str) or not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise _fail("invalid_canonical_field", "omitted values must be non-negative integers")
        self.next_action = _validate_next_action(self.next_action)
        self.metadata = _validate_dict(self.metadata, "metadata")
        self.omitted = dict(self.omitted)
        self.declared_effects = _validate_dict_list(self.declared_effects, "declared_effects")
        self.filesystem_changes = _validate_dict_list(self.filesystem_changes, "filesystem_changes")
        self.artifact_refs = _validate_artifacts(self.artifact_refs)
        self.normalized_request = _validate_dict(self.normalized_request, "normalized_request")
        self.provenance = _validate_dict(self.provenance, "provenance")
        self.batch_closure = _validate_batch_closure(self.batch_closure)
        projected = _model_projection(self.output, self.model_output)
        self.output = _clone_json(self.output, "output")
        self.model_output = _clone_json(projected, "model_output")
        self._validate_terminal_invariants()
        self._validate_recovery_invariants()

    def _validate_terminal_invariants(self) -> None:
        if self.status == "success":
            if self.error is not None or self.error_kind is not None or self.error_code is not None:
                raise _fail("contradictory_outcome", "success cannot carry error fields")
            if self.worker_still_running:
                raise _fail("contradictory_outcome", "success cannot have a running worker")
            return
        if self.error_kind is None or not isinstance(self.error_code, str) or not self.error_code:
            raise _fail("contradictory_outcome", f"{self.status} requires error_kind and error_code")
        if self.status == "skipped" and self.error_kind != "policy":
            raise _fail("contradictory_outcome", "skipped requires policy error_kind")
        if self.status in {"timed_out", "cancelled"} and self.error_kind != "execution":
            raise _fail("contradictory_outcome", f"{self.status} requires execution error_kind")
        if self.worker_still_running and self.status not in {"timed_out", "cancelled"}:
            raise _fail(
                "contradictory_outcome",
                "worker_still_running is valid only for timed_out or cancelled",
            )

    def _validate_recovery_invariants(self) -> None:
        if self.effect_state == "no_effect_declared" and self.effect_ref is not None:
            raise _fail(
                "contradictory_effect",
                "no_effect_declared cannot carry effect_ref",
            )
        if self.effect_state != "no_effect_declared" and not self.effect_ref:
            raise _fail(
                "contradictory_effect",
                f"{self.effect_state} requires effect_ref",
            )
        if self.effect_state == "unknown" and not self.outcome_unknown:
            raise _fail("contradictory_effect", "unknown effect requires outcome_unknown")
        if self.effect_state == "reconciliation_required" and not (
            self.outcome_unknown and self.reconciliation_required
        ):
            raise _fail(
                "contradictory_effect",
                "reconciliation_required effect requires both uncertainty flags",
            )
        if self.reconciliation_required and self.effect_state not in {
            "unknown",
            "reconciliation_required",
        }:
            raise _fail(
                "contradictory_effect",
                "reconciliation_required needs an unknown effect state",
            )
        if self.outcome_unknown and self.effect_state not in {
            "started",
            "unknown",
            "reconciliation_required",
        }:
            raise _fail(
                "contradictory_effect",
                "outcome_unknown requires a started or unknown effect",
            )
        if self.retry_disposition == "retryable" and (
            not self.recoverable
            or self.worker_still_running
            or self.outcome_unknown
            or self.effect_state == "committed"
        ):
            raise _fail(
                "unsafe_retry_disposition",
                "retryable requires recoverable, settled, non-committed work",
            )
        if (
            self.retry_disposition == "blocked_worker_running"
            and not self.worker_still_running
        ):
            raise _fail(
                "unsafe_retry_disposition",
                "blocked_worker_running requires a continuing worker",
            )
        if self.retry_disposition == "requires_reconciliation" and not (
            self.outcome_unknown or self.reconciliation_required
        ):
            raise _fail(
                "unsafe_retry_disposition",
                "requires_reconciliation needs outcome uncertainty",
            )

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    @property
    def text(self) -> str:
        if isinstance(self.output, str):
            return self.output
        return json.dumps(self.output, ensure_ascii=False, sort_keys=True)

    @property
    def model_text(self) -> str:
        visible = self.model_output if self.model_output is not None else self.output
        return _projection_text(visible, _new_facts())

    def to_persistence_dict(self) -> Dict[str, Any]:
        """Serialize the complete current grammar without legacy flattening."""
        self.__post_init__()
        payload: Dict[str, Any] = {
            "schema_version": TOOL_RESULT_SCHEMA_VERSION, "status": self.status,
            "success": self.is_success, "tool_name": self.tool_name,
            "action_id": self.action_id,
            "output": _clone_json(self.output, "output"),
            "model_output": _clone_json(self.model_output, "model_output"),
            "error": self.error,
            "error_kind": self.error_kind, "error_code": self.error_code,
            "recoverable": self.recoverable, "recovery_hint": self.recovery_hint,
            "next_action": (
                _clone_json(self.next_action, "next_action")
                if self.next_action is not None else None
            ),
            "complete": self.complete, "truncated": self.truncated,
            "omitted": _clone_json(self.omitted, "omitted"),
            "attempts": self.attempts,
            "latency_ms": self.latency_ms,
            "declared_effects": _clone_json(self.declared_effects, "declared_effects"),
            "filesystem_changes": _clone_json(
                self.filesystem_changes, "filesystem_changes"
            ),
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "normalized_request": _clone_json(
                self.normalized_request, "normalized_request"
            ),
            "provenance": _clone_json(self.provenance, "provenance"),
            "worker_still_running": self.worker_still_running,
            "attempt_id": self.attempt_id.to_dict() if self.attempt_id else None,
            "effect_ref": self.effect_ref,
            "effect_state": self.effect_state,
            "idempotency_ref": self.idempotency_ref,
            "retry_disposition": self.retry_disposition,
            "reconciliation_required": self.reconciliation_required,
            "outcome_unknown": self.outcome_unknown,
            "late_result": self.late_result,
            "owner_generation": self.owner_generation,
            "stale_owner": self.stale_owner,
            "batch_closure": _clone_json(self.batch_closure, "batch_closure"),
            "metadata": _clone_json(self.metadata, "metadata"),
        }
        _require_json(payload, "ToolResult")
        return payload

    def to_dict(self) -> Dict[str, Any]:
        return self.to_persistence_dict()

    def to_legacy_dict(self, *, flatten_output: bool = True) -> Dict[str, Any]:
        payload = self.to_persistence_dict()
        if flatten_output and isinstance(self.output, dict):
            for key, value in self.output.items():
                payload.setdefault(str(key), _clone_json(value, f"output.{key}"))
        return payload

    def _model_view_with_loss(
        self, max_chars: int
    ) -> tuple[Dict[str, Any], Dict[str, Any], int]:
        """Build one bounded view and aggregate loss across every visible field."""

        self.__post_init__()
        budget = max(0, int(max_chars))
        totals = _new_facts()
        by_field: Dict[str, Dict[str, int]] = {}

        def facts_for(field_name: str) -> Dict[str, int]:
            facts = _new_facts()
            by_field[field_name] = facts
            return facts

        output_facts = facts_for("model_output")
        source = self.model_output
        if source is None:
            source = self.output if self.output is not None else self.error or ""
        model_text = _bounded_text(
            _projection_text(source, output_facts), budget, output_facts
        )
        remaining = max(0, budget - len(model_text))

        error_facts = facts_for("error")
        safe_error = None
        if self.error is not None:
            if remaining > 0:
                safe_error = _bounded_text(
                    _redact_text(self.error, error_facts), remaining, error_facts
                )
                remaining = max(0, remaining - len(safe_error))
            else:
                error_facts["omitted_characters"] += len(self.error)
                error_facts["omitted_fields"] += 1

        hint_facts = facts_for("recovery_hint")
        safe_hint = None
        if self.recovery_hint is not None:
            if remaining > 0:
                safe_hint = _bounded_text(
                    _redact_text(self.recovery_hint, hint_facts),
                    remaining,
                    hint_facts,
                )
                remaining = max(0, remaining - len(safe_hint))
            else:
                hint_facts["omitted_characters"] += len(self.recovery_hint)
                hint_facts["omitted_fields"] += 1

        identity_facts = facts_for("identifiers")
        safe_tool_name = _safe_identifier(self.tool_name, identity_facts)
        safe_action_id = _safe_identifier(self.action_id, identity_facts)
        safe_error_code = _safe_identifier(self.error_code, identity_facts)

        action_facts = facts_for("next_action")
        safe_next_action = None
        if self.next_action is not None:
            safe_next_action = {
                "name": _safe_identifier(self.next_action["name"], action_facts),
                "args": _redact_value(self.next_action.get("args", {}), action_facts),
            }
            if self.next_action.get("action_id") is not None:
                safe_next_action["action_id"] = _safe_identifier(
                    self.next_action["action_id"], action_facts
                )
            rendered_action = json.dumps(
                safe_next_action,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if len(rendered_action) > remaining:
                action_facts["omitted_characters"] += len(rendered_action)
                action_facts["omitted_fields"] += 1
                safe_next_action = None
            else:
                remaining = max(0, remaining - len(rendered_action))

        for facts in by_field.values():
            _merge_facts(totals, facts)
        payload: Dict[str, Any] = {
            "schema_version": TOOL_RESULT_MODEL_VIEW_VERSION,
            "status": self.status,
            "tool_name": safe_tool_name,
            "action_id": safe_action_id,
            "model_output": model_text,
            "error": safe_error,
            "error_code": safe_error_code,
            "recoverable": self.recoverable,
            "recovery_hint": safe_hint,
            "next_action": safe_next_action,
        }
        _require_json(payload, "model_view")
        return payload, {"totals": totals, "fields": by_field}, remaining

    def to_model_dict(self, *, max_chars: int = 4000) -> Dict[str, Any]:
        """Return the allowlist view permitted in model messages."""
        payload, projection_loss, _ = self._model_view_with_loss(max_chars)
        totals = projection_loss["totals"]
        payload["projection_loss"] = {
            "truncated": bool(totals["omitted_characters"]),
            "omitted_characters": int(totals["omitted_characters"]),
            "omitted_fields": int(totals["omitted_fields"]),
            "redacted_values": int(totals["secret_values"]),
            "redacted_locations": int(totals["host_paths"]),
            "redacted_non_json_values": int(totals["non_json_values"]),
        }
        _require_json(payload, "model_view")
        return payload

    def to_trace_safe_dict(self, *, max_chars: int = 4000) -> Dict[str, Any]:
        """Return the bounded ToolResult-only Lane D handoff projection."""
        payload, projection_loss, remaining = self._model_view_with_loss(max_chars)
        facts = projection_loss["totals"]
        omitted_facts = _new_facts()
        safe_omitted = _bounded_mapping(self.omitted, remaining, omitted_facts)
        projection_loss["fields"]["omitted"] = omitted_facts
        _merge_facts(facts, omitted_facts)
        recovery_facts = _new_facts()
        safe_attempt_id = (
            self.attempt_id.to_dict() if self.attempt_id is not None else None
        )
        safe_effect_ref = _safe_identifier(self.effect_ref, recovery_facts)
        safe_idempotency_ref = _safe_identifier(
            self.idempotency_ref, recovery_facts
        )
        safe_batch_closure = _redact_value(
            self.batch_closure, recovery_facts
        )
        _merge_facts(projection_loss["fields"]["identifiers"], recovery_facts)
        _merge_facts(facts, recovery_facts)
        excluded = [
            name for name, value in (
                ("output", self.output), ("metadata", self.metadata),
                ("normalized_request", self.normalized_request), ("provenance", self.provenance),
                ("declared_effects", self.declared_effects),
                ("filesystem_changes", self.filesystem_changes), ("artifact_refs", self.artifact_refs),
            ) if value not in (None, {}, [], ())
        ]
        payload.update(
            {
                "schema_version": TOOL_RESULT_TRACE_SAFE_VERSION,
                "complete": self.complete, "truncated": self.truncated,
                "omitted": safe_omitted, "attempts": self.attempts,
                "latency_ms": self.latency_ms,
                "worker_still_running": self.worker_still_running,
                "attempt_id": safe_attempt_id,
                "effect_ref": safe_effect_ref,
                "effect_state": self.effect_state,
                "idempotency_ref": safe_idempotency_ref,
                "retry_disposition": self.retry_disposition,
                "reconciliation_required": self.reconciliation_required,
                "outcome_unknown": self.outcome_unknown,
                "late_result": self.late_result,
                "owner_generation": self.owner_generation,
                "stale_owner": self.stale_owner,
                "batch_closure": safe_batch_closure,
                "loss": {
                    "canonical_output_included": False,
                    "excluded_fields": excluded,
                    "redacted_secret_values": facts["secret_values"],
                    "redacted_host_paths": facts["host_paths"],
                    "redacted_non_json_values": facts["non_json_values"],
                    "redacted_identifiers": facts["redacted_identifiers"],
                    "redacted_keys": facts["redacted_keys"],
                    "omitted_characters": facts["omitted_characters"],
                    "omitted_fields": facts["omitted_fields"],
                    "fields": projection_loss["fields"],
                },
            }
        )
        _require_json(payload, "trace_safe_view")
        return payload

    @classmethod
    def semantic_error(
        cls, *, code: str, error: str, output: Any = None, recoverable: bool = True,
        recovery_hint: str | None = None, next_action: Mapping[str, Any] | None = None,
        complete: bool = True, **kwargs: Any,
    ) -> "ToolResult":
        return cls(
            status="error", output=output, error=error, error_kind="semantic",
            error_code=code, recoverable=recoverable, recovery_hint=recovery_hint,
            next_action=dict(next_action) if next_action is not None else None,
            complete=complete, **kwargs,
        )

    @classmethod
    def execution_error(
        cls, *, code: str, error: str, output: Any = None, recoverable: bool = False,
        recovery_hint: str | None = None, **kwargs: Any,
    ) -> "ToolResult":
        return cls(
            status="error", output=output, error=error, error_kind="execution",
            error_code=code, recoverable=recoverable, recovery_hint=recovery_hint, **kwargs,
        )

    @classmethod
    def from_action_result(cls, payload: "ActionResult") -> "ToolResult":
        from .action import ActionResult
        if not isinstance(payload, ActionResult):
            raise TypeError("from_action_result() expects ActionResult")
        metadata = dict(payload.metadata or {})
        nested = payload.output if isinstance(payload.output, ToolResult) else None
        if nested is not None:
            return cls(
                status=nested.status, output=nested.output, error=nested.error,
                metadata={**metadata, **nested.metadata}, tool_name=nested.tool_name or payload.name,
                action_id=nested.action_id or payload.action_id, model_output=nested.model_output,
                error_kind=nested.error_kind, error_code=nested.error_code,
                recoverable=nested.recoverable, recovery_hint=nested.recovery_hint,
                next_action=nested.next_action, complete=nested.complete,
                truncated=nested.truncated, omitted=nested.omitted, attempts=payload.attempts,
                latency_ms=payload.latency_ms, declared_effects=nested.declared_effects,
                filesystem_changes=nested.filesystem_changes, artifact_refs=nested.artifact_refs,
                normalized_request=nested.normalized_request, provenance=nested.provenance,
                worker_still_running=nested.worker_still_running,
                attempt_id=nested.attempt_id, effect_ref=nested.effect_ref,
                effect_state=nested.effect_state,
                idempotency_ref=nested.idempotency_ref,
                retry_disposition=nested.retry_disposition,
                reconciliation_required=nested.reconciliation_required,
                outcome_unknown=nested.outcome_unknown,
                late_result=nested.late_result,
                owner_generation=nested.owner_generation,
                stale_owner=nested.stale_owner,
                batch_closure=nested.batch_closure,
            )
        status = str(getattr(payload.status, "value", payload.status))
        if status not in _STATUSES:
            status = "error"
        error_code = metadata.get("error_code") or metadata.get("error_category")
        error_kind: ToolErrorKind | None = None
        if status == "skipped":
            error_kind, error_code = "policy", error_code or "skipped"
        elif status != "success":
            declared_kind = metadata.get("error_kind")
            error_kind = (
                declared_kind if declared_kind in _ERROR_KINDS else "execution"
            )
            error_code = error_code or status
        return cls(
            status=status,  # type: ignore[arg-type]
            output=payload.output, error=payload.error, metadata=metadata,
            tool_name=payload.name, action_id=payload.action_id,
            model_output=_model_projection(payload.output, metadata.get("model_output")),
            error_kind=error_kind,
            error_code=str(error_code) if error_code not in (None, "") else None,
            recoverable=bool(metadata.get("recoverable", False)),
            recovery_hint=str(metadata["recovery_hint"]) if metadata.get("recovery_hint") not in (None, "") else None,
            next_action=metadata.get("next_action"), complete=bool(metadata.get("complete", True)),
            truncated=bool(metadata.get("truncated", False)), omitted=_legacy_dict(metadata.get("omitted")),
            attempts=payload.attempts, latency_ms=payload.latency_ms,
            declared_effects=_legacy_dict_list(metadata.get("declared_effects")),
            filesystem_changes=_legacy_dict_list(metadata.get("filesystem_changes")),
            artifact_refs=_legacy_artifact_refs(metadata.get("artifact_refs", metadata.get("artifacts"))),
            normalized_request=_legacy_dict(metadata.get("normalized_request")),
            provenance=_legacy_dict(metadata.get("provenance")),
            worker_still_running=bool(metadata.get("worker_still_running", False)),
            attempt_id=_legacy_attempt_identity(metadata.get("attempt_id")),
            effect_ref=_legacy_optional_string(metadata.get("effect_ref")),
            effect_state=_legacy_effect_state(metadata.get("effect_state")),
            idempotency_ref=_legacy_optional_string(metadata.get("idempotency_ref")),
            retry_disposition=_legacy_retry_disposition(
                metadata.get("retry_disposition"),
                status=status,
                recoverable=bool(metadata.get("recoverable", False)),
                worker_still_running=bool(metadata.get("worker_still_running", False)),
            ),
            reconciliation_required=bool(metadata.get("reconciliation_required", False)),
            outcome_unknown=bool(metadata.get("outcome_unknown", False)),
            late_result=bool(metadata.get("late_result", False)),
            owner_generation=_legacy_non_negative_int(metadata.get("owner_generation")),
            stale_owner=bool(metadata.get("stale_owner", False)),
            batch_closure=_legacy_dict(metadata.get("batch_closure")),
        )

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> "ToolResult":
        if not isinstance(payload, Mapping):
            raise _fail("invalid_canonical_payload", "canonical payload must be an object")
        data = dict(payload)
        version = data.get("schema_version")
        if version != TOOL_RESULT_SCHEMA_VERSION:
            raise _fail("unknown_schema_version", f"unsupported schema version: {version!r}")
        unknown = sorted(set(data) - _CURRENT_FIELDS)
        if unknown:
            raise _fail("unknown_canonical_field", "current payload has an unknown field")
        missing = sorted(_CURRENT_FIELDS - set(data))
        if missing:
            raise _fail(
                "missing_canonical_field",
                "current payload does not match the complete writer grammar",
            )
        success_present = "success" in data
        success = data.pop("success", None)
        raw_artifacts = data.get("artifact_refs", [])
        if not isinstance(raw_artifacts, list):
            raise _fail("invalid_artifact_ref", "artifact_refs must be an array")
        try:
            data["artifact_refs"] = tuple(
                ArtifactRef.from_dict(item) for item in raw_artifacts
            )
        except ArtifactContractError as exc:
            raise _fail("invalid_artifact_ref", "artifact reference is invalid") from exc
        raw_attempt = data.get("attempt_id")
        if raw_attempt is not None:
            try:
                data["attempt_id"] = AttemptIdentity.from_dict(raw_attempt)
            except Exception as exc:
                raise _fail("invalid_attempt_identity", "attempt identity is invalid") from exc
        result = cls(**data)  # type: ignore[arg-type]
        if success_present and (
            not isinstance(success, bool) or success != result.is_success
        ):
            raise _fail("contradictory_outcome", "success must exactly match terminal status")
        return result

    @classmethod
    def from_legacy_value(cls, payload: Any) -> "ToolResult":
        if isinstance(payload, ToolResult):
            return payload
        from .action import ActionResult
        if isinstance(payload, ActionResult):
            return cls.from_action_result(payload)
        if not isinstance(payload, Mapping):
            return cls(status="success", output=payload)
        data, metadata = dict(payload), _legacy_dict(payload.get("metadata"))
        raw_status = str(data.get("status") or "success")
        error = data.get("error")
        if error in (None, "") and raw_status in {"error", "failed"}:
            error = data.get("message")
        if raw_status not in _STATUSES:
            raw_status = "error" if error not in (None, "") else "success"
        if raw_status == "success" and error not in (None, ""):
            raw_status = "error"
        error_kind, error_code = data.get("error_kind"), data.get("error_code") or metadata.get("error_category")
        if raw_status == "success":
            error, error_kind, error_code = None, None, None
        elif raw_status == "skipped":
            error_kind, error_code = "policy", error_code or "skipped"
        elif raw_status in {"timed_out", "cancelled"}:
            error_kind, error_code = "execution", error_code or raw_status
        else:
            error_kind = error_kind if error_kind in _ERROR_KINDS else "execution"
            error_code = error_code or "legacy_error"
        output = data.get("output", data)
        return cls(
            status=raw_status,  # type: ignore[arg-type]
            output=output, error=str(error) if error not in (None, "") else None,
            metadata=metadata,
            tool_name=str(data["tool_name"]) if data.get("tool_name") not in (None, "") else metadata.get("tool_name"),
            action_id=str(data["action_id"]) if data.get("action_id") not in (None, "") else None,
            model_output=_model_projection(output, data.get("model_output")),
            error_kind=error_kind,  # type: ignore[arg-type]
            error_code=str(error_code) if error_code not in (None, "") else None,
            recoverable=bool(data.get("recoverable", metadata.get("recoverable", False))),
            recovery_hint=str(data["recovery_hint"]) if data.get("recovery_hint") not in (None, "") else None,
            next_action=data.get("next_action"), complete=bool(data.get("complete", True)),
            truncated=bool(data.get("truncated", False)), omitted=_legacy_dict(data.get("omitted")),
            attempts=int(data.get("attempts", metadata.get("attempts", 1))),
            latency_ms=float(data.get("latency_ms", metadata.get("latency_ms", 0.0))),
            declared_effects=_legacy_dict_list(data.get("declared_effects")),
            filesystem_changes=_legacy_dict_list(data.get("filesystem_changes")),
            artifact_refs=_legacy_artifact_refs(data.get("artifact_refs")),
            normalized_request=_legacy_dict(data.get("normalized_request")),
            provenance=_legacy_dict(data.get("provenance")),
            worker_still_running=bool(data.get("worker_still_running", False)),
            attempt_id=_legacy_attempt_identity(data.get("attempt_id")),
            effect_ref=_legacy_optional_string(data.get("effect_ref")),
            effect_state=_legacy_effect_state(data.get("effect_state")),
            idempotency_ref=_legacy_optional_string(data.get("idempotency_ref")),
            retry_disposition=_legacy_retry_disposition(
                data.get("retry_disposition"),
                status=raw_status,
                recoverable=bool(data.get("recoverable", metadata.get("recoverable", False))),
                worker_still_running=bool(data.get("worker_still_running", False)),
            ),
            reconciliation_required=bool(data.get("reconciliation_required", False)),
            outcome_unknown=bool(data.get("outcome_unknown", False)),
            late_result=bool(data.get("late_result", False)),
            owner_generation=_legacy_non_negative_int(data.get("owner_generation")),
            stale_owner=bool(data.get("stale_owner", False)),
            batch_closure=_legacy_dict(data.get("batch_closure")),
        )

    @classmethod
    def from_value(cls, payload: Any) -> "ToolResult":
        if isinstance(payload, Mapping) and "schema_version" in payload:
            if payload.get("schema_version") == TOOL_RESULT_SCHEMA_VERSION:
                return cls.from_canonical_dict(payload)
            return ToolResultCompatibilityReader.read(payload)
        return cls.from_legacy_value(payload)


class ToolResultCompatibilityReader:
    """Bounded reader for the historical v1 shape; never a current writer."""

    @classmethod
    def read(cls, payload: Mapping[str, Any]) -> ToolResult:
        if not isinstance(payload, Mapping):
            raise _fail("invalid_canonical_payload", "historical payload must be an object")
        data = dict(payload)
        if data.get("schema_version") != HISTORICAL_TOOL_RESULT_SCHEMA_VERSION:
            raise _fail("unknown_schema_version", "historical tool-result schema is unsupported")
        unknown = sorted(set(data) - _HISTORICAL_FIELDS)
        if unknown:
            code = (
                "mixed_schema_field"
                if any(name in _CURRENT_FIELDS for name in unknown)
                else "unknown_canonical_field"
            )
            raise _fail(code, "historical payload does not match its frozen grammar")
        if "status" not in data:
            raise _fail("missing_canonical_field", "historical status is required")
        success_present = "success" in data
        success = data.pop("success", None)
        data["schema_version"] = TOOL_RESULT_SCHEMA_VERSION
        data["artifact_refs"] = _legacy_artifact_refs(data.get("artifact_refs"))
        data["attempt_id"] = _legacy_attempt_identity(data.get("attempt_id"))
        closure = _legacy_dict(data.get("batch_closure"))
        for slot in closure.get("slots", []) if isinstance(closure.get("slots"), list) else []:
            if isinstance(slot, dict) and isinstance(slot.get("attempt_id"), str):
                attempt = _legacy_attempt_identity(slot["attempt_id"])
                slot["attempt_id"] = attempt.to_dict() if attempt else None
        data["batch_closure"] = closure
        result = ToolResult(**data)  # type: ignore[arg-type]
        if success_present and (
            not isinstance(success, bool) or success != result.is_success
        ):
            raise _fail("contradictory_outcome", "historical success flag is contradictory")
        return result


@dataclass(frozen=True)
class ToolEffectsSnapshotComponent:
    """Lane C's unresolved and committed outcomes in a snapshot."""

    results: tuple[ToolResult, ...]
    schema_version: str = TOOL_EFFECTS_COMPONENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOL_EFFECTS_COMPONENT_SCHEMA_VERSION:
            raise _fail("unknown_schema_version", "unsupported tool-effects component")
        if any(not isinstance(item, ToolResult) for item in self.results):
            raise _fail("invalid_canonical_field", "tool-effects entries must be ToolResult")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "results": [item.to_persistence_dict() for item in self.results],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToolEffectsSnapshotComponent":
        if not isinstance(payload, Mapping) or set(payload) != {"schema_version", "results"}:
            raise _fail("invalid_canonical_payload", "tool-effects component shape is invalid")
        results = payload.get("results")
        if not isinstance(results, list):
            raise _fail("invalid_canonical_field", "tool-effects results must be an array")
        return cls(
            schema_version=payload["schema_version"],
            results=tuple(ToolResult.from_canonical_dict(item) for item in results),
        )


def _encode_tool_effects_component(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, ToolEffectsSnapshotComponent):
        raise _fail("invalid_canonical_field", "tool-effects codec requires its component type")
    return value.to_dict()


TOOL_EFFECTS_SNAPSHOT_COMPONENT_CODEC = SnapshotComponentCodec(
    slot="tool_effects",
    owner="qitos.effects",
    schema_version=TOOL_EFFECTS_COMPONENT_SCHEMA_VERSION,
    required=True,
    encode=_encode_tool_effects_component,
    decode=ToolEffectsSnapshotComponent.from_dict,
)


__all__ = [
    "HISTORICAL_TOOL_RESULT_SCHEMA_VERSION", "TOOL_RESULT_MODEL_VIEW_VERSION",
    "TOOL_RESULT_SCHEMA_VERSION",
    "TOOL_BATCH_CLOSURE_SCHEMA_VERSION", "TOOL_RESULT_TRACE_SAFE_VERSION",
    "TOOL_EFFECTS_COMPONENT_SCHEMA_VERSION", "TOOL_EFFECTS_SNAPSHOT_COMPONENT_CODEC",
    "EffectState", "RetryDisposition",
    "ToolEffectsSnapshotComponent", "ToolErrorKind", "ToolResult",
    "ToolResultCompatibilityReader", "ToolResultContractError", "ToolResultStatus",
]

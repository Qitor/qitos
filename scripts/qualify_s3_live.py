#!/usr/bin/env python3
"""Run bounded, opt-in S3 live-provider qualification.

Profile configuration is parsed from the internal Markdown matrix. Credential
values stay in their endpoint-specific environment variables and are never
included in the redacted summary. Provider payloads, when requested, are
written only to an explicit directory outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "docs" / "internal" / "plans" / "s3_g4_live_model_matrix.md"
SCHEMA_VERSION = "qitos.s3.live_qualification/v1"
MAX_REQUESTS_PER_PROFILE = 12
MAX_OUTPUT_TOKENS_PER_REQUEST = 10_240
TIMEOUT_SECONDS = 180
_ALLOWED_OUTCOMES = frozenset(
    {
        "supported",
        "unsupported",
        "capability_loss",
        "provider_error",
        "protocol_error",
        "configuration_blocked",
        "timeout",
        "unsafe_to_retry",
    }
)
_CREDENTIAL_RE = re.compile(r"^env:(QITOS_LIVE_(?:DSV4|GLM52|QWEN38)_API_KEY)$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_HOST_PATH_RE = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\\\Users\\\\)")
_SECRET_MARKER_RE = re.compile(
    r"(?i)(authorization\s*:|bearer\s+[A-Za-z0-9._~+/=-]+|cookie\s*:|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTESTATION_FACTS = (
    "cwd_is_workspace",
    "expected_non_root_user",
    "network_mode_none",
    "tmpfs_matches_policy",
    "root_filesystem_read_only",
    "required_mounts_present",
    "mount_modes_correct",
    "unexpected_mounts_absent",
    "docker_socket_absent",
    "host_private_paths_absent",
    "sensitive_environment_absent",
    "required_tools_present",
    "workspace_writable",
    "outside_boundary_not_writable",
    "initial_agent_output_absent",
    "all_tools_same_env_identity",
)


@dataclass(frozen=True)
class LiveProfile:
    profile_id: str
    endpoint: str
    model: str
    credential_env: str
    request_override: Mapping[str, Any]

    @property
    def base_url(self) -> str:
        suffix = "/chat/completions"
        if not self.endpoint.endswith(suffix):
            raise ValueError("profile endpoint is not a chat-completions route")
        return self.endpoint[: -len(suffix)]

    @property
    def endpoint_digest(self) -> str:
        return _sha256_text(self.endpoint)

    @property
    def request_policy_digest(self) -> str:
        return _sha256_json(
            {
                "max_requests_per_profile": MAX_REQUESTS_PER_PROFILE,
                "max_output_tokens_per_request": MAX_OUTPUT_TOKENS_PER_REQUEST,
                "timeout_seconds": TIMEOUT_SECONDS,
                "retry_count": 0,
                "request_override": self.request_override,
            }
        )


class QualificationConfigurationError(ValueError):
    """The checked-in qualification configuration is invalid."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )


def _parse_scalar(value: str) -> Any:
    normalized = value.strip()
    if normalized.lower() == "true":
        return True
    if normalized.lower() == "false":
        return False
    if re.fullmatch(r"-?[0-9]+", normalized):
        return int(normalized)
    return normalized


def _parse_override(value: str) -> Mapping[str, Any]:
    cleaned = value.strip().strip("`")
    if not cleaned or "=" not in cleaned:
        raise QualificationConfigurationError("profile request override is invalid")
    dotted_key, raw_value = cleaned.split("=", 1)
    keys = [item.strip() for item in dotted_key.split(".") if item.strip()]
    if not keys or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for key in keys):
        raise QualificationConfigurationError("profile request override key is invalid")
    result: dict[str, Any] = {}
    cursor = result
    for key in keys[:-1]:
        child: dict[str, Any] = {}
        cursor[key] = child
        cursor = child
    cursor[keys[-1]] = _parse_scalar(raw_value)
    return result


def load_profiles(matrix_path: Path = MATRIX_PATH) -> tuple[LiveProfile, ...]:
    """Parse the sole registered-profile table from the internal matrix."""

    rows: list[LiveProfile] = []
    in_profiles = False
    for line in matrix_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "## Registered profiles":
            in_profiles = True
            continue
        if in_profiles and line.startswith("## "):
            break
        if not in_profiles or not line.startswith("| `sii-"):
            continue
        fields = [item.strip() for item in line.strip().strip("|").split("|")]
        if len(fields) != 6:
            raise QualificationConfigurationError("registered profile row is malformed")
        profile_id = fields[0].strip("`")
        endpoint = fields[1].strip("`")
        model = fields[2].strip("`")
        credential = fields[3].strip("`")
        match = _CREDENTIAL_RE.fullmatch(credential)
        if match is None:
            raise QualificationConfigurationError("profile credential reference is invalid")
        if not endpoint.startswith("https://") or not endpoint.endswith(
            "/v1/chat/completions"
        ):
            raise QualificationConfigurationError("profile endpoint is invalid")
        rows.append(
            LiveProfile(
                profile_id=profile_id,
                endpoint=endpoint,
                model=model,
                credential_env=match.group(1),
                request_override=_parse_override(fields[4]),
            )
        )
    if len(rows) != 3 or len({row.profile_id for row in rows}) != len(rows):
        raise QualificationConfigurationError(
            "live matrix must contain exactly three distinct registered profiles"
        )
    return tuple(sorted(rows, key=lambda item: item.profile_id))


def _tool(name: str, property_name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Return the supplied harmless value.",
            "parameters": {
                "type": "object",
                "properties": {property_name: {"type": "string"}},
                "required": [property_name],
                "additionalProperties": False,
            },
        },
    }


_SINGLE_TOOL = _tool("echo_value", "value")
_PARALLEL_TOOLS = (
    _tool("echo_alpha", "alpha"),
    _tool("echo_beta", "beta"),
    _tool("echo_gamma", "gamma"),
)


def _native_message(response: Any) -> Any:
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        return getattr(choices[0], "message", None)
    if isinstance(response, Mapping):
        raw_choices = response.get("choices")
        if isinstance(raw_choices, list) and raw_choices:
            first = raw_choices[0]
            if isinstance(first, Mapping):
                return first.get("message")
    return None


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _native_calls(response: Any) -> list[dict[str, Any]]:
    """Read only the provider-native tool_calls field, never assistant text."""

    raw_calls = _field(_native_message(response), "tool_calls")
    if not isinstance(raw_calls, list):
        return []
    calls: list[dict[str, Any]] = []
    for raw in raw_calls:
        function = _field(raw, "function")
        call_id = _field(raw, "id")
        name = _field(function, "name")
        arguments = _field(function, "arguments")
        if not isinstance(call_id, str) or not isinstance(name, str):
            continue
        calls.append(
            {
                "id": call_id,
                "type": str(_field(raw, "type") or "function"),
                "function": {
                    "name": name,
                    "arguments": str(arguments if arguments is not None else ""),
                },
            }
        )
    return calls


def _response_facts(response: Any) -> dict[str, Any]:
    message = _native_message(response)
    content = _field(message, "content")
    reasoning = _field(message, "reasoning_content")
    calls = _native_calls(response)
    finish_reason = None
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        finish_reason = getattr(choices[0], "finish_reason", None)
    return {
        "assistant_text_present": isinstance(content, str) and bool(content.strip()),
        "native_tool_call_count": len(calls),
        "provider_call_ids_present": bool(calls)
        and all(bool(item["id"].strip()) for item in calls),
        "provider_call_ids_unique": len({item["id"] for item in calls}) == len(calls),
        "reasoning_present": isinstance(reasoning, str) and bool(reasoning.strip()),
        "finish_reason": str(finish_reason or "unknown")[:64],
    }


def _raw_json(response: Any) -> Any:
    dumper = getattr(response, "model_dump", None)
    if callable(dumper):
        return dumper(mode="json")
    if isinstance(response, Mapping):
        return dict(response)
    return {"type": type(response).__name__}


class _LiveProbe:
    def __init__(
        self,
        *,
        profile: LiveProfile,
        credential: str,
        private_dir: Path,
        model_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.profile = profile
        self.credential = credential
        self.private_dir = private_dir
        self.request_count = 0
        self.retry_count = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.latency_ms = 0
        self.private_records: list[dict[str, Any]] = []
        if model_factory is None:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from qitos.models.openai import OpenAICompatibleModel

            model_factory = OpenAICompatibleModel
        self._model_factory = model_factory
        self.model = self._make_model(timeout=TIMEOUT_SECONDS)

    def _make_model(self, *, timeout: float) -> Any:
        return self._model_factory(
            model=self.profile.model,
            api_key=self.credential,
            base_url=self.profile.base_url,
            temperature=0.0,
            max_tokens=MAX_OUTPUT_TOKENS_PER_REQUEST,
            timeout=timeout,
            default_request_kwargs=dict(self.profile.request_override),
            retry=None,
        )

    def request(
        self,
        probe_id: str,
        messages: list[dict[str, Any]],
        *,
        model: Any = None,
        **options: Any,
    ) -> tuple[Optional[Any], dict[str, Any]]:
        if self.request_count >= MAX_REQUESTS_PER_PROFILE:
            return None, {
                "probe_id": probe_id,
                "outcome": "configuration_blocked",
                "reason": "request_budget_exhausted",
            }
        self.request_count += 1
        started = time.monotonic()
        active_model = model or self.model
        try:
            response = active_model.call_raw(messages, **options)
        except Exception as exc:
            elapsed = max(0, round((time.monotonic() - started) * 1000))
            self.latency_ms += elapsed
            failure = active_model.qitos_normalize_failure(exc)
            category = str(getattr(failure, "category", "provider_exception"))
            outcome = "timeout" if category == "timeout" else "provider_error"
            record = {
                "probe_id": probe_id,
                "outcome": outcome,
                "failure_category": category,
                "retryable": bool(getattr(failure, "retryable", False)),
                "safe_to_retry": False,
                "correlation_digest": str(
                    getattr(failure, "correlation_digest", "")
                ),
                "latency_ms": elapsed,
            }
            self.private_records.append(
                {
                    "probe_id": probe_id,
                    "outcome": outcome,
                    "failure_category": category,
                }
            )
            return None, record
        elapsed = max(0, round((time.monotonic() - started) * 1000))
        self.latency_ms += elapsed
        usage = active_model.extract_usage(response) or {}
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        total = usage.get("total_tokens")
        if isinstance(prompt, int) and not isinstance(prompt, bool):
            self.input_tokens += prompt
        if isinstance(completion, int) and not isinstance(completion, bool):
            self.output_tokens += completion
        if isinstance(total, int) and not isinstance(total, bool):
            self.total_tokens += total
        self.private_records.append(
            {"probe_id": probe_id, "response": _raw_json(response)}
        )
        return response, {
            "probe_id": probe_id,
            "outcome": "supported",
            "latency_ms": elapsed,
            "usage_reported": bool(usage),
            **_response_facts(response),
        }

    def persist_private(self) -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "profile_id": self.profile.profile_id,
            "endpoint": self.profile.endpoint,
            "model": self.profile.model,
            "records": self.private_records,
        }
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        path = self.private_dir / f"{self.profile.profile_id}.private.json"
        path.write_bytes(raw)
        path.chmod(0o600)
        return hashlib.sha256(raw).hexdigest()


def _probe_live(profile: LiveProfile, credential: str, private_dir: Path) -> dict[str, Any]:
    probe = _LiveProbe(
        profile=profile,
        credential=credential,
        private_dir=private_dir,
    )
    records: list[dict[str, Any]] = []
    basic, record = probe.request(
        "basic_response",
        [
            {"role": "system", "content": "Answer concisely and follow tool schemas exactly."},
            {"role": "user", "content": "Reply with the single word ready."},
        ],
    )
    _ = basic
    records.append(record)

    single, record = probe.request(
        "single_native_tool",
        [{"role": "user", "content": "Call echo_value once with value ready."}],
        tools=[_SINGLE_TOOL],
        tool_choice="required",
    )
    single_calls = _native_calls(single) if single is not None else []
    if record["outcome"] == "supported" and len(single_calls) != 1:
        record["outcome"] = "capability_loss"
        record["reason"] = "native_single_tool_call_absent"
    records.append(record)

    parallel, record = probe.request(
        "parallel_native_tools",
        [
            {
                "role": "user",
                "content": "Call echo_alpha, echo_beta, and echo_gamma exactly once each in one response.",
            }
        ],
        tools=list(_PARALLEL_TOOLS),
        tool_choice="required",
        parallel_tool_calls=True,
    )
    parallel_calls = _native_calls(parallel) if parallel is not None else []
    if record["outcome"] == "supported":
        names = {item["function"]["name"] for item in parallel_calls}
        if names != {"echo_alpha", "echo_beta", "echo_gamma"}:
            record["outcome"] = "capability_loss"
            record["reason"] = "native_parallel_tool_calls_incomplete"
    records.append(record)

    if parallel_calls:
        assistant = {"role": "assistant", "content": None, "tool_calls": parallel_calls}
        results = [
            {
                "role": "tool",
                "tool_call_id": item["id"],
                "content": json.dumps({"ok": True}),
            }
            for item in parallel_calls
        ]
        _, record = probe.request(
            "tool_result_continuation",
            [
                {"role": "user", "content": "Call all three tools, then summarize their results."},
                assistant,
                *results,
            ],
            tools=list(_PARALLEL_TOOLS),
            tool_choice="auto",
            parallel_tool_calls=True,
        )
    else:
        record = {
            "probe_id": "tool_result_continuation",
            "outcome": "capability_loss",
            "reason": "parallel_declaration_unavailable",
        }
    records.append(record)

    malformed_call = {
        "id": "qitos_malformed_call",
        "type": "function",
        "function": {"name": "echo_value", "arguments": "{"},
    }
    _, record = probe.request(
        "malformed_tool_arguments",
        [
            {"role": "user", "content": "Inspect this intentionally malformed prior call."},
            {"role": "assistant", "content": None, "tool_calls": [malformed_call]},
            {
                "role": "tool",
                "tool_call_id": "qitos_malformed_call",
                "content": "typed protocol error",
            },
        ],
        tools=[_SINGLE_TOOL],
    )
    records.append(record)

    invalid_tool = _tool("invalid_tool", "value")
    invalid_tool["function"]["name"] = ""
    _, record = probe.request(
        "typed_provider_failure",
        [{"role": "user", "content": "This request must be rejected."}],
        tools=[invalid_tool],
        tool_choice="required",
    )
    if record["outcome"] == "supported":
        record["outcome"] = "capability_loss"
        record["reason"] = "invalid_tool_schema_was_accepted"
    records.append(record)

    timeout_model = probe._make_model(timeout=0.001)
    _, record = probe.request(
        "timeout_cancellation",
        [{"role": "user", "content": "Reply with ready."}],
        model=timeout_model,
    )
    if record["outcome"] == "supported":
        record["outcome"] = "unsupported"
        record["reason"] = "timeout_not_observed"
    else:
        record["safe_to_retry"] = False
    records.append(record)

    private_digest = probe.persist_private()
    native_required = {
        item["probe_id"]: item["outcome"] for item in records
    }
    tool_capable = all(
        native_required.get(probe_id) == "supported"
        for probe_id in (
            "single_native_tool",
            "parallel_native_tools",
            "tool_result_continuation",
        )
    )
    outcomes = {item["outcome"] for item in records}
    overall = "supported" if tool_capable else (
        "provider_error" if "provider_error" in outcomes else "capability_loss"
    )
    return {
        "profile_id": profile.profile_id,
        "endpoint_digest": profile.endpoint_digest,
        "model": profile.model,
        "credential_reference": f"env:{profile.credential_env}",
        "credential_reference_status": "present",
        "request_policy_digest": profile.request_policy_digest,
        "outcome": overall,
        "tool_capable": tool_capable,
        "request_count": probe.request_count,
        "retry_count": probe.retry_count,
        "usage": {
            "input_tokens": probe.input_tokens,
            "output_tokens": probe.output_tokens,
            "total_tokens": probe.total_tokens,
            "provider_reported": bool(probe.total_tokens or probe.input_tokens or probe.output_tokens),
        },
        "latency_ms": probe.latency_ms,
        "stop_reason": "preflight_complete",
        "preflight": records,
        "raw_private_evidence_digest": private_digest,
    }


def _blocked_profile(profile: LiveProfile, reason: str) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "endpoint_digest": profile.endpoint_digest,
        "model": profile.model,
        "credential_reference": f"env:{profile.credential_env}",
        "credential_reference_status": (
            "missing" if reason == "credential_missing" else "not_read"
        ),
        "request_policy_digest": profile.request_policy_digest,
        "outcome": "configuration_blocked",
        "tool_capable": False,
        "request_count": 0,
        "retry_count": 0,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "provider_reported": False,
        },
        "latency_ms": 0,
        "stop_reason": reason,
        "preflight": [],
        "raw_private_evidence_digest": None,
    }


def _validate_private_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        pass
    else:
        raise QualificationConfigurationError(
            "private evidence directory must be outside the repository"
        )
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    resolved.chmod(0o700)
    return resolved


def _load_attestation(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationConfigurationError("sandbox attestation is not valid JSON") from exc
    if not isinstance(value, dict):
        raise QualificationConfigurationError("sandbox attestation must be an object")
    expected = {
        "schema_version",
        "sandbox_identity_digest",
        "env_identity_digest",
        "image_digest",
        "initial_repository_digest",
        "facts",
    }
    if set(value) != expected:
        raise QualificationConfigurationError("sandbox attestation fields are invalid")
    if value.get("schema_version") != "qitos.s3.sandbox_attestation/v1":
        raise QualificationConfigurationError("sandbox attestation schema is unsupported")
    for name in (
        "sandbox_identity_digest",
        "env_identity_digest",
        "image_digest",
        "initial_repository_digest",
    ):
        if not isinstance(value.get(name), str) or _DIGEST_RE.fullmatch(value[name]) is None:
            raise QualificationConfigurationError("sandbox attestation digest is invalid")
    facts = value.get("facts")
    if not isinstance(facts, dict) or set(facts) != set(_ATTESTATION_FACTS):
        raise QualificationConfigurationError("sandbox attestation fact set is invalid")
    if any(facts.get(name) is not True for name in _ATTESTATION_FACTS):
        raise QualificationConfigurationError("sandbox attestation did not pass")
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if _HOST_PATH_RE.search(serialized) or _SECRET_MARKER_RE.search(serialized):
        raise QualificationConfigurationError("sandbox attestation is not safely redacted")
    return value, hashlib.sha256(raw).hexdigest()


def _privacy_report(summary: Mapping[str, Any], credentials: Sequence[str]) -> dict[str, Any]:
    serialized = json.dumps(
        summary,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    findings: list[str] = []
    if _HOST_PATH_RE.search(serialized):
        findings.append("host_path_detected")
    if _SECRET_MARKER_RE.search(serialized):
        findings.append("secret_marker_detected")
    if any(value and value in serialized for value in credentials):
        findings.append("credential_value_detected")
    endpoints = [profile.endpoint for profile in load_profiles()]
    if any(endpoint in serialized for endpoint in endpoints):
        findings.append("raw_endpoint_detected")
    return {
        "scan_passed": not findings,
        "findings": sorted(findings),
        "credential_values_absent": "credential_value_detected" not in findings,
        "raw_endpoints_absent": "raw_endpoint_detected" not in findings,
        "host_paths_absent": "host_path_detected" not in findings,
        "raw_provider_payload_committed": False,
        "hidden_reasoning_committed": False,
    }


def qualify(
    profiles: Sequence[LiveProfile],
    *,
    live: bool,
    source_commit: str,
    private_dir: Optional[Path],
    attestation_path: Optional[Path] = None,
    generated_at: Optional[str] = None,
) -> dict[str, Any]:
    if not _COMMIT_RE.fullmatch(source_commit):
        raise QualificationConfigurationError("source commit must be a full SHA")
    selected = tuple(sorted(profiles, key=lambda item: item.profile_id))
    credentials = (
        [os.environ.get(profile.credential_env, "") for profile in selected]
        if live
        else ["" for _ in selected]
    )
    results: list[dict[str, Any]] = []
    live_private_dir: Optional[Path] = None
    attestation_digest: Optional[str] = None
    attestation_error: Optional[str] = None
    if live and any(credentials):
        if private_dir is None:
            attestation_error = "private_evidence_dir_required"
        else:
            live_private_dir = _validate_private_dir(private_dir)
        if attestation_error is None:
            if attestation_path is None:
                attestation_error = "sandbox_attestation_required"
            else:
                try:
                    _, attestation_digest = _load_attestation(attestation_path)
                except (OSError, QualificationConfigurationError):
                    attestation_error = "sandbox_attestation_invalid"
    for profile, credential in zip(selected, credentials):
        if not live:
            results.append(_blocked_profile(profile, "live_flag_required"))
        elif not credential:
            results.append(_blocked_profile(profile, "credential_missing"))
        elif attestation_error is not None:
            results.append(_blocked_profile(profile, attestation_error))
        elif live_private_dir is None or attestation_digest is None:
            results.append(_blocked_profile(profile, "sandbox_attestation_required"))
        else:
            results.append(_probe_live(profile, credential, live_private_dir))
    tool_capable_count = sum(bool(item["tool_capable"]) for item in results)
    all_profiles_observed = len(results) == 3
    single_agent_workflow = {
        "outcome": "configuration_blocked",
        "reason": "no_tool_capable_live_route"
        if tool_capable_count == 0
        else "workflow_not_executed_by_preflight_runner",
        "model_requests": 0,
    }
    multi_agent_workflow = {
        "outcome": "configuration_blocked",
        "reason": "no_tool_capable_live_route"
        if tool_capable_count == 0
        else "workflow_not_executed_by_preflight_runner",
        "model_requests": 0,
    }
    s3_live_passed = (
        all_profiles_observed
        and tool_capable_count >= 1
        and all(item["outcome"] != "configuration_blocked" for item in results)
        and single_agent_workflow["outcome"] == "supported"
        and multi_agent_workflow["outcome"] == "supported"
    )
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_commit": source_commit,
        "matrix_path": "docs/internal/plans/s3_g4_live_model_matrix.md",
        "matrix_digest": hashlib.sha256(MATRIX_PATH.read_bytes()).hexdigest(),
        "runner_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "live_requested": live,
        "budget": {
            "max_requests_per_profile": MAX_REQUESTS_PER_PROFILE,
            "max_output_tokens_per_request": MAX_OUTPUT_TOKENS_PER_REQUEST,
            "timeout_seconds": TIMEOUT_SECONDS,
            "automatic_retries": 0,
        },
        "profiles": results,
        "totals": {
            "profiles": len(results),
            "configuration_blocked": sum(
                item["outcome"] == "configuration_blocked" for item in results
            ),
            "tool_capable_profiles": tool_capable_count,
            "requests": sum(int(item["request_count"]) for item in results),
            "input_tokens": sum(int(item["usage"]["input_tokens"]) for item in results),
            "output_tokens": sum(int(item["usage"]["output_tokens"]) for item in results),
            "reported_tokens": sum(int(item["usage"]["total_tokens"]) for item in results),
            "latency_ms": sum(int(item["latency_ms"]) for item in results),
            "retries": sum(int(item["retry_count"]) for item in results),
        },
        "single_agent_workflow": single_agent_workflow,
        "multi_agent_restore_workflow": multi_agent_workflow,
        "sandbox": {
            "pre_model_attestation": "passed" if attestation_digest else "not_started",
            "attestation_digest": attestation_digest,
            "reason": "credential_gate_preceded_sandbox_provisioning"
            if not any(credentials)
            else attestation_error,
            "model_requests_before_attestation": 0,
            "host_fallback": False,
            "cleanup": "not_applicable_no_resource_created",
        },
        "trajectory": {
            "candidate_writer_default": False,
            "schema_frozen": False,
            "live_events_recorded": 0,
            "qita_default": "frozen_trace_v1_compatibility",
        },
        "decision": {
            "s3_status": "closed" if s3_live_passed else "blocked_live_qualification",
            "g4_live": "passed" if s3_live_passed else "configuration_blocked",
            "s4_ready": s3_live_passed,
            "feature_baseline_promoted": False,
            "default_branch_ready": False,
        },
    }
    summary["privacy"] = _privacy_report(summary, credentials)
    if not summary["privacy"]["scan_passed"]:
        summary["decision"] = {
            "s3_status": "blocked_live_qualification",
            "g4_live": "protocol_error",
            "s4_ready": False,
            "feature_baseline_promoted": False,
            "default_branch_ready": False,
        }
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    profiles = load_profiles()
    by_id = {profile.profile_id: profile for profile in profiles}
    parser = argparse.ArgumentParser(
        description="Run bounded S3 live-model qualification"
    )
    parser.add_argument(
        "--profile",
        action="append",
        required=True,
        choices=tuple(sorted(by_id)),
        help="explicit registered profile; repeat to select multiple profiles",
    )
    parser.add_argument("--live", action="store_true", help="allow live provider requests")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--private-dir", type=Path)
    parser.add_argument(
        "--attestation",
        type=Path,
        help="redacted passing sandbox attestation produced before any model request",
    )
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--generated-at", help="fixed RFC3339 timestamp for reproducible evidence")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    selected_ids = tuple(dict.fromkeys(args.profile))
    result = qualify(
        [by_id[profile_id] for profile_id in selected_ids],
        live=args.live,
        source_commit=args.source_commit,
        private_dir=args.private_dir,
        attestation_path=args.attestation,
        generated_at=args.generated_at,
    )
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.summary_out is not None:
        args.summary_out.write_text(rendered, encoding="utf-8")
    if args.json or args.summary_out is None:
        print(rendered, end="")
    return 0 if result["decision"]["g4_live"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

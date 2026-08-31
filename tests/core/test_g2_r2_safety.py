"""Adversarial safety checks for the repaired G2 diagnostic boundary."""

from __future__ import annotations

import json
import re

import pytest

from qitos.core.artifact import ArtifactContractError, ArtifactRef
from qitos.core.diagnostics import (
    diagnostic_string_is_sensitive,
    redact_diagnostic_value,
    safe_diagnostic_text,
)
from qitos.core.tool_result import ToolResult
from qitos.core.work_graph import WorkGraph, WorkGraphContractError
from qitos.models.codec import ProviderFailure


SENSITIVE_VALUES = (
    "/etc/passwd",
    "/usr/local/private/data.json",
    "/Library/Application Support/private.db",
    r"C:\Users\example\private.txt",
    r"\\server\share\private.txt",
    "file:///var/private/data.json",
    "~/private/data.json",
    "localhost",
    "127.0.0.1:9000",
    "http://[::1]:9010/private",
    "Authorization: Bearer synthetic-bearer-value",
    "Cookie: synthetic-cookie-value",
    "headers=synthetic-header-value",
    "sk-proj-syntheticcredential",
    "AKIAABCDEFGHIJKLMNOP",
    "abcdefgh.ijklmnop.qrstuvwx",
    "-----BEGIN PRIVATE KEY-----",
)


@pytest.mark.parametrize("value", SENSITIVE_VALUES)
def test_shared_diagnostic_boundary_classifies_and_never_echoes(value: str) -> None:
    assert diagnostic_string_is_sensitive(value)
    assert redact_diagnostic_value({"safe_name": [{"nested": value}]}) == {
        "safe_name": [{"nested": "[redacted]"}]
    }
    assert safe_diagnostic_text(value, fallback="safe fallback") == "safe fallback"


def test_recursive_redaction_covers_sensitive_keys_and_safe_named_leaves() -> None:
    raw = {
        "safe_name": [{"still_safe_name": value} for value in SENSITIVE_VALUES],
        "authorization": "synthetic value",
        "/etc/private-key-name": "synthetic value",
    }

    rendered = json.dumps(redact_diagnostic_value(raw), sort_keys=True)

    assert all(value not in rendered for value in SENSITIVE_VALUES)
    assert "authorization" not in rendered
    assert "/etc/private-key-name" not in rendered


def test_provider_failure_sanitizes_every_external_text_and_is_correlatable() -> None:
    failure = ProviderFailure(
        category=SENSITIVE_VALUES[0],
        message=SENSITIVE_VALUES[1],
        provider=SENSITIVE_VALUES[3],
        api_mode=SENSITIVE_VALUES[8],
        retryable=True,
        status_code=503,
        error_code=SENSITIVE_VALUES[13],
        redacted_details={"safe_name": list(SENSITIVE_VALUES)},
    )

    payload = failure.to_dict()
    rendered = json.dumps(payload, sort_keys=True)

    assert all(value not in rendered for value in SENSITIVE_VALUES)
    assert all(value not in str(failure) for value in SENSITIVE_VALUES)
    assert payload["retryable"] is True
    assert payload["status_code"] == 503
    assert payload["remediation"] == "Inspect the typed provider failure and codec report."
    assert re.fullmatch(r"[0-9a-f]{64}", payload["correlation_digest"])


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("artifact_id", "artifact:/etc/passwd"),
        ("resolver_key", "resolver:/usr/local/private"),
        ("media_type", "application//etc/passwd"),
        ("encoding", "file:///tmp/encoding"),
        ("model_summary", "available at /Library/private/data"),
    ),
)
def test_artifact_reference_rejects_unsafe_tokens_without_echo(
    field: str, value: str
) -> None:
    values = {
        "artifact_id": "artifact:fixture",
        "resolver_key": "resolver:fixture",
        "sha256": "a" * 64,
        "media_type": "application/json",
        "byte_length": 12,
        "encoding": "binary",
        "model_summary": "Portable fixture summary.",
    }
    values[field] = value

    with pytest.raises(ArtifactContractError) as caught:
        ArtifactRef(**values)

    assert value not in str(caught.value)


def test_artifact_serializers_revalidate_mutated_frozen_instances() -> None:
    artifact = ArtifactRef(
        artifact_id="artifact:fixture",
        resolver_key="resolver:fixture",
        sha256="b" * 64,
        media_type="application/json",
        byte_length=3,
        model_summary="Portable fixture summary.",
    )
    object.__setattr__(artifact, "resolver_key", "/etc/private/resolver")

    with pytest.raises(ArtifactContractError):
        artifact.to_dict()
    with pytest.raises(ArtifactContractError):
        artifact.to_model_projection()


def test_work_graph_and_tool_result_boundaries_do_not_echo_adversarial_values() -> None:
    raw = list(SENSITIVE_VALUES)
    with pytest.raises(WorkGraphContractError) as caught:
        WorkGraph(graph_id=raw[0])
    assert raw[0] not in str(caught.value)

    result = ToolResult(
        output={"safe_name": [{"nested": value} for value in raw]},
        next_action={"name": "read", "args": {"safe_name": raw}},
    )
    model = json.dumps(result.to_model_dict(max_chars=16000), sort_keys=True)
    trace = json.dumps(result.to_trace_safe_dict(max_chars=16000), sort_keys=True)

    assert all(value not in model for value in raw)
    assert all(value not in trace for value in raw)

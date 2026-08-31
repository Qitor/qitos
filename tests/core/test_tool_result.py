from __future__ import annotations

import json
from pathlib import Path

import pytest

from qitos.core.action import ActionResult, ActionStatus
from qitos.core.artifact import ArtifactRef
from qitos.core.tool_result import (
    HISTORICAL_TOOL_RESULT_SCHEMA_VERSION,
    TOOL_RESULT_MODEL_VIEW_VERSION,
    TOOL_RESULT_SCHEMA_VERSION,
    TOOL_RESULT_TRACE_SAFE_VERSION,
    ToolResult,
    ToolResultCompatibilityReader,
    ToolResultContractError,
)


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "tool_results" / "v1"
CURRENT_WRITER_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "tool_results"
    / "current"
    / "canonical-writer.json"
)
CURRENT_WRITER_EVIDENCE = CURRENT_WRITER_FIXTURE.with_name(
    "qualification-evidence.json"
)


def _artifact(name: str = "fixture") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"artifact:{name}",
        resolver_key=f"artifact-resolver:{name}",
        sha256="a" * 64,
        media_type="application/json",
        byte_length=12,
        model_summary="Artifact available through the declared resolver.",
    )


def test_canonical_result_round_trip_is_lossless() -> None:
    result = ToolResult(
        tool_name="edit",
        action_id="call-1",
        output={"changed": True, "private": "canonical"},
        model_output="Changed one file.",
        complete=False,
        truncated=True,
        omitted={"lines": 4},
        next_action={"name": "read", "args": {"path": "a.py"}},
        attempts=2,
        latency_ms=3.5,
        declared_effects=[{"kind": "filesystem_write"}],
        filesystem_changes=[{"path": "a.py", "operation": "updated"}],
        artifact_refs=(_artifact(),),
        normalized_request={"path": "a.py"},
        provenance={"source": "executor"},
    )

    payload = json.loads(json.dumps(result.to_dict()))
    loaded = ToolResult.from_value(payload)

    assert loaded.to_dict() == payload
    assert payload["schema_version"] == TOOL_RESULT_SCHEMA_VERSION
    assert payload["success"] is True
    assert payload["output"]["private"] == "canonical"
    assert payload["model_output"] == "Changed one file."


def test_current_writer_fixture_has_exact_strict_round_trip() -> None:
    payload = json.loads(CURRENT_WRITER_FIXTURE.read_text(encoding="utf-8"))
    evidence = json.loads(CURRENT_WRITER_EVIDENCE.read_text(encoding="utf-8"))

    restored = ToolResult.from_canonical_dict(payload)

    assert restored.to_persistence_dict() == payload
    assert payload["schema_version"] == TOOL_RESULT_SCHEMA_VERSION
    assert payload["attempt_id"]["kind"] == "attempt"
    assert payload["effect_state"] == "committed"
    assert evidence["contract_id"] == "qitos.tool_result.current_writer"
    assert evidence["contract_version"] == TOOL_RESULT_SCHEMA_VERSION
    assert evidence["fixture_path"].endswith("current/canonical-writer.json")


def test_action_result_adapter_preserves_terminal_execution_fields() -> None:
    action_result = ActionResult(
        name="slow",
        action_id="call-timeout",
        status=ActionStatus.TIMED_OUT,
        error="deadline exceeded",
        attempts=1,
        latency_ms=50.0,
        metadata={
            "error_category": "timeout",
            "worker_still_running": True,
            "recoverable": False,
            "provenance": {"timeout_source": "action"},
        },
    )

    canonical = action_result.to_tool_result()

    assert canonical.status == "timed_out"
    assert canonical.tool_name == "slow"
    assert canonical.action_id == "call-timeout"
    assert canonical.error_code == "timeout"
    assert canonical.error_kind == "execution"
    assert canonical.worker_still_running is True
    assert canonical.attempts == 1
    assert canonical.latency_ms == 50.0


def test_nested_canonical_result_is_authoritative_during_action_adaptation() -> None:
    semantic = ToolResult.semantic_error(
        code="path_not_found",
        error="missing path",
        recovery_hint="List the directory.",
        next_action={"name": "list_files", "args": {"path": "."}},
    )
    executor_record = ActionResult(
        name="read",
        action_id="call-2",
        status=ActionStatus.SUCCESS,
        output=semantic,
        attempts=2,
        latency_ms=4.0,
        metadata={"source": "function"},
    )

    canonical = ToolResult.from_action_result(executor_record)

    assert canonical.status == "error"
    assert canonical.error_kind == "semantic"
    assert canonical.error_code == "path_not_found"
    assert canonical.tool_name == "read"
    assert canonical.action_id == "call-2"
    assert canonical.attempts == 2


def test_legacy_dict_and_model_summary_remain_compatible() -> None:
    result = ToolResult.from_value(
        {
            "status": "partial",
            "output": {"model_summary": "bounded", "raw": [1, 2, 3]},
            "metadata": {"tool_name": "legacy"},
        }
    )

    assert result.status == "success"
    assert result.model_output == "bounded"
    assert result.output["raw"] == [1, 2, 3]
    assert result.tool_name == "legacy"


def test_canonical_serializer_does_not_flatten_output_but_legacy_adapter_can() -> None:
    result = ToolResult(output={"value": 7, "status": "nested"})

    canonical = result.to_persistence_dict()
    legacy = result.to_legacy_dict()

    assert "value" not in canonical
    assert canonical["status"] == "success"
    assert legacy["value"] == 7
    assert legacy["status"] == "success"


def test_from_value_discriminates_canonical_before_legacy_adaptation() -> None:
    with pytest.raises(ToolResultContractError) as caught:
        ToolResult.from_value(
            {
                "schema_version": "qitos.tool_result/v999",
                "status": "success",
                "output": "must not be guessed",
            }
        )

    assert caught.value.code == "unknown_schema_version"


@pytest.mark.parametrize(
    "current_only_field",
    [
        "attempt_id",
        "owner_generation",
        "effect_ref",
        "effect_state",
        "idempotency_ref",
        "reconciliation_required",
        "outcome_unknown",
        "late_result",
        "stale_owner",
        "retry_disposition",
        "batch_closure",
    ],
)
def test_historical_reader_rejects_every_current_only_field(
    current_only_field: str,
) -> None:
    payload: dict[str, object] = {
        "schema_version": HISTORICAL_TOOL_RESULT_SCHEMA_VERSION,
        "status": "success",
        current_only_field: None,
    }

    with pytest.raises(ToolResultContractError) as caught:
        ToolResultCompatibilityReader.read(payload)

    assert caught.value.code == "mixed_schema_field"


def test_current_identifier_rejects_historical_only_shape() -> None:
    payload = {
        "schema_version": TOOL_RESULT_SCHEMA_VERSION,
        "status": "success",
        "output": "historical shape under a current identifier",
    }

    with pytest.raises(ToolResultContractError) as caught:
        ToolResult.from_canonical_dict(payload)

    assert caught.value.code == "missing_canonical_field"


def test_rejected_tool_result_data_never_appears_in_typed_error() -> None:
    rejected = "sk-proj-synthetic-value-that-must-not-appear"
    payload = {
        "schema_version": HISTORICAL_TOOL_RESULT_SCHEMA_VERSION,
        "status": "success",
        rejected: {"nested": rejected},
    }

    with pytest.raises(ToolResultContractError) as caught:
        ToolResultCompatibilityReader.read(payload)

    assert caught.value.code == "unknown_canonical_field"
    assert rejected not in str(caught.value)


@pytest.mark.parametrize(
    "override",
    [
        {"metadata": []},
        {"omitted": []},
        {"declared_effects": ["not-an-object"]},
        {"filesystem_changes": {}},
        {"artifact_refs": [{"artifact_id": "x", "host_path": "/tmp/x"}]},
        {"normalized_request": []},
        {"provenance": []},
    ],
)
def test_malformed_canonical_collections_fail_without_silent_drops(
    override: dict[str, object],
) -> None:
    payload = ToolResult().to_dict()
    payload.update(override)

    with pytest.raises(ToolResultContractError):
        ToolResult.from_canonical_dict(payload)


@pytest.mark.parametrize(
    "override",
    [
        {"attempts": True},
        {"attempts": -1},
        {"latency_ms": float("inf")},
        {"complete": 1},
        {"truncated": 0},
        {"worker_still_running": "yes"},
        {"omitted": {"characters": True}},
    ],
)
def test_canonical_scalar_types_and_ranges_are_strict(
    override: dict[str, object],
) -> None:
    payload = ToolResult().to_dict()
    payload.update(override)

    with pytest.raises(ToolResultContractError):
        ToolResult.from_canonical_dict(payload)


def test_contradictory_terminal_state_is_rejected() -> None:
    payload = ToolResult().to_dict()
    payload.update(
        {
            "status": "success",
            "success": True,
            "error_kind": "execution",
            "error_code": "tool_failed",
        }
    )

    with pytest.raises(ToolResultContractError) as caught:
        ToolResult.from_canonical_dict(payload)

    assert caught.value.code == "contradictory_outcome"


def test_non_json_value_fails_at_typed_contract_boundary() -> None:
    with pytest.raises(ToolResultContractError) as caught:
        ToolResult(output=object())

    assert caught.value.code == "non_serializable_value"


def test_constructor_recursively_detaches_caller_owned_values() -> None:
    output = {"nested": [{"value": 1}]}
    metadata = {"nested": [{"value": 2}]}
    provenance = {"nested": {"value": 3}}
    artifact_refs = [_artifact("owned")]
    next_action = {"name": "read", "args": {"paths": ["a.py"]}}
    result = ToolResult(
        output=output,
        metadata=metadata,
        provenance=provenance,
        artifact_refs=artifact_refs,
        next_action=next_action,
    )

    output["nested"][0]["value"] = 10
    metadata["nested"][0]["value"] = 20
    provenance["nested"]["value"] = 30
    artifact_refs.append(_artifact("mutated"))
    next_action["args"]["paths"].append("b.py")
    result.output["nested"][0]["value"] = 40

    assert result.output == {"nested": [{"value": 40}]}
    assert result.metadata == {"nested": [{"value": 2}]}
    assert result.provenance == {"nested": {"value": 3}}
    assert result.artifact_refs == (_artifact("owned"),)
    assert result.next_action == {"name": "read", "args": {"paths": ["a.py"]}}
    assert output == {"nested": [{"value": 10}]}


def test_canonical_reader_recursively_detaches_input_mapping() -> None:
    payload = ToolResult(
        output={"nested": [1]},
        metadata={"nested": [2]},
        next_action={"name": "read", "args": {"paths": ["a.py"]}},
    ).to_persistence_dict()
    result = ToolResult.from_canonical_dict(payload)

    payload["output"]["nested"].append(9)
    payload["metadata"]["nested"].append(9)
    payload["next_action"]["args"]["paths"].append("b.py")

    assert result.output == {"nested": [1]}
    assert result.metadata == {"nested": [2]}
    assert result.next_action == {"name": "read", "args": {"paths": ["a.py"]}}


def test_legacy_reader_recursively_detaches_input_mapping() -> None:
    payload = {
        "output": {"nested": [1]},
        "metadata": {"nested": [2]},
        "next_action": {"name": "read", "args": {"paths": ["a.py"]}},
    }
    result = ToolResult.from_legacy_value(payload)

    payload["output"]["nested"].append(9)
    payload["metadata"]["nested"].append(9)
    payload["next_action"]["args"]["paths"].append("b.py")

    assert result.output == {"nested": [1]}
    assert result.metadata == {"nested": [2]}
    assert result.next_action == {"name": "read", "args": {"paths": ["a.py"]}}


def test_persistence_and_legacy_serializers_return_detached_trees() -> None:
    result = ToolResult(
        output={"nested": [1]},
        metadata={"nested": [2]},
        next_action={"name": "read", "args": {"paths": ["a.py"]}},
    )
    persistence = result.to_persistence_dict()
    legacy = result.to_legacy_dict()

    persistence["output"]["nested"].append(9)
    persistence["metadata"]["nested"].append(9)
    persistence["next_action"]["args"]["paths"].append("b.py")
    legacy["nested"].append(8)

    assert result.output == {"nested": [1]}
    assert result.metadata == {"nested": [2]}
    assert result.next_action == {"name": "read", "args": {"paths": ["a.py"]}}


def test_serializer_revalidates_mutated_canonical_object() -> None:
    result = ToolResult(output="valid")
    result.attempts = True

    with pytest.raises(ToolResultContractError) as caught:
        result.to_persistence_dict()

    assert caught.value.code == "invalid_canonical_field"


def test_present_success_field_must_be_boolean() -> None:
    payload = ToolResult().to_dict()
    payload["success"] = None

    with pytest.raises(ToolResultContractError) as caught:
        ToolResult.from_canonical_dict(payload)

    assert caught.value.code == "contradictory_outcome"


def test_model_view_is_allowlisted_redacted_and_bounded() -> None:
    result = ToolResult(
        tool_name="inspect",
        action_id="call-safe",
        output={"raw": "x" * 200},
        model_output=(
            "token=super-secret /Users/alice/work/private.txt " + "x" * 200
        ),
        metadata={"authorization": "Bearer internal"},
        normalized_request={"path": "/Users/alice/work/private.txt"},
        provenance={"exception_repr": "RuntimeError(secret)"},
        artifact_refs=(_artifact(),),
        filesystem_changes=[{"path": "/Users/alice/work/private.txt"}],
    )

    visible = result.to_model_dict(max_chars=80)

    assert set(visible) == {
        "schema_version",
        "status",
        "tool_name",
        "action_id",
        "model_output",
        "error",
        "error_code",
        "recoverable",
        "recovery_hint",
        "next_action",
    }
    assert visible["schema_version"] == TOOL_RESULT_MODEL_VIEW_VERSION
    assert len(visible["model_output"]) <= 80
    rendered = json.dumps(visible)
    assert "super-secret" not in rendered
    assert "/Users/alice" not in rendered
    assert "authorization" not in rendered
    assert "exception_repr" not in rendered
    assert "artifact_id" not in rendered
    assert "filesystem_changes" not in rendered
    assert result.output == {"raw": "x" * 200}


def test_zero_remaining_model_budget_emits_no_oversized_truncation_card() -> None:
    visible = ToolResult(output="x" * 100).to_model_dict(max_chars=0)

    assert visible["model_output"] == ""
    assert visible["error"] is None


def test_large_error_output_and_message_share_one_budget() -> None:
    result = ToolResult.execution_error(
        code="tool_failed",
        error="e" * 100,
        output="o" * 100,
    )

    visible = result.to_model_dict(max_chars=32)

    assert len(visible["model_output"] or "") + len(visible["error"] or "") <= 32


def test_trace_safe_projection_is_versioned_and_declares_loss() -> None:
    result = ToolResult(
        output={"token": "secret", "path": "/Users/alice/work/a.py"},
        metadata={"internal": True},
        provenance={"source": "executor"},
        artifact_refs=(_artifact(),),
    )

    visible = result.to_trace_safe_dict(max_chars=120)

    assert visible["schema_version"] == TOOL_RESULT_TRACE_SAFE_VERSION
    assert visible["loss"]["canonical_output_included"] is False
    assert set(visible["loss"]["excluded_fields"]) >= {
        "output",
        "metadata",
        "provenance",
        "artifact_refs",
    }
    assert visible["loss"]["redacted_secret_values"] == 2
    assert visible["loss"]["redacted_host_paths"] == 1
    assert '"token": "secret"' not in json.dumps(visible)
    assert "/Users/alice" not in json.dumps(visible)


def test_every_model_visible_field_is_redacted_and_loss_accounted() -> None:
    result = ToolResult.execution_error(
        tool_name="token=tool-secret",
        action_id="/Users/alice/private/action-id",
        code="secret=error-code",
        error="token=error-secret at /Users/alice/private/error.log",
        output="token=output-secret /Users/alice/private/output.log",
        recovery_hint="password=hint-secret in /Users/alice/private/hint.txt",
        next_action={
            "name": "secret=next-tool",
            "action_id": "/Users/alice/private/next-id",
            "args": {
                "authorization": "Bearer next-secret",
                "path": "/Users/alice/private/next.txt",
            },
        },
    )

    model_view = result.to_model_dict(max_chars=1000)
    trace_view = result.to_trace_safe_dict(max_chars=1000)
    rendered_model = json.dumps(model_view)
    rendered_trace = json.dumps(trace_view)

    for forbidden in (
        "tool-secret",
        "error-code",
        "error-secret",
        "output-secret",
        "hint-secret",
        "next-secret",
        "/Users/alice",
    ):
        assert forbidden not in rendered_model
        assert forbidden not in rendered_trace
    assert model_view["tool_name"] == "[REDACTED_IDENTIFIER]"
    assert model_view["action_id"] == "[REDACTED_IDENTIFIER]"
    assert model_view["error_code"] == "[REDACTED_IDENTIFIER]"
    loss = trace_view["loss"]
    assert loss["redacted_secret_values"] >= 5
    assert loss["redacted_host_paths"] >= 5
    assert loss["redacted_identifiers"] >= 5
    assert set(loss["fields"]) == {
        "model_output",
        "error",
        "recovery_hint",
        "identifiers",
        "next_action",
        "omitted",
    }
    assert loss["fields"]["model_output"]["secret_values"] >= 1
    assert loss["fields"]["error"]["host_paths"] >= 1
    assert loss["fields"]["recovery_hint"]["secret_values"] >= 1
    assert loss["fields"]["identifiers"]["redacted_identifiers"] == 3
    assert loss["fields"]["next_action"]["redacted_identifiers"] == 2


def test_sensitive_mapping_keys_are_recursive_collision_safe_and_loss_accounted() -> None:
    raw_output = {
        "/Users/alice/private/key": {
            "kept": "path-key-value",
            "nested": [{"token=nested-secret": "nested-value"}],
        },
        "token=key-secret": {
            "kept": "token-key-value",
            "detail": "password=value-secret /Users/alice/private/value.txt",
        },
        "[REDACTED_KEY_1]": "preexisting-placeholder",
        "benign": "unchanged",
    }
    next_args = {
        "safe": "kept",
        "nested": [{"authorization": "token=next-secret"}],
    }
    result = ToolResult(
        output=raw_output,
        next_action={"name": "read", "args": next_args},
    )

    canonical = result.to_persistence_dict()
    model = result.to_model_dict(max_chars=4000)
    trace = result.to_trace_safe_dict(max_chars=4000)
    rendered_model = json.dumps(model, sort_keys=True)
    rendered_trace = json.dumps(trace, sort_keys=True)
    projected_output = json.loads(model["model_output"])

    for forbidden in (
        "/Users/alice/private/key",
        "token=key-secret",
        "token=nested-secret",
        "authorization",
        "value-secret",
        "next-secret",
        "/Users/alice/private/value.txt",
    ):
        assert forbidden not in rendered_model
        assert forbidden not in rendered_trace
    assert canonical["output"] == raw_output
    assert canonical["next_action"]["args"] == next_args
    assert ToolResult.from_canonical_dict(canonical).to_persistence_dict() == canonical

    assert projected_output["[REDACTED_KEY_1]"] == "preexisting-placeholder"
    assert projected_output["benign"] == "unchanged"
    projected_values = list(projected_output.values())
    assert any(
        isinstance(value, dict) and value.get("kept") == "path-key-value"
        for value in projected_values
    )
    assert any(
        isinstance(value, dict)
        and value.get("kept") == "[REDACTED]"
        and value.get("detail") is not None
        for value in projected_values
    )
    assert len(projected_output) == len(raw_output)
    assert len(set(projected_output)) == len(raw_output)
    assert model["next_action"]["args"]["safe"] == "kept"

    loss = trace["loss"]
    assert loss["fields"]["model_output"]["redacted_keys"] == 3
    assert loss["fields"]["next_action"]["redacted_keys"] == 1
    assert loss["redacted_keys"] == sum(
        field["redacted_keys"] for field in loss["fields"].values()
    )
    for fact in (
        "secret_values",
        "host_paths",
        "non_json_values",
        "redacted_identifiers",
        "omitted_characters",
        "omitted_fields",
        "redacted_keys",
    ):
        aggregate_name = {
            "secret_values": "redacted_secret_values",
            "host_paths": "redacted_host_paths",
            "non_json_values": "redacted_non_json_values",
        }.get(fact, fact)
        assert loss[aggregate_name] == sum(
            field[fact] for field in loss["fields"].values()
        )


def test_trace_safe_omitted_keys_are_sanitized_bounded_and_loss_accounted() -> None:
    omitted = {
        "/Users/alice/private/omitted": 1,
        "token=omitted-secret": 2,
        "[REDACTED_KEY_1]": 3,
        "benign": 4,
        **{f"entry_{index:02d}_{'x' * 20}": index for index in range(5, 45)},
    }
    result = ToolResult(output=None, omitted=omitted)

    canonical = result.to_persistence_dict()
    trace = result.to_trace_safe_dict(max_chars=120)
    rendered = json.dumps(trace, sort_keys=True)
    safe_omitted = trace["omitted"]
    omitted_loss = trace["loss"]["fields"]["omitted"]

    assert canonical["omitted"] == omitted
    assert ToolResult.from_canonical_dict(canonical).to_persistence_dict() == canonical
    assert "/Users/alice/private/omitted" not in rendered
    assert "token=omitted-secret" not in rendered
    assert len(json.dumps(safe_omitted, sort_keys=True, separators=(",", ":"))) <= 120
    assert len(safe_omitted) < len(omitted)
    assert safe_omitted["[REDACTED_KEY_1]"] == 3
    assert safe_omitted["benign"] == 4
    assert omitted_loss["redacted_keys"] == 2
    assert omitted_loss["omitted_fields"] == len(omitted) - len(safe_omitted)
    assert omitted_loss["omitted_characters"] > 0
    assert trace["loss"]["redacted_keys"] == sum(
        field["redacted_keys"] for field in trace["loss"]["fields"].values()
    )


def test_zero_budget_omitted_projection_is_empty_and_explicitly_lossy() -> None:
    trace = ToolResult(
        output=None,
        omitted={"token=hidden": 1, "benign": 2},
    ).to_trace_safe_dict(max_chars=0)

    assert trace["model_output"] == ""
    assert trace["next_action"] is None
    assert trace["omitted"] == {}
    assert trace["loss"]["fields"]["omitted"]["redacted_keys"] == 1
    assert trace["loss"]["fields"]["omitted"]["omitted_fields"] == 2


def _scalar_leaves(value: object) -> list[object]:
    if isinstance(value, dict):
        return [
            leaf
            for item in value.values()
            for leaf in _scalar_leaves(item)
        ]
    if isinstance(value, list):
        return [leaf for item in value for leaf in _scalar_leaves(item)]
    return [value]


def test_forced_secret_content_redacts_all_scalar_types_without_harming_benign_values() -> None:
    unique_integer = 918273645
    unique_float = 918273.625
    raw_output = {
        "secret": {
            "text": "plain-sensitive-leaf",
            "integer": unique_integer,
            "float": unique_float,
            "boolean": True,
            "null": None,
            "nested": [{"value": 314159265}],
        },
        "/Users/example/private/count-key": 271828182,
        "benign": {
            "integer": 42,
            "float": 2.5,
            "boolean": False,
            "null": None,
        },
    }
    result = ToolResult(output=raw_output)

    model = result.to_model_dict(max_chars=4000)
    trace = result.to_trace_safe_dict(max_chars=4000)
    projected = json.loads(model["model_output"])
    rendered_model = json.dumps(model, sort_keys=True)
    rendered_trace = json.dumps(trace, sort_keys=True)
    secret_subtree = next(
        value
        for key, value in projected.items()
        if key.startswith("[REDACTED_KEY_") and isinstance(value, dict)
    )

    assert set(_scalar_leaves(secret_subtree)) == {"[REDACTED]"}
    assert projected["benign"] == raw_output["benign"]
    assert 271828182 in projected.values()
    assert str(unique_integer) not in rendered_model
    assert str(unique_integer) not in rendered_trace
    assert str(unique_float) not in rendered_model
    assert str(unique_float) not in rendered_trace
    assert result.to_persistence_dict()["output"] == raw_output
    canonical = ToolResult.from_canonical_dict(result.to_persistence_dict())
    assert canonical.output == raw_output
    output_facts = trace["loss"]["fields"]["model_output"]
    assert output_facts["redacted_keys"] == 2
    assert output_facts["secret_values"] == 7


def test_explicit_model_output_and_next_action_redact_forced_secret_scalars() -> None:
    model_float = 776655.125
    action_integer = 887766551
    result = ToolResult(
        output="canonical-output",
        model_output={"api_key": model_float, "benign": 3.25},
        next_action={
            "name": "read",
            "args": {
                "credential": {
                    "integer": action_integer,
                    "float": 123456.75,
                    "boolean": False,
                    "null": None,
                },
                "benign": {"integer": 9, "boolean": True, "null": None},
            },
        },
    )

    model = result.to_model_dict(max_chars=4000)
    trace = result.to_trace_safe_dict(max_chars=4000)
    projected_model_output = json.loads(model["model_output"])
    model_secret = next(
        value
        for key, value in projected_model_output.items()
        if key.startswith("[REDACTED_KEY_")
    )
    action_secret = next(
        value
        for key, value in model["next_action"]["args"].items()
        if key.startswith("[REDACTED_KEY_")
    )

    assert model_secret == "[REDACTED]"
    assert projected_model_output["benign"] == 3.25
    assert set(_scalar_leaves(action_secret)) == {"[REDACTED]"}
    assert model["next_action"]["args"]["benign"] == {
        "integer": 9,
        "boolean": True,
        "null": None,
    }
    rendered = json.dumps({"model": model, "trace": trace}, sort_keys=True)
    assert str(model_float) not in rendered
    assert str(action_integer) not in rendered
    assert trace["loss"]["fields"]["model_output"]["secret_values"] == 2
    assert trace["loss"]["fields"]["next_action"]["secret_values"] == 5


def test_omitted_sensitive_key_uses_count_role_and_preserves_integer_value() -> None:
    result = ToolResult(
        output=None,
        omitted={"token=hidden-field": 7, "benign": 11},
    )

    trace = result.to_trace_safe_dict(max_chars=4000)
    safe_key = next(
        key for key in trace["omitted"] if key.startswith("[REDACTED_KEY_")
    )

    assert trace["omitted"][safe_key] == 7
    assert type(trace["omitted"][safe_key]) is int
    assert trace["omitted"]["benign"] == 11
    omitted_facts = trace["loss"]["fields"]["omitted"]
    assert omitted_facts["redacted_keys"] == 1
    assert omitted_facts["secret_values"] == 1
    assert result.to_persistence_dict()["omitted"] == {
        "token=hidden-field": 7,
        "benign": 11,
    }


@pytest.mark.parametrize(
    "next_action",
    ["read", {"name": "", "args": {}}, {"name": "read", "args": []}],
)
def test_next_action_is_validated(next_action: object) -> None:
    with pytest.raises(ValueError, match="next_action"):
        ToolResult(next_action=next_action)  # type: ignore[arg-type]


def test_versioned_outcome_fixture_inventory() -> None:
    fixture = json.loads((FIXTURE_DIR / "canonical_outcomes.json").read_text())
    cases = {item["case"]: ToolResult.from_value(item["result"]) for item in fixture["cases"]}

    assert fixture["schema_version"] == HISTORICAL_TOOL_RESULT_SCHEMA_VERSION
    assert set(cases) == {
        "success",
        "semantic_error",
        "execution_error",
        "permission_skipped",
        "timed_out_worker_still_running",
        "cancelled",
        "missing_parallel_slot",
        "retries_attempt_count",
        "truncated_next_action",
        "filesystem_effects",
        "artifact_ref_slot",
        "legacy_dict_model_summary",
    }
    assert cases["timed_out_worker_still_running"].worker_still_running is True
    assert cases["retries_attempt_count"].attempts == 3
    assert cases["truncated_next_action"].omitted == {"hits": 19}
    assert cases["filesystem_effects"].filesystem_changes[0]["path"] == "notes.txt"
    assert cases["artifact_ref_slot"].artifact_refs[0].artifact_id.startswith("sha256:")


def test_versioned_durability_and_lifecycle_fixture_inventory() -> None:
    durability = json.loads((FIXTURE_DIR / "durability_receipts.json").read_text())
    lifecycle = json.loads((FIXTURE_DIR / "lifecycle_receipts.json").read_text())

    assert {item["receipt"]["state"] for item in durability["cases"]} == {
        "accepted",
        "queued",
        "persisted",
        "failed",
        "dropped",
    }
    lifecycle_cases = {item["case"]: item["receipt"] for item in lifecycle["cases"]}
    assert lifecycle_cases["repeated_shutdown"]["close_effects"] == 1
    assert lifecycle_cases["borrowed_resource_remains_open"]["state"] == "open"
    assert lifecycle_cases["borrowed_resource_remains_open"]["framework_close_calls"] == 0


def test_contract_hardening_fixture_is_consumable_by_lanes_b_and_d() -> None:
    fixture = json.loads((FIXTURE_DIR / "contract_hardening.json").read_text())
    evidence = json.loads((FIXTURE_DIR / "qualification-evidence.json").read_text())

    assert fixture["canonical_schema_version"] == HISTORICAL_TOOL_RESULT_SCHEMA_VERSION
    assert fixture["model_view_version"] == TOOL_RESULT_MODEL_VIEW_VERSION
    assert fixture["trace_safe_version"] == TOOL_RESULT_TRACE_SAFE_VERSION
    for case in fixture["invalid_canonical_cases"]:
        expected_error_code = case["expected_error_code"]
        if (
            expected_error_code == "unknown_schema_version"
            and case["result"].get("schema_version") == TOOL_RESULT_SCHEMA_VERSION
        ):
            expected_error_code = "missing_canonical_field"
        with pytest.raises(ToolResultContractError) as caught:
            ToolResult.from_value(case["result"])
        assert caught.value.code == expected_error_code

    canonical = ToolResult.from_value(fixture["model_safe_source"])
    model_view = canonical.to_model_dict(max_chars=4000)
    trace_view = canonical.to_trace_safe_dict(max_chars=4000)
    rendered_model = json.dumps(model_view)
    rendered_trace = json.dumps(trace_view)
    qualification = fixture["projection_qualification"]

    for forbidden in qualification["sensitive_text_forbidden"][:-2]:
        assert forbidden not in rendered_model
        assert forbidden not in rendered_trace
    projected_output = json.loads(model_view["model_output"])
    assert len(projected_output) == qualification["expected_model_output_entries"]
    placeholder = qualification["preexisting_placeholder_key"]
    assert projected_output[placeholder] == "preexisting-placeholder"
    assert projected_output["benign"] == "unchanged"
    assert trace_view["loss"]["canonical_output_included"] is False
    assert set(trace_view["loss"]["excluded_fields"]) == set(
        fixture["expected_trace_loss"]["excluded_fields"]
    )
    assert set(trace_view["loss"]["fields"]) == set(
        qualification["required_loss_fields"]
    )

    omitted = ToolResult.from_value(fixture["omitted_safe_source"])
    omitted_canonical = omitted.to_persistence_dict()
    omitted_trace = omitted.to_trace_safe_dict(
        max_chars=qualification["omitted_budget_chars"]
    )
    rendered_omitted = json.dumps(omitted_trace)
    for forbidden in qualification["sensitive_text_forbidden"][-2:]:
        assert forbidden not in rendered_omitted
    assert omitted_canonical["omitted"] == fixture["omitted_safe_source"]["omitted"]
    assert ToolResult.from_canonical_dict(
        omitted_canonical
    ).to_persistence_dict() == omitted_canonical
    assert len(omitted_trace["omitted"]) < len(omitted_canonical["omitted"])
    omitted_loss = omitted_trace["loss"]["fields"]["omitted"]
    assert omitted_loss["redacted_keys"] == 2
    assert omitted_loss["omitted_fields"] > 0
    assert omitted_loss["omitted_characters"] > 0
    assert omitted_trace["loss"]["redacted_keys"] == sum(
        field["redacted_keys"]
        for field in omitted_trace["loss"]["fields"].values()
    )
    scalar_qualification = fixture["scalar_projection_qualification"]
    redacted_count_values = [
        value
        for key, value in omitted_trace["omitted"].items()
        if key.startswith("[REDACTED_KEY_")
    ]
    assert scalar_qualification["omitted_count_preserved"] in redacted_count_values
    assert all(type(value) is int for value in redacted_count_values)

    scalar_canonical = ToolResult.from_value(fixture["forced_secret_scalar_source"])
    scalar_model = scalar_canonical.to_model_dict(max_chars=4000)
    scalar_trace = scalar_canonical.to_trace_safe_dict(max_chars=4000)
    scalar_output = json.loads(scalar_model["model_output"])
    secret_output = next(
        value
        for key, value in scalar_output.items()
        if key.startswith("[REDACTED_KEY_") and isinstance(value, dict)
    )
    secret_action = next(
        value
        for key, value in scalar_model["next_action"]["args"].items()
        if key.startswith("[REDACTED_KEY_")
    )
    assert set(_scalar_leaves(secret_output)) == {"[REDACTED]"}
    assert set(_scalar_leaves(secret_action)) == {"[REDACTED]"}
    assert scalar_output["benign"] == {
        "integer": 42,
        "float": 2.5,
        "boolean": False,
        "null": None,
    }
    assert scalar_model["next_action"]["args"]["benign"] == {
        "integer": 9,
        "boolean": True,
        "null": None,
    }
    assert scalar_qualification["host_path_value_preserved"] in scalar_output.values()
    scalar_rendered = json.dumps(
        {"model": scalar_model, "trace": scalar_trace}, sort_keys=True
    )
    for sentinel in scalar_qualification["forced_content_sentinels"][:-1]:
        assert sentinel not in scalar_rendered
    scalar_loss = scalar_trace["loss"]["fields"]
    assert scalar_loss["model_output"]["secret_values"] == (
        scalar_qualification["forced_output_secret_values"]
    )
    assert scalar_loss["next_action"]["secret_values"] == (
        scalar_qualification["forced_next_action_secret_values"]
    )
    assert scalar_trace["loss"]["redacted_secret_values"] == sum(
        field["secret_values"] for field in scalar_loss.values()
    )
    scalar_persistence = scalar_canonical.to_persistence_dict()
    assert scalar_persistence["output"] == fixture["forced_secret_scalar_source"][
        "output"
    ]
    assert scalar_persistence["next_action"] == fixture[
        "forced_secret_scalar_source"
    ]["next_action"]
    assert ToolResult.from_canonical_dict(
        scalar_persistence
    ).to_persistence_dict() == scalar_persistence

    explicit_canonical = ToolResult.from_value(
        fixture["explicit_model_output_scalar_source"]
    )
    explicit_model = explicit_canonical.to_model_dict(max_chars=4000)
    explicit_trace = explicit_canonical.to_trace_safe_dict(max_chars=4000)
    explicit_output = json.loads(explicit_model["model_output"])
    explicit_secret = next(
        value
        for key, value in explicit_output.items()
        if key.startswith("[REDACTED_KEY_")
    )
    assert explicit_secret == "[REDACTED]"
    assert explicit_output["benign"] == 3.25
    assert scalar_qualification["forced_content_sentinels"][-1] not in json.dumps(
        {"model": explicit_model, "trace": explicit_trace}, sort_keys=True
    )
    assert explicit_trace["loss"]["fields"]["model_output"][
        "secret_values"
    ] == scalar_qualification["explicit_model_output_secret_values"]
    explicit_persistence = explicit_canonical.to_persistence_dict()
    assert explicit_persistence["model_output"] == fixture[
        "explicit_model_output_scalar_source"
    ]["model_output"]
    assert ToolResult.from_canonical_dict(
        explicit_persistence
    ).to_persistence_dict() == explicit_persistence
    assert evidence["contract_id"] == "qitos.tool_result"
    assert evidence["contract_version"] == HISTORICAL_TOOL_RESULT_SCHEMA_VERSION
    assert evidence["fixture_path"].endswith("contract_hardening.json")
    assert evidence["qualification_authority"] == "qitos.g1.integration_owner/v1"
    assert evidence["qualified"] is True
    assert set(evidence["test_files"]) >= {
        "tests/core/test_tool_result.py",
        "tests/core/test_conversation.py",
    }
    assert len(evidence["probes"]) == 29

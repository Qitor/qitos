from __future__ import annotations

import json

import pytest

from qitos.tracing.privacy import (
    ProjectionLimits,
    ProviderRawPolicy,
    project_data,
)
from qitos.tracing.trajectory import PrivacyView


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("/Users/example/private.json", "host_path"),
        ("/home/example/private.json", "host_path"),
        ("/opt/qitos/private.json", "host_path"),
        (r"C:\Users\example\private.json", "host_path"),
        ("file:///private/run.json", "host_path"),
        ("http://localhost:9000/private", "local_endpoint"),
        ("Bearer private-token-value", "secret_value"),
        ("sk-proj-privatecredential", "secret_value"),
        ("-----BEGIN PRIVATE KEY-----", "secret_value"),
    ],
)
def test_public_projection_rejects_unsafe_values_without_echo(
    value: str, code: str
) -> None:
    result = project_data({"safe": value}, view=PrivacyView.REDACTED_PUBLIC)
    rendered = json.dumps(
        {
            "data": result.data,
            "findings": [finding.to_dict() for finding in result.findings],
        },
        sort_keys=True,
    )
    assert code in {finding.code for finding in result.findings}
    assert value not in rendered


def test_sensitive_key_and_provider_raw_policy() -> None:
    private = {
        "authorization": "synthetic-private-value",
        "provider_raw_payload": {"response": "opaque"},
        "normal": "visible",
    }
    public = project_data(
        private,
        view=PrivacyView.REDACTED_PUBLIC,
        provider_raw_policy=ProviderRawPolicy.REFERENCE_ONLY,
    )
    diagnostic = project_data(
        private,
        view=PrivacyView.SAFE_DIAGNOSTIC,
        provider_raw_policy=ProviderRawPolicy.OMIT,
    )
    raw = project_data(private, view=PrivacyView.RAW_PRIVATE)

    assert public.data["authorization"] == "__redacted__"
    assert public.data["provider_raw_payload"]["value"] == "__omitted__"
    assert diagnostic.data["provider_raw_payload"] == "__omitted__"
    assert raw.data == private
    assert private["provider_raw_payload"]["response"] == "opaque"
    assert "authorization" not in json.dumps(
        [finding.to_dict() for finding in public.findings]
    )


def test_safe_diagnostic_projection_is_bounded_and_reports_loss() -> None:
    value = {
        "long": "x" * 100,
        "many": list(range(20)),
        "deep": {"a": {"b": {"c": "end"}}},
    }
    result = project_data(
        value,
        view=PrivacyView.SAFE_DIAGNOSTIC,
        limits=ProjectionLimits(
            max_depth=2,
            max_mapping_items=3,
            max_sequence_items=4,
            max_string_chars=8,
            max_total_nodes=20,
        ),
    )
    codes = {finding.code for finding in result.findings}
    assert {"string_length_limit", "sequence_item_limit", "depth_limit"} <= codes
    assert not result.loss.is_lossless
    assert len(result.data["long"]) == 9
    assert len(result.data["many"]) == 4


def test_public_projection_bounds_input_before_recursive_conversion() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    cyclic["/Users/private/secret"] = "value"
    cyclic.update({f"safe_{index}": index for index in range(300)})

    projected = project_data(cyclic, view=PrivacyView.SAFE_DIAGNOSTIC)

    codes = {finding.code for finding in projected.findings}
    assert "depth_limit" in codes
    assert "mapping_item_limit" in codes
    assert "host_path" in codes
    assert "/Users/private/secret" not in str(projected.data)

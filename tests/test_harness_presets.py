from __future__ import annotations

from qitos.harness import build_harness_policy, resolve_family_preset
from qitos.models import build_model_for_preset
from qitos.models.profile_registry import infer_default_protocol, infer_model_profile


def test_resolve_family_preset_for_gold_families() -> None:
    assert resolve_family_preset("Qwen/Qwen3-8B").id == "qwen"
    assert resolve_family_preset("qwen-plus").id == "qwen"
    assert resolve_family_preset("qwen-max").id == "qwen"
    assert resolve_family_preset("GLM-5.1-sii").id == "glm"
    assert resolve_family_preset("zai-org/GLM-5.1-FP8").id == "glm"
    assert resolve_family_preset("moonshot-v1-128k").id == "kimi"
    assert resolve_family_preset("MiniMax-M2.5").id == "minimax"
    assert resolve_family_preset("gpt-oss-120b").id == "gpt-oss"
    assert resolve_family_preset("gemma-4-31b-it").id == "gemma-4"


def test_profile_registry_is_derived_from_presets() -> None:
    assert infer_model_profile("GLM-5.1-sii").default_protocol == "json_decision_v1"
    assert infer_model_profile("moonshot-v1-128k").default_protocol == "json_decision_v1"
    assert infer_model_profile("gpt-oss-120b").default_protocol == "json_decision_v1"
    assert infer_model_profile("gemma-4-31b-it").default_protocol == "json_decision_v1"
    assert infer_default_protocol("MiniMax-M2.5") == "minimax_tool_call_v1"


def test_build_harness_policy_keeps_glm_native_chain() -> None:
    harness = build_harness_policy(model_name="GLM-5.1-sii")
    assert harness.family_preset.id == "glm"
    assert harness.protocol.id == "json_decision_v1"
    assert harness.protocol.fallback_protocols == (
        "xml_decision_v1",
        "react_text_v1",
    )
    assert harness.tool_policy.primary_delivery == "api_parameter"
    assert harness.tool_policy.native_tool_call_preferred is True
    assert harness.parser_name == "JsonDecisionParser"


def test_build_harness_policy_keeps_minimax_native_chain() -> None:
    harness = build_harness_policy(model_name="MiniMax-M2.5")
    assert harness.family_preset.id == "minimax"
    assert harness.protocol.id == "minimax_tool_call_v1"
    assert harness.protocol.fallback_protocols == (
        "terminus_xml_v1",
        "terminus_json_v1",
        "json_decision_v1",
    )
    assert harness.tool_policy.primary_delivery == "api_parameter"
    assert harness.parser_name == "MiniMaxToolCallParser"


def test_build_model_for_preset_attaches_harness_metadata() -> None:
    llm = build_model_for_preset(
        family_id="qwen",
        model_name="Qwen/Qwen3-8B",
        api_key="test-key",
        base_url="https://example.invalid/v1",
    )
    assert llm.context_window == 128_000
    metadata = dict(getattr(llm, "qitos_harness_metadata", {}) or {})
    assert metadata["family_preset"] == "qwen"
    assert metadata["protocol"] == "json_decision_v1"
    assert metadata["adapter_kind"] == "openai-compatible"
    assert metadata["native_tool_call_preferred"] is True
    assert metadata["decision_lane_preference"] == "native_tool_calls"
    assert metadata["effective_tool_delivery"] == "api_parameter"
    assert llm.timeout == 120


def test_build_model_for_glm_preset_attaches_native_tool_call_metadata() -> None:
    llm = build_model_for_preset(
        family_id="glm",
        model_name="GLM-5.1-sii",
        api_key="test-key",
        base_url="https://example.invalid/v1",
    )
    metadata = dict(getattr(llm, "qitos_harness_metadata", {}) or {})
    assert metadata["family_preset"] == "glm"
    assert metadata["protocol"] == "json_decision_v1"
    assert metadata["native_tool_call_preferred"] is True
    assert metadata["decision_lane_preference"] == "native_tool_calls"
    assert metadata["effective_tool_delivery"] == "api_parameter"

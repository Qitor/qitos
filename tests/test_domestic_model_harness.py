"""Integration tests for domestic (Chinese) model harness — presets, protocols, and parsers.

Validates the full chain: FamilyPreset → adapter → protocol → parser → tool call decision
for all supported domestic model families.
"""

from __future__ import annotations

import pytest

from qitos.harness import build_model_for_preset
from qitos.protocols import (
    get_protocol,
    list_protocols,
    render_protocol_contract,
    render_protocol_prompt,
    render_protocol_tool_schema,
)
from qitos.harness._types import (
    FamilyPreset,
    ToolPolicy,
    ContextPolicy,
    build_protocol_for_preset,
)


# ---------------------------------------------------------------------------
# Domestic model presets (mirroring gold-presets data)
# ---------------------------------------------------------------------------

DEEPSEEK_PRESET = FamilyPreset(
    id="deepseek",
    display_name="DeepSeek",
    model_matchers=("deepseek",),
    adapter_kind="openai_compatible",
    default_protocol="json_decision_v1",
    fallback_protocols=("react_text_v1",),
    tool_policy=ToolPolicy(primary_delivery="prompt_injection"),
    context_policy=ContextPolicy(context_window_hint=128_000),
    recommended_models=("deepseek-chat", "deepseek-reasoner"),
)

QWEN_PRESET = FamilyPreset(
    id="qwen",
    display_name="Qwen (Tongyi)",
    model_matchers=("qwen",),
    adapter_kind="openai_compatible",
    default_protocol="json_decision_v1",
    fallback_protocols=("react_text_v1",),
    tool_policy=ToolPolicy(
        primary_delivery="prompt_injection",
        native_tool_call_preferred=True,
    ),
    context_policy=ContextPolicy(context_window_hint=128_000),
    recommended_models=("qwen-plus", "qwen-turbo", "Qwen3-8B"),
)

GLM_PRESET = FamilyPreset(
    id="glm",
    display_name="GLM (Zhipu)",
    model_matchers=("glm",),
    adapter_kind="openai_compatible",
    default_protocol="json_decision_v1",
    fallback_protocols=("react_text_v1",),
    tool_policy=ToolPolicy(primary_delivery="prompt_injection"),
    context_policy=ContextPolicy(context_window_hint=128_000),
    recommended_models=("glm-4", "glm-4-flash"),
)

MINIMAX_PRESET = FamilyPreset(
    id="minimax",
    display_name="MiniMax",
    model_matchers=("minimax",),
    adapter_kind="openai_compatible",
    default_protocol="minimax_tool_call_v1",
    fallback_protocols=("terminus_xml_v1", "json_decision_v1"),
    tool_policy=ToolPolicy(
        primary_delivery="prompt_injection",
        native_tool_call_preferred=True,
    ),
    context_policy=ContextPolicy(context_window_hint=128_000),
    recommended_models=("MiniMax-M2.5",),
)


# ---------------------------------------------------------------------------
# Tests: Preset resolution
# ---------------------------------------------------------------------------


class TestDomesticPresetResolution:
    @pytest.mark.parametrize(
        "preset,model_id",
        [
            (DEEPSEEK_PRESET, "deepseek-chat"),
            (QWEN_PRESET, "qwen-plus"),
            (GLM_PRESET, "glm-4"),
            (MINIMAX_PRESET, "MiniMax-M2.5"),
        ],
    )
    def test_preset_matches_recommended(self, preset, model_id):
        assert preset.matches(model_id)

    @pytest.mark.parametrize(
        "preset,wrong_id",
        [
            (DEEPSEEK_PRESET, "gpt-4"),
            (QWEN_PRESET, "claude-3"),
            (GLM_PRESET, "llama-3"),
            (MINIMAX_PRESET, "gemini-pro"),
        ],
    )
    def test_preset_rejects_unrelated(self, preset, wrong_id):
        assert not preset.matches(wrong_id)

    def test_preset_id_match(self):
        assert DEEPSEEK_PRESET.matches("deepseek")
        assert QWEN_PRESET.matches("qwen")
        assert GLM_PRESET.matches("glm")
        assert MINIMAX_PRESET.matches("minimax")


# ---------------------------------------------------------------------------
# Tests: Protocol building
# ---------------------------------------------------------------------------


class TestDomesticProtocolBuild:
    @pytest.mark.parametrize(
        "preset",
        [DEEPSEEK_PRESET, QWEN_PRESET, GLM_PRESET, MINIMAX_PRESET],
    )
    def test_build_protocol_succeeds(self, preset):
        protocol = build_protocol_for_preset(preset=preset)
        assert protocol.id is not None
        assert protocol.prompt_renderer is not None
        assert protocol.tool_schema_renderer is not None

    def test_deepseek_uses_json_decision(self):
        protocol = build_protocol_for_preset(preset=DEEPSEEK_PRESET)
        assert "json" in protocol.id.lower() or protocol.id == "json_decision_v1"

    def test_qwen_uses_json_decision(self):
        protocol = build_protocol_for_preset(preset=QWEN_PRESET)
        assert protocol.id == "json_decision_v1"

    def test_glm_uses_json_decision(self):
        protocol = build_protocol_for_preset(preset=GLM_PRESET)
        assert protocol.id == "json_decision_v1"

    def test_minimax_uses_native_tool_call(self):
        protocol = build_protocol_for_preset(preset=MINIMAX_PRESET)
        assert protocol.id == "minimax_tool_call_v1"
        assert protocol.supports_native_tool_call_markup is True

    def test_minimax_has_fallback_chain(self):
        protocol = build_protocol_for_preset(preset=MINIMAX_PRESET)
        assert len(protocol.fallback_protocols) >= 2


# ---------------------------------------------------------------------------
# Tests: Protocol rendering
# ---------------------------------------------------------------------------


class TestDomesticProtocolRendering:
    @pytest.mark.parametrize(
        "preset",
        [DEEPSEEK_PRESET, QWEN_PRESET, GLM_PRESET, MINIMAX_PRESET],
    )
    def test_render_prompt(self, preset):
        protocol = build_protocol_for_preset(preset=preset)
        # render_protocol_prompt(base_prompt, protocol, tool_registry)
        prompt = render_protocol_prompt("test task", protocol, None)
        assert len(prompt) > 0

    @pytest.mark.parametrize(
        "preset",
        [DEEPSEEK_PRESET, QWEN_PRESET, GLM_PRESET, MINIMAX_PRESET],
    )
    def test_render_tool_schema(self, preset):
        protocol = build_protocol_for_preset(preset=preset)
        # render_protocol_tool_schema(tool_registry, protocol)
        schema = render_protocol_tool_schema(None, protocol)
        # tool_registry=None may produce empty schema; just verify no error
        assert schema is not None

    @pytest.mark.parametrize(
        "preset",
        [DEEPSEEK_PRESET, QWEN_PRESET, GLM_PRESET, MINIMAX_PRESET],
    )
    def test_render_contract(self, preset):
        protocol = build_protocol_for_preset(preset=preset)
        contract = render_protocol_contract(protocol)
        assert len(contract) > 0


# ---------------------------------------------------------------------------
# Tests: Embedder ↔ Preset pairing
# ---------------------------------------------------------------------------


class TestEmbedderPresetPairing:
    def test_dashscope_pairs_with_qwen(self):
        from qitos.kit.embedding import DashScopeEmbedder

        embedder = DashScopeEmbedder(model="text-embedding-v3")
        assert embedder.dimension == 1024
        assert QWEN_PRESET.id == "qwen"

    def test_zhipu_pairs_with_glm(self):
        from qitos.kit.embedding import ZhipuEmbedder

        embedder = ZhipuEmbedder(model="embedding-3")
        assert embedder.dimension == 2048
        assert GLM_PRESET.id == "glm"


# ---------------------------------------------------------------------------
# Tests: Context policy
# ---------------------------------------------------------------------------


class TestDomesticContextPolicy:
    def test_qwen_context_window(self):
        assert QWEN_PRESET.context_policy.context_window_hint == 128_000

    def test_minimax_context_window(self):
        assert MINIMAX_PRESET.context_policy.context_window_hint == 128_000

    def test_deepseek_context_window(self):
        assert DEEPSEEK_PRESET.context_policy.context_window_hint == 128_000

    def test_glm_context_window(self):
        assert GLM_PRESET.context_policy.context_window_hint == 128_000

    def test_qwen_native_tool_call(self):
        assert QWEN_PRESET.tool_policy.native_tool_call_preferred is True

    def test_minimax_native_tool_call(self):
        assert MINIMAX_PRESET.tool_policy.native_tool_call_preferred is True


def test_openai_compatible_harness_propagates_responses_api_mode():
    model = build_model_for_preset(
        model_name="qwen-plus",
        family_id="qwen",
        api_key="test-key",
        base_url="https://example.test/v1",
        api_mode="responses",
    )

    assert model.api_mode == "responses"
    assert model.qitos_harness_metadata["api_mode"] == "responses"

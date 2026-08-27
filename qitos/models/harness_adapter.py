"""Preset-backed model transport adapters.

Concrete adapters construct provider transports from family presets and
therefore live on the models side of the harness/models boundary (D5):
harness owns preset data and policy types, models owns transports.
"""

from __future__ import annotations

from ..harness import build_harness_policy
from ..harness._types import ContextPolicy, FamilyPreset, ModelAdapter
from .context_registry import infer_context_window
from .openai import OpenAICompatibleModel


def _coerce_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return float(default)


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(default)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(value)
    return int(default)


def resolve_context_window(
    model_name: str | None, *, context_policy: ContextPolicy, explicit: int | None = None
) -> int:
    if isinstance(explicit, int) and explicit > 0:
        return int(explicit)
    inferred = infer_context_window(
        model_name,
        fallback=context_policy.context_window_hint
        or context_policy.fallback_context_window,
    )
    if isinstance(inferred, int) and inferred > 0:
        return int(inferred)
    return int(context_policy.fallback_context_window)


class OpenAICompatibleAdapter(ModelAdapter):
    kind = "openai-compatible"

    def build_model(self, **kwargs: object) -> OpenAICompatibleModel:
        preset = kwargs["preset"]
        model_name = kwargs["model_name"]
        api_key = kwargs.get("api_key")
        base_url = kwargs.get("base_url")
        context_policy = kwargs["context_policy"]
        temperature = _coerce_float(kwargs.get("temperature"), 0.2)
        max_tokens = _coerce_int(kwargs.get("max_tokens"), 2048)
        timeout = _coerce_int(kwargs.get("timeout"), 120)
        system_prompt = kwargs.get("system_prompt")
        context_window = kwargs.get("context_window")
        default_request_kwargs = kwargs.get("default_request_kwargs")
        api_mode = str(kwargs.get("api_mode") or "chat_completions")
        if not isinstance(preset, FamilyPreset):
            raise TypeError("preset must be a FamilyPreset")
        if not isinstance(model_name, str):
            raise TypeError("model_name must be a string")
        if not isinstance(context_policy, ContextPolicy):
            raise TypeError("context_policy must be a ContextPolicy")
        llm = OpenAICompatibleModel(
            model=model_name,
            api_key=str(api_key) if api_key is not None else None,
            base_url=str(base_url) if base_url is not None else None,
            system_prompt=str(system_prompt) if system_prompt is not None else None,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            context_window=resolve_context_window(
                model_name,
                context_policy=context_policy,
                explicit=(
                    _coerce_int(context_window, 0)
                    if context_window is not None
                    else None
                ),
            ),
            default_request_kwargs=dict(default_request_kwargs) if isinstance(default_request_kwargs, dict) else None,
            api_mode=api_mode,
        )
        setattr(
            llm,
            "qitos_harness_metadata",
            {
                "family_preset": preset.id,
                "context_policy": context_policy.to_dict(),
                "adapter_kind": self.kind,
                "api_mode": llm.api_mode,
            },
        )
        return llm


def adapter_for_kind(kind: str) -> ModelAdapter:
    normalized = str(kind or "").strip().lower()
    if normalized == "openai-compatible":
        return OpenAICompatibleAdapter()
    raise ValueError(f"Unknown harness adapter kind: {kind}")


def build_model_for_preset(
    *,
    model_name: str,
    family_id: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    protocol: object | None = None,
    tool_delivery: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: int = 120,
    system_prompt: str | None = None,
    context_window: int | None = None,
    default_request_kwargs: dict[str, object] | None = None,
    api_mode: str = "chat_completions",
) -> object:
    harness = build_harness_policy(
        model_name=model_name,
        family_id=family_id,
        protocol=protocol,
        tool_delivery=tool_delivery,
    )
    adapter = adapter_for_kind(harness.family_preset.adapter_kind)
    llm = adapter.build_model(
        preset=harness.family_preset,
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        context_policy=harness.context_policy,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        system_prompt=system_prompt,
        context_window=context_window,
        default_request_kwargs=default_request_kwargs,
        api_mode=api_mode,
    )
    metadata = dict(getattr(llm, "qitos_harness_metadata", {}) or {})
    metadata.update(harness.to_dict())
    metadata.setdefault(
        "decision_lane_preference",
        "native_tool_calls"
        if harness.tool_policy.native_tool_call_preferred
        else "parser",
    )
    metadata.setdefault(
        "native_tool_call_preferred", harness.tool_policy.native_tool_call_preferred
    )
    metadata.setdefault("effective_tool_delivery", harness.protocol.tool_schema_delivery)
    setattr(llm, "qitos_harness_metadata", metadata)
    setattr(llm, "qitos_family_preset", harness.family_preset.id)
    setattr(llm, "qitos_protocol", harness.protocol.id)
    return llm


__all__ = [
    "OpenAICompatibleAdapter",
    "adapter_for_kind",
    "build_model_for_preset",
    "resolve_context_window",
]

"""Preset-backed model harness helpers."""

from __future__ import annotations

from typing import Any

from ._presets import known_family_presets, resolve_builtin_preset
from ._types import (
    ContextPolicy,
    FamilyPreset,
    HarnessPolicy,
    ModelAdapter,
    ToolPolicy,
    build_protocol_for_preset,
)


def resolve_family_preset(identifier: str | None = None, *, family_id: str | None = None) -> FamilyPreset:
    target = family_id if family_id is not None else identifier
    return resolve_builtin_preset(target)


def build_harness_policy(
    *,
    model_name: str | None = None,
    family_id: str | None = None,
    protocol: Any = None,
    tool_delivery: str | None = None,
    resolution_source: str = "family_preset",
    adapter: ModelAdapter | None = None,
) -> HarnessPolicy:
    preset = resolve_family_preset(model_name, family_id=family_id)
    protocol_obj = build_protocol_for_preset(
        preset=preset,
        protocol=protocol,
        delivery=tool_delivery,
    )
    parser = protocol_obj.parser_factory()
    return HarnessPolicy(
        family_preset=preset,
        adapter=adapter,
        protocol=protocol_obj,
        parser=parser,
        tool_policy=preset.tool_policy,
        context_policy=preset.context_policy,
        resolution_source=resolution_source,
    )


__all__ = [
    "ModelAdapter",
    "ToolPolicy",
    "ContextPolicy",
    "HarnessPolicy",
    "FamilyPreset",
    "resolve_family_preset",
    "build_harness_policy",
    "known_family_presets",
]

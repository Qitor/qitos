"""Preset registry metadata and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass(frozen=True)
class PresetSpec:
    kind: str
    name: str
    factory: Callable[..., Any]
    description: str


class PresetRegistry:
    def __init__(self):
        self._items: Dict[str, PresetSpec] = {}

    def register(self, spec: PresetSpec) -> None:
        key = f"{spec.kind}:{spec.name}"
        if key in self._items:
            raise ValueError(f"Duplicate preset: {key}")
        self._items[key] = spec

    def get(self, kind: str, name: str) -> PresetSpec:
        key = f"{kind}:{name}"
        if key not in self._items:
            raise KeyError(f"Unknown preset: {key}")
        return self._items[key]

    def list(self, kind: str | None = None) -> list[PresetSpec]:
        values = list(self._items.values())
        if kind is None:
            return sorted(values, key=lambda x: (x.kind, x.name))
        return sorted([v for v in values if v.kind == kind], key=lambda x: x.name)


__all__ = ["PresetSpec", "PresetRegistry"]

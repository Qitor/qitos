"""Composable preset modules built on canonical contracts."""

from __future__ import annotations

from . import critics, memories, parsers, policies, search, toolkits
from .registry import PresetRegistry, PresetSpec


def build_registry() -> PresetRegistry:
    reg = PresetRegistry()
    reg.register(PresetSpec(kind="policy", name="react_arithmetic", factory=policies.ReActArithmeticPolicy, description="Arithmetic ReAct-style policy"))
    reg.register(PresetSpec(kind="parser", name="react_text", factory=parsers.react_parser, description="ReAct plain-text parser"))
    reg.register(PresetSpec(kind="parser", name="json", factory=parsers.json_parser, description="JSON Decision parser"))
    reg.register(PresetSpec(kind="parser", name="xml", factory=parsers.xml_parser, description="XML Decision parser"))
    reg.register(PresetSpec(kind="memory", name="window", factory=memories.window_memory, description="Window memory"))
    reg.register(PresetSpec(kind="memory", name="summary", factory=memories.summary_memory, description="Summary memory"))
    reg.register(PresetSpec(kind="memory", name="vector", factory=memories.vector_memory, description="Vector memory"))
    reg.register(PresetSpec(kind="search", name="greedy", factory=search.greedy_search, description="Greedy branch selector"))
    reg.register(PresetSpec(kind="critic", name="pass_through", factory=critics.pass_through_critic, description="No-op critic"))
    reg.register(PresetSpec(kind="toolkit", name="math", factory=toolkits.math_toolkit, description="Math function toolkit"))
    reg.register(PresetSpec(kind="toolkit", name="editor", factory=toolkits.editor_toolkit, description="Editor toolkit"))
    return reg


__all__ = [
    "PresetRegistry",
    "PresetSpec",
    "build_registry",
    "parsers",
    "memories",
    "search",
    "critics",
    "toolkits",
    "policies",
]

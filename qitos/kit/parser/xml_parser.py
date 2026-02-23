"""XML decision parser with configurable tag/keyword mapping."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from qitos.core.decision import Decision
from qitos.engine.parser import BaseParser
from qitos.kit.parser.parser_utils import (
    first_xml_text,
    norm,
    parse_xml_action,
    parse_xml_root,
)


class XmlDecisionParser(BaseParser[dict[str, Any]]):
    def __init__(
        self,
        *,
        thought_keys: Optional[Sequence[str]] = None,
        reflection_keys: Optional[Sequence[str]] = None,
        action_keys: Optional[Sequence[str]] = None,
        final_keys: Optional[Sequence[str]] = None,
        xml_think_tags: Optional[Sequence[str]] = None,
        xml_reflection_tags: Optional[Sequence[str]] = None,
        xml_action_tags: Optional[Sequence[str]] = None,
        xml_final_tags: Optional[Sequence[str]] = None,
    ):
        # Keep text-style keys configurable for API symmetry, even if XML parsers
        # primarily rely on XML tags.
        self.thought_keys = tuple(norm(x) for x in (thought_keys or ("thought", "thinking", "think", "rationale")))
        self.reflection_keys = tuple(norm(x) for x in (reflection_keys or ("reflection", "reflect", "selfreflection")))
        self.action_keys = tuple(norm(x) for x in (action_keys or ("action", "tool", "call")))
        self.final_keys = tuple(norm(x) for x in (final_keys or ("finalanswer", "final", "answer")))
        self.xml_think_tags = tuple(norm(x) for x in (xml_think_tags or ("think", "thought", "thinking", "rationale")))
        self.xml_reflection_tags = tuple(
            norm(x) for x in (xml_reflection_tags or ("reflection", "reflect", "self_reflection"))
        )
        self.xml_action_tags = tuple(norm(x) for x in (xml_action_tags or ("action", "tool", "call")))
        self.xml_final_tags = tuple(norm(x) for x in (xml_final_tags or ("final_answer", "final", "answer")))

    def parse(self, raw_output: Any, context: Optional[Dict[str, Any]] = None) -> Decision[dict[str, Any]]:
        if not isinstance(raw_output, str):
            raise ValueError("XML parser expects XML string output")
        text = raw_output.strip()
        if not text:
            raise ValueError("Empty XML output")

        root = parse_xml_root(text)
        mode = norm(root.attrib.get("mode", "")) if hasattr(root, "attrib") else ""
        thought = first_xml_text(root, self.xml_think_tags)
        reflection = first_xml_text(root, self.xml_reflection_tags)
        final_answer = first_xml_text(root, self.xml_final_tags)
        meta = {"reflection": reflection} if reflection else {}

        if mode == "wait":
            return Decision.wait(rationale=thought, meta=meta)
        if mode == "final":
            if not final_answer:
                raise ValueError("XML final mode requires final answer tag content")
            return Decision.final(answer=final_answer, rationale=thought, meta=meta)
        if mode == "act":
            action = parse_xml_action(root, self.xml_action_tags)
            if action is None:
                raise ValueError("XML act mode requires parseable action")
            return Decision.act(actions=[action], rationale=thought, meta=meta)

        if final_answer:
            return Decision.final(answer=final_answer, rationale=thought, meta=meta)
        action = parse_xml_action(root, self.xml_action_tags)
        if action is not None:
            return Decision.act(actions=[action], rationale=thought, meta=meta)
        raise ValueError("No parseable action/final answer found in XML output")


__all__ = ["XmlDecisionParser"]

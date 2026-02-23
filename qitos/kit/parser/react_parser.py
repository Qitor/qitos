"""ReAct-style text parser with configurable keyword mapping."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from qitos.core.decision import Decision
from qitos.engine.parser import BaseParser
from qitos.kit.parser.parser_utils import (
    extract_labeled_blocks,
    first_block_value,
    norm,
    parse_action_any,
)


class ReActTextParser(BaseParser[dict[str, Any]]):
    def __init__(
        self,
        *,
        thought_keys: Optional[Sequence[str]] = None,
        reflection_keys: Optional[Sequence[str]] = None,
        action_keys: Optional[Sequence[str]] = None,
        final_keys: Optional[Sequence[str]] = None,
    ):
        self.thought_keys = tuple(norm(x) for x in (thought_keys or ("thought", "thinking", "think", "rationale")))
        self.reflection_keys = tuple(norm(x) for x in (reflection_keys or ("reflection", "reflect", "selfreflection")))
        self.action_keys = tuple(norm(x) for x in (action_keys or ("action", "tool", "call")))
        self.final_keys = tuple(norm(x) for x in (final_keys or ("finalanswer", "final", "answer")))

    def parse(self, raw_output: Any, context: Optional[Dict[str, Any]] = None) -> Decision[dict[str, Any]]:
        if not isinstance(raw_output, str):
            raise ValueError("ReActTextParser expects string output")
        text = raw_output.strip()
        if not text:
            raise ValueError("Empty model output")

        blocks = extract_labeled_blocks(text)
        thought = first_block_value(blocks, self.thought_keys)
        reflection = first_block_value(blocks, self.reflection_keys)
        final_answer = first_block_value(blocks, self.final_keys)
        action_blob = first_block_value(blocks, self.action_keys)

        meta = {"reflection": reflection} if reflection else {}
        if final_answer:
            return Decision.final(answer=final_answer, rationale=thought, meta=meta)

        action = parse_action_any(action_blob or text)
        if action is not None:
            return Decision.act(actions=[action], rationale=thought, meta=meta)
        raise ValueError("No ReAct action/final answer found")


__all__ = ["ReActTextParser"]

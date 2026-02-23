"""JSON decision parser with configurable key mapping."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from qitos.core.decision import Decision
from qitos.engine.parser import BaseParser
from qitos.kit.parser.parser_utils import (
    extract_json_actions,
    first_dict_value,
    json_payload,
    norm,
)


class JsonDecisionParser(BaseParser[dict[str, Any]]):
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
        payload = json_payload(raw_output)
        thought = first_dict_value(payload, self.thought_keys)
        reflection = first_dict_value(payload, self.reflection_keys)
        mode = norm(str(payload.get("mode", "")))
        meta = {"reflection": reflection} if reflection else {}
        final_answer = (
            first_dict_value(payload, self.final_keys)
            or first_dict_value(payload, ("final_answer",))
            or first_dict_value(payload, ("answer",))
        )

        if mode == "wait":
            return Decision.wait(rationale=thought, meta=meta)
        if mode == "final":
            if not final_answer:
                raise ValueError("JSON final mode requires final_answer/answer")
            return Decision.final(answer=final_answer, rationale=thought, meta=meta)

        actions = extract_json_actions(payload)
        if actions:
            return Decision.act(actions=actions, rationale=thought, meta=meta)
        if final_answer:
            return Decision.final(answer=final_answer, rationale=thought, meta=meta)
        raise ValueError("Unsupported or missing decision fields in JSON output")


__all__ = ["JsonDecisionParser"]

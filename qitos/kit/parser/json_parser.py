"""JSON decision parser."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from qitos.core.decision import Decision
from qitos.engine.parser import BaseParser


class JsonDecisionParser(BaseParser[dict[str, Any]]):
    def parse(self, raw_output: Any, context: Optional[Dict[str, Any]] = None) -> Decision[dict[str, Any]]:
        payload: Dict[str, Any]
        if isinstance(raw_output, str):
            payload = json.loads(raw_output)
        elif isinstance(raw_output, dict):
            payload = raw_output
        else:
            raise ValueError("JsonDecisionParser expects dict or JSON string")

        mode = str(payload.get("mode", "")).strip()
        rationale = payload.get("rationale")
        meta = payload.get("meta") or {}

        if mode == "act":
            return Decision.act(actions=payload.get("actions") or [], rationale=rationale, meta=meta)
        if mode == "final":
            return Decision.final(answer=str(payload.get("final_answer")), rationale=rationale, meta=meta)
        if mode == "wait":
            return Decision.wait(rationale=rationale, meta=meta)
        raise ValueError(f"Unsupported decision mode: {mode}")


__all__ = ["JsonDecisionParser"]

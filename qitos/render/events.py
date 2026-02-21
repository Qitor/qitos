"""Structured render events for console and frontend consumption."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass
class RenderEvent:
    channel: str
    node: str
    step_id: int
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "node": self.node,
            "step_id": self.step_id,
            "payload": self.payload,
            "ts": self.ts,
        }


__all__ = ["RenderEvent"]

"""Minimal Tau-Bench types used by QitOS internal runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

RESPOND_ACTION_NAME = "respond"
RESPOND_ACTION_FIELD_NAME = "content"


@dataclass
class Action:
    name: str
    kwargs: Dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)


class Task:
    """Schema-tolerant task object compatible with vendored Tau task files."""

    def __init__(
        self,
        user_id: str,
        actions: List[Action],
        instruction: str,
        outputs: List[str],
        **extra: Any,
    ):
        self.user_id = user_id
        self.actions = actions
        self.instruction = instruction
        self.outputs = outputs
        self.extra = dict(extra)

    def model_dump(self) -> Dict[str, Any]:
        payload = {
            "user_id": self.user_id,
            "actions": [a.model_dump() for a in self.actions],
            "instruction": self.instruction,
            "outputs": list(self.outputs),
        }
        payload.update(self.extra)
        return payload

"""Canonical observation contract passed to Agent.reduce()."""

from __future__ import annotations

from collections.abc import ItemsView, Mapping, ValuesView
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List

from .tool_result import ToolResult


_FIELDS = frozenset({"step", "task", "state", "decision", "action_results", "env", "metadata"})
_MISSING = object()


@dataclass(init=False)
class Observation(dict):
    """One mutable authority with a legacy mapping projection for tool results.

    Attribute writes, item assignment, update and |= validate before mutation.
    Schema fields cannot be deleted; extension keys support pop/del/popitem.
    clear is rejected because step identity is required. Mapping action_results
    are compatibility snapshots; assign the field to update canonical results.
    Explicit serialization returns independent snapshots. Calling unbound dict
    mutators on this subclass is outside this contract.
    """

    step_id: int
    task: str
    state: Dict[str, Any]
    decision: Dict[str, Any] | None
    action_results: List[ToolResult]
    env: Dict[str, Any]
    metadata: Dict[str, Any]

    def __init__(
        self,
        step_id: int,
        task: str = "",
        state: Dict[str, Any] | None = None,
        decision: Dict[str, Any] | None = None,
        action_results: List[ToolResult] | None = None,
        env: Dict[str, Any] | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        self.update({
            "step": step_id, "task": task, "state": {} if state is None else state,
            "decision": decision, "action_results": [] if action_results is None else action_results,
            "env": {} if env is None else env, "metadata": {} if metadata is None else metadata,
        })

    def __getattr__(self, name: str) -> Any:
        key = "step" if name == "step_id" else name
        if key in _FIELDS:
            return dict.__getitem__(self, key)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        key = "step" if name == "step_id" else name
        if key not in _FIELDS:
            raise AttributeError(name)
        self[key] = value

    def __delattr__(self, name: str) -> None:
        self.__delitem__("step" if name == "step_id" else name)

    def __getitem__(self, key: str) -> Any:
        value = dict.__getitem__(self, "step" if key == "step_id" else key)
        if key == "action_results":
            return deepcopy([item.to_legacy_dict() for item in value])
        return value

    def __contains__(self, key: object) -> bool:
        return dict.__contains__(self, "step" if key == "step_id" else key)

    def __iter__(self) -> Iterator[str]:
        # Also makes dict(obs) use the public projection, not raw dict storage.
        return dict.__iter__(self)

    def get(self, key: str, default: Any = None) -> Any:
        return self[key] if key in self else default

    def items(self) -> Any:
        return ItemsView(self)

    def values(self) -> Any:
        return ValuesView(self)

    def __setitem__(self, key: str, value: Any) -> None:
        self.update({key: value})

    def update(self, *args: Any, **kwargs: Any) -> None:
        if len(args) > 1:
            raise TypeError("update accepts at most one positional argument")
        incoming = dict(args[0]) if args else {}
        incoming.update(kwargs)
        if "step" in incoming and "step_id" in incoming:
            # Validate both aliases, including bool versus int equality.
            self._validate("step", incoming["step"])
            self._validate("step", incoming["step_id"])
            if incoming["step"] != incoming["step_id"]:
                raise ValueError("step and step_id conflict")
        if "step_id" in incoming:
            incoming["step"] = incoming.pop("step_id")
        prepared = {key: self._validate(key, value) for key, value in incoming.items()}
        dict.update(self, prepared)

    @staticmethod
    def _validate(key: str, value: Any) -> Any:
        if not isinstance(key, str):
            raise TypeError("observation keys must be strings")
        if key == "step" and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise ValueError("step must be a non-negative integer")
        if key == "task" and not isinstance(value, str):
            raise TypeError("task must be a string")
        if key in {"state", "env", "metadata"} or (key == "decision" and value is not None):
            if not isinstance(value, Mapping):
                raise TypeError(f"{key} must be a mapping")
            value = dict(value)
        if key == "action_results":
            if not isinstance(value, (list, tuple)):
                raise TypeError("action_results must be a sequence")
            value = [ToolResult.from_value(item) for item in value]
        return deepcopy(value)

    def __delitem__(self, key: str) -> None:
        if key in _FIELDS or key == "step_id":
            raise ValueError(f"cannot delete observation schema field {key}")
        dict.__delitem__(self, key)

    def pop(self, key: str, default: Any = _MISSING) -> Any:
        if key in self:
            value = self[key]
            del self[key]
            return value
        if default is _MISSING:
            raise KeyError(key)
        return default

    def popitem(self) -> tuple[str, Any]:
        key = next(reversed(self))
        return key, self.pop(key)

    def clear(self) -> None:
        raise ValueError("cannot clear required observation identity")

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key not in self:
            self[key] = default
        return self[key]

    def __ior__(self, other: Any) -> Observation:
        self.update(other)
        return self

    def __or__(self, other: Any) -> dict:
        return self.to_legacy_dict() | dict(other)

    def __ror__(self, other: Any) -> dict:
        return dict(other) | self.to_legacy_dict()

    def copy(self) -> Observation:
        return self.from_value(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        payload = {key: dict.__getitem__(self, key) for key in self}
        payload["decision"] = self.decision or {}
        payload["action_results"] = [item.to_dict() for item in self.action_results]
        return deepcopy(payload)

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Explicit compatibility snapshot with flattened tool outputs."""
        payload = self.to_dict()
        payload["action_results"] = deepcopy([item.to_legacy_dict() for item in self.action_results])
        return payload

    @classmethod
    def from_value(cls, payload: Any) -> Observation:
        if isinstance(payload, Observation):
            return payload
        result = cls(step_id=0)
        if isinstance(payload, Mapping):
            result.update(payload)
        else:
            result.metadata = {"raw": payload}
        return result


__all__ = ["Observation"]

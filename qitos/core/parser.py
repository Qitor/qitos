"""Parser plugins that normalize model output into canonical Decision."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, Protocol, TypeVar

from .decision import Decision


ActionT = TypeVar("ActionT")


class Parser(Protocol, Generic[ActionT]):
    def parse(self, raw_output: Any, context: Optional[Dict[str, Any]] = None) -> Decision[ActionT]:
        """Parse raw output into a validated Decision."""


class BaseParser(ABC, Generic[ActionT]):
    @abstractmethod
    def parse(self, raw_output: Any, context: Optional[Dict[str, Any]] = None) -> Decision[ActionT]:
        """Parse raw output into Decision."""


class JsonDecisionParser(BaseParser[dict[str, Any]]):
    """Parse JSON payloads into Decision.

    Supported shapes:
    - {"mode":"final","final_answer":"..."}
    - {"mode":"act","actions":[{"name":"tool","args":{...}}]}
    - {"mode":"wait"}
    """

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
            actions = payload.get("actions") or []
            return Decision.act(actions=actions, rationale=rationale, meta=meta)
        if mode == "final":
            answer = payload.get("final_answer")
            return Decision.final(answer=str(answer), rationale=rationale, meta=meta)
        if mode == "wait":
            return Decision.wait(rationale=rationale, meta=meta)

        raise ValueError(f"Unsupported decision mode: {mode}")


class ReActTextParser(BaseParser[dict[str, Any]]):
    """Parse ReAct-like plain text into Decision."""

    action_pattern = re.compile(r"Action:\s*([a-zA-Z0-9_\.]+)\((.*)\)")

    def parse(self, raw_output: Any, context: Optional[Dict[str, Any]] = None) -> Decision[dict[str, Any]]:
        if not isinstance(raw_output, str):
            raise ValueError("ReActTextParser expects string output")

        text = raw_output.strip()
        if "Final Answer:" in text:
            answer = text.split("Final Answer:", 1)[1].strip()
            return Decision.final(answer=answer)

        match = self.action_pattern.search(text)
        if not match:
            raise ValueError("No ReAct action/final answer found")

        name = match.group(1)
        args_text = match.group(2).strip()
        args: Dict[str, Any] = {}
        if args_text:
            for item in [x.strip() for x in args_text.split(",") if x.strip()]:
                if "=" not in item:
                    raise ValueError(f"Malformed action arg: {item}")
                k, v = [x.strip() for x in item.split("=", 1)]
                args[k] = self._coerce(v)

        return Decision.act(actions=[{"name": name, "args": args}])

    def _coerce(self, value: str) -> Any:
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        if value.startswith("'") and value.endswith("'"):
            return value[1:-1]
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        if re.fullmatch(r"-?\d+\.\d+", value):
            return float(value)
        if value.lower() in {"true", "false"}:
            return value.lower() == "true"
        return value


class XmlDecisionParser(BaseParser[dict[str, Any]]):
    """Parse simple XML decision payloads into Decision."""

    def parse(self, raw_output: Any, context: Optional[Dict[str, Any]] = None) -> Decision[dict[str, Any]]:
        if not isinstance(raw_output, str):
            raise ValueError("XmlDecisionParser expects XML string")

        root = ET.fromstring(raw_output)
        if root.tag != "decision":
            raise ValueError("Root tag must be <decision>")

        mode = root.attrib.get("mode", "").strip()

        if mode == "final":
            answer_node = root.find("final_answer")
            if answer_node is None or answer_node.text is None:
                raise ValueError("<final_answer> is required for final mode")
            return Decision.final(answer=answer_node.text.strip())

        if mode == "act":
            action_node = root.find("action")
            if action_node is None:
                raise ValueError("<action> is required for act mode")
            name = action_node.attrib.get("name", "").strip()
            args: Dict[str, Any] = {}
            for arg in action_node.findall("arg"):
                key = arg.attrib.get("name", "").strip()
                if not key:
                    continue
                args[key] = (arg.text or "").strip()
            return Decision.act(actions=[{"name": name, "args": args}])

        if mode == "wait":
            return Decision.wait()

        raise ValueError(f"Unsupported decision mode: {mode}")


__all__ = [
    "Parser",
    "BaseParser",
    "JsonDecisionParser",
    "ReActTextParser",
    "XmlDecisionParser",
]

"""ReAct text parser."""

from __future__ import annotations

import re
import ast
from typing import Any, Dict, Optional

from qitos.core.decision import Decision
from qitos.engine.parser import BaseParser
from qitos.kit.parser.func_parser import parse_first_action_invocation


class ReActTextParser(BaseParser[dict[str, Any]]):
    action_pattern = re.compile(r"Action(?:\s+\d+)?\s*:\s*([a-zA-Z0-9_\.]+)\((.*)\)", re.IGNORECASE)
    action_dict_pattern = re.compile(r"Action:\s*(\{.*\})", re.DOTALL)

    def parse(self, raw_output: Any, context: Optional[Dict[str, Any]] = None) -> Decision[dict[str, Any]]:
        if not isinstance(raw_output, str):
            raise ValueError("ReActTextParser expects string output")
        text = raw_output.strip()
        if "Final Answer:" in text:
            return Decision.final(answer=text.split("Final Answer:", 1)[1].strip())

        parsed = parse_first_action_invocation(text)
        if parsed is not None:
            return Decision.act(actions=[parsed])

        match = self.action_pattern.search(text)
        if match:
            name = match.group(1)
            args_text = match.group(2).strip()
            args = self._parse_args(args_text)
            return Decision.act(actions=[{"name": name, "args": args}])

        dict_match = self.action_dict_pattern.search(text)
        if dict_match:
            action_obj = self._parse_action_dict(dict_match.group(1).strip())
            if action_obj is not None:
                return Decision.act(actions=[action_obj])
        raise ValueError("No ReAct action/final answer found")

    def _parse_action_dict(self, action_text: str) -> Optional[Dict[str, Any]]:
        try:
            obj = ast.literal_eval(action_text)
        except Exception:
            return None
        if not isinstance(obj, dict):
            return None
        name = obj.get("name")
        args = obj.get("args", {})
        if not isinstance(name, str):
            return None
        if not isinstance(args, dict):
            args = {}
        return {"name": name, "args": args}

    def _parse_args(self, args_text: str) -> Dict[str, Any]:
        if not args_text:
            return {}
        try:
            node = ast.parse(f"f({args_text})", mode="eval")
            call = node.body
            if not isinstance(call, ast.Call):
                raise ValueError("Action args must parse as a function call")
            args: Dict[str, Any] = {}
            for kw in call.keywords:
                if kw.arg is None:
                    raise ValueError("Unsupported **kwargs in action args")
                args[kw.arg] = ast.literal_eval(kw.value)
            return args
        except Exception:
            parsed: Dict[str, Any] = {}
            for item in [x.strip() for x in args_text.split(",") if x.strip()]:
                if "=" not in item:
                    raise ValueError(f"Malformed action arg: {item}")
                k, v = [x.strip() for x in item.split("=", 1)]
                parsed[k] = self._coerce(v)
            return parsed

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


__all__ = ["ReActTextParser"]

"""XML decision parser."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional

from qitos.core.decision import Decision
from qitos.engine.parser import BaseParser


class XmlDecisionParser(BaseParser[dict[str, Any]]):
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
                if key:
                    args[key] = (arg.text or "").strip()
            return Decision.act(actions=[{"name": name, "args": args}])
        if mode == "wait":
            return Decision.wait()
        raise ValueError(f"Unsupported decision mode: {mode}")


__all__ = ["XmlDecisionParser"]

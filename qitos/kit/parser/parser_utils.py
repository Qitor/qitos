"""Shared parsing helpers for text/xml/json decision parsers."""

from __future__ import annotations

import ast
import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Sequence

from qitos.kit.parser.func_parser import parse_first_action_invocation


def norm(token: str) -> str:
    return re.sub(r"[\s_\-]+", "", token.strip().lower())


def extract_labeled_blocks(text: str) -> Dict[str, str]:
    pattern = re.compile(r"(?im)^\s*([A-Za-z][A-Za-z _-]{0,40})\s*:\s*")
    matches = list(pattern.finditer(text))
    blocks: Dict[str, str] = {}
    if not matches:
        return blocks
    for i, m in enumerate(matches):
        key = norm(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        val = text[start:end].strip()
        if key and val:
            blocks.setdefault(key, val)
    return blocks


def first_block_value(blocks: Dict[str, str], keys: Sequence[str]) -> Optional[str]:
    for key in keys:
        value = blocks.get(norm(key))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_action_any(blob: str) -> Optional[Dict[str, Any]]:
    if not isinstance(blob, str):
        return None
    text = blob.strip()
    if not text:
        return None

    parsed = parse_first_action_invocation(f"Action: {text}")
    if parsed is not None:
        return parsed
    parsed = parse_first_action_invocation(text)
    if parsed is not None:
        return parsed

    obj = parse_object_like(text)
    if isinstance(obj, dict):
        name = obj.get("name")
        args = obj.get("args", {})
        if isinstance(name, str):
            if not isinstance(args, dict):
                args = {}
            return {"name": name, "args": args}
    return None


def parse_object_like(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        return ast.literal_eval(text)
    except Exception:
        return None


def parse_xml_root(text: str) -> ET.Element:
    try:
        return ET.fromstring(text)
    except Exception:
        wrapped = f"<root>{text}</root>"
        return ET.fromstring(wrapped)


def first_xml_text(root: ET.Element, tags: Sequence[str]) -> Optional[str]:
    target = {norm(t) for t in tags}
    for node in root.iter():
        if node is root:
            continue
        if norm(node.tag) in target:
            content = "".join(node.itertext()).strip()
            if content:
                return content
    return None


def parse_xml_action(root: ET.Element, action_tags: Sequence[str]) -> Optional[Dict[str, Any]]:
    targets = {norm(t) for t in action_tags}
    for node in root.iter():
        if norm(node.tag) not in targets:
            continue
        name_attr = node.attrib.get("name", "").strip()
        if name_attr:
            args: Dict[str, Any] = {}
            for arg in node.findall(".//arg"):
                key = arg.attrib.get("name", "").strip()
                if key:
                    args[key] = "".join(arg.itertext()).strip()
            return {"name": name_attr, "args": args}
        body = "".join(node.itertext()).strip()
        if body:
            parsed = parse_action_any(body)
            if parsed is not None:
                return parsed
    return None


def json_payload(raw_output: Any) -> Dict[str, Any]:
    if isinstance(raw_output, dict):
        return raw_output
    if not isinstance(raw_output, str):
        raise ValueError("JSON parser expects dict or JSON string output")
    text = raw_output.strip()
    if not text:
        raise ValueError("Empty JSON output")
    try:
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError("JSON output must decode to object")
        return obj
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict):
                return obj
        raise ValueError("Invalid JSON output")


def first_dict_value(payload: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    norm_map: Dict[str, Any] = {norm(str(k)): v for k, v in payload.items()}
    for key in keys:
        value = norm_map.get(norm(str(key)))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_json_actions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions_val = payload.get("actions")
    if isinstance(actions_val, list):
        out: List[Dict[str, Any]] = []
        for item in actions_val:
            if isinstance(item, dict):
                name = item.get("name")
                args = item.get("args", {})
                if isinstance(name, str):
                    if not isinstance(args, dict):
                        args = {}
                    out.append({"name": name, "args": args})
            elif isinstance(item, str):
                parsed = parse_action_any(item)
                if parsed is not None:
                    out.append(parsed)
        if out:
            return out

    action_val = payload.get("action")
    if isinstance(action_val, dict):
        name = action_val.get("name")
        args = action_val.get("args", {})
        if isinstance(name, str):
            if not isinstance(args, dict):
                args = {}
            return [{"name": name, "args": args}]
    if isinstance(action_val, str):
        parsed = parse_action_any(action_val)
        if parsed is not None:
            return [parsed]
    return []


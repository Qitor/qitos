"""Robust function-invocation parsing helpers for agent outputs."""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple


_FUNC_PATTERN = re.compile(r"([A-Za-z_][A-Za-z0-9_\.]*)\s*\(")
_ACTION_MARKER = re.compile(r"Action(?:\s+\d+)?\s*:\s*", re.IGNORECASE)


def extract_function_calls(code_str: str) -> Iterator[Tuple[str, str, bool]]:
    """
    Extract function calls from text using balanced-parentheses scanning.

    Yields tuples:
    - func_name: tool/function name
    - arg_str: raw args segment inside call
    - complete: whether closing `)` was found
    """
    pos = 0
    length = len(code_str)
    while pos < length:
        m = _FUNC_PATTERN.search(code_str, pos)
        if not m:
            break

        func_name = m.group(1)
        start = m.end()  # position right after '('
        i = start
        depth = 1
        in_single_quote = False
        in_double_quote = False
        escape = False

        while i < length and depth > 0:
            c = code_str[i]
            if escape:
                escape = False
                i += 1
                continue

            if c == "\\":
                escape = True
                i += 1
                continue

            if c == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                i += 1
                continue
            if c == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                i += 1
                continue

            if not in_single_quote and not in_double_quote:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
            i += 1

        if depth == 0:
            yield func_name, code_str[start : i - 1].strip(), True
            pos = i
        else:
            # tolerate truncated output: emit best-effort tail args.
            yield func_name, code_str[start:].strip(), False
            break


def split_args_robust(arg_str: str) -> List[str]:
    """Split function args by top-level commas while respecting nested structures."""
    args: List[str] = []
    current: List[str] = []
    paren_level = 0
    square_level = 0
    curly_level = 0
    in_single_quote = False
    in_double_quote = False
    escape = False

    for c in arg_str:
        if escape:
            current.append(c)
            escape = False
            continue

        if c == "\\":
            current.append(c)
            escape = True
            continue

        if c == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(c)
            continue
        if c == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(c)
            continue

        if not in_single_quote and not in_double_quote:
            if c == "(":
                paren_level += 1
            elif c == ")":
                if paren_level > 0:
                    paren_level -= 1
            elif c == "[":
                square_level += 1
            elif c == "]":
                if square_level > 0:
                    square_level -= 1
            elif c == "{":
                curly_level += 1
            elif c == "}":
                if curly_level > 0:
                    curly_level -= 1
            elif c == "," and paren_level == 0 and square_level == 0 and curly_level == 0:
                item = "".join(current).strip()
                if item:
                    args.append(item)
                current = []
                continue

        current.append(c)

    tail = "".join(current).strip()
    if tail:
        args.append(tail)
    return args


def parse_kwargs_loose(arg_str: str) -> Dict[str, Any]:
    """Best-effort kwargs parser for function arguments."""
    kwargs: Dict[str, Any] = {}
    for item in split_args_robust(arg_str):
        if "=" not in item:
            continue
        key, raw_value = item.split("=", 1)
        k = key.strip()
        if not k:
            continue
        kwargs[k] = _parse_value_loose(raw_value.strip())
    return kwargs


def parse_first_action_invocation(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse first action function invocation from an LLM output blob.

    Supports:
    - Action: tool(a=1, b="x")
    - Action 1: tool(...)
    - Multi-line action payloads
    """
    for marker in _ACTION_MARKER.finditer(text):
        chunk = text[marker.end() :]
        for func_name, arg_str, _complete in extract_function_calls(chunk):
            return {"name": func_name, "args": parse_kwargs_loose(arg_str)}
    return None


def _parse_value_loose(value: str) -> Any:
    try:
        return ast.literal_eval(value)
    except Exception:
        pass
    try:
        return json.loads(value)
    except Exception:
        pass
    return value


__all__ = [
    "extract_function_calls",
    "split_args_robust",
    "parse_kwargs_loose",
    "parse_first_action_invocation",
]

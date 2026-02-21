"""Safe prompt rendering helpers."""

from __future__ import annotations

import re
from typing import Any, Mapping


_DOUBLE_BRACE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_SINGLE_BRACE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def render_prompt(
    template: str,
    values: Mapping[str, Any] | None = None,
    *,
    strict: bool = False,
    enable_single_brace: bool = True,
) -> str:
    """
    Safely render a prompt template.

    Supported placeholders:
    - ``{{name}}`` / ``{{ name }}``
    - ``{name}`` (optional compatibility path)

    This renderer never evaluates expressions and never raises on unrelated braces,
    e.g. ``{'name': 'tool'}``, unless strict mode is enabled and a matching
    placeholder key is missing.
    """
    text = str(template)
    vars_map = dict(values or {})

    def repl_double(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in vars_map:
            return str(vars_map[key])
        if strict:
            raise KeyError(key)
        return match.group(0)

    text = _DOUBLE_BRACE.sub(repl_double, text)

    if enable_single_brace:
        def repl_single(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in vars_map:
                return str(vars_map[key])
            if strict:
                raise KeyError(key)
            return match.group(0)

        text = _SINGLE_BRACE.sub(repl_single, text)

    return text


__all__ = ["render_prompt"]

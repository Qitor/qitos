"""Redaction-safe diagnostic values shared by stable core contracts.

The helpers in this module are deliberately conservative.  Diagnostics are
for remediation and correlation, not for reproducing an untrusted provider
payload or a host-local identifier.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Mapping


_SENSITIVE_KEY = re.compile(
    r"(?:authorization|proxy[_-]?authorization|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|password|passwd|secret|cookie|set[_-]?cookie|headers?|"
    r"provider[_-]?(?:payload|request|response)|request[_-]?body|response[_-]?body)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?:\bBearer\s+\S+|\bBasic\s+\S+|(?:token|password|passwd|secret|api[_-]?key)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
_POSIX_PATH = re.compile(r"(?:^|\s)/(?:Users|home|private|var|tmp|opt|srv|mnt|Volumes)(?:/|\b)")
_WINDOWS_PATH = re.compile(r"(?:^|\s)[A-Za-z]:\\")
_FILE_URI = re.compile(r"\bfile://", re.IGNORECASE)
_HOME_PATH = re.compile(r"(?:^|\s)~(?:/|\\)")
_LOCAL_ENDPOINT = re.compile(
    r"\b(?:https?|wss?)://(?:localhost|127(?:\.\d{1,3}){3}|0\.0\.0\.0|"
    r"10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?::\d+)?(?:/\S*)?",
    re.IGNORECASE,
)


def diagnostic_string_is_sensitive(value: str) -> bool:
    """Return whether a string must not cross a diagnostic boundary."""

    return any(
        pattern.search(value) is not None
        for pattern in (
            _SECRET_VALUE,
            _POSIX_PATH,
            _WINDOWS_PATH,
            _FILE_URI,
            _HOME_PATH,
            _LOCAL_ENDPOINT,
        )
    )


def redact_diagnostic_value(value: Any, *, max_depth: int = 8) -> Any:
    """Return a JSON-safe, recursively redacted diagnostic projection."""

    def visit(item: Any, depth: int) -> Any:
        if depth > max_depth:
            return "[redacted]"
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            return item if math.isfinite(item) else "[redacted]"
        if isinstance(item, str):
            if diagnostic_string_is_sensitive(item):
                return "[redacted]"
            return item[:256]
        if isinstance(item, Mapping):
            result: Dict[str, Any] = {}
            redacted_index = 0
            for raw_key, nested in item.items():
                if not isinstance(raw_key, str):
                    continue
                if _SENSITIVE_KEY.search(raw_key):
                    redacted_index += 1
                    result[f"[redacted_key_{redacted_index}]"] = "[redacted]"
                else:
                    result[raw_key[:64]] = visit(nested, depth + 1)
            return result
        if isinstance(item, (list, tuple)):
            return [visit(nested, depth + 1) for nested in item[:64]]
        return "[redacted]"

    return visit(value, 0)


def safe_diagnostic_text(value: Any, *, fallback: str) -> str:
    """Return bounded safe text, replacing untrusted/path-like input."""

    if not isinstance(value, str) or not value.strip():
        return fallback
    text = value.strip()
    if diagnostic_string_is_sensitive(text):
        return fallback
    return text[:256]


__all__ = [
    "diagnostic_string_is_sensitive",
    "redact_diagnostic_value",
    "safe_diagnostic_text",
]

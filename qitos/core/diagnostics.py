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
    r"(?:authorization|proxy[_-]?authorization|api[_-]?key|token|credential|"
    r"access[_-]?token|"
    r"refresh[_-]?token|password|passwd|secret|cookie|set[_-]?cookie|headers?|"
    r"provider[_-]?(?:payload|request|response)|request[_-]?body|response[_-]?body|"
    r"raw[_-]?(?:payload|request|response)|exception|traceback|stack[_-]?trace|"
    r"private[_-]?key)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?:\bBearer\s+\S+|\bBasic\s+\S+|"
    r"(?:authorization|cookie|headers?|token|password|passwd|secret|api[_-]?key|"
    r"aws[_-]?(?:access[_-]?key[_-]?id|secret[_-]?access[_-]?key))\s*[:=]\s*\S+|"
    r"\bsk-[A-Za-z0-9_-]{8,}|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|"
    r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b|"
    r"-----BEGIN\s+[A-Z0-9 ]*PRIVATE KEY-----)",
    re.IGNORECASE,
)
_POSIX_PATH = re.compile(
    r"(?:^|[\s(\"'=,:\[{])/(?!/)[A-Za-z0-9._~-][^\s,;'\"<>\]}]*"
)
_WINDOWS_PATH = re.compile(r"(?:^|[\s(\"'=,\[])[A-Za-z]:[\\/][^\s,;'\"<>]+")
_WINDOWS_UNC_PATH = re.compile(r"(?:^|[\s(\"'=,\[])\\\\[^\\\s]+\\[^\s,;'\"<>]+")
_FILE_URI = re.compile(r"\bfile://", re.IGNORECASE)
_HOME_PATH = re.compile(r"(?:^|[\s(\"'=,\[])~(?:[A-Za-z0-9._-]+)?(?:/|\\)")
_LOCAL_ENDPOINT = re.compile(
    r"(?:\b(?:https?|wss?|ssh|tcp)://)?(?:localhost|127(?:\.\d{1,3}){3}|0\.0\.0\.0|"
    r"\[?::1\]?|"
    r"10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?::\d+)?(?:/\S*)?|"
    r"\bunix://\S+",
    re.IGNORECASE,
)


def _diagnostic_key_is_sensitive(value: str) -> bool:
    return _diagnostic_key_is_secret(value) or bool(_diagnostic_string_categories(value))


def _diagnostic_key_is_secret(value: str) -> bool:
    return _SENSITIVE_KEY.search(value) is not None


def _diagnostic_string_categories(value: str) -> frozenset[str]:
    categories = set()
    for name, pattern in (
        ("secret", _SECRET_VALUE),
        ("absolute_posix_path", _POSIX_PATH),
        ("windows_path", _WINDOWS_PATH),
        ("windows_unc_path", _WINDOWS_UNC_PATH),
        ("file_uri", _FILE_URI),
        ("home_path", _HOME_PATH),
        ("local_endpoint", _LOCAL_ENDPOINT),
    ):
        if pattern.search(value) is not None:
            categories.add(name)
    return frozenset(categories)


def diagnostic_string_is_sensitive(value: str) -> bool:
    """Return whether a string must not cross a diagnostic boundary."""

    return bool(_diagnostic_string_categories(value))


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
                if _diagnostic_key_is_sensitive(raw_key):
                    redacted_index += 1
                    safe_key = f"[redacted_key_{redacted_index}]"
                    while safe_key in result:
                        redacted_index += 1
                        safe_key = f"[redacted_key_{redacted_index}]"
                    result[safe_key] = "[redacted]"
                else:
                    safe_key = raw_key[:64]
                    while safe_key in result:
                        safe_key = f"[duplicate_key_{len(result) + 1}]"
                    result[safe_key] = visit(nested, depth + 1)
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


__all__: list[str] = []

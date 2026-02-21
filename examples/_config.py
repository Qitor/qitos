"""Config helpers for examples."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml

from qitos.models import OpenAICompatibleModel

_ENV = re.compile(r"\$\{([A-Z0-9_]+)\}")


def load_yaml(path: str) -> Dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return os.getenv(key, "")

    expanded = _ENV.sub(repl, text)
    data = yaml.safe_load(expanded) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be mapping: {path}")
    return data


def build_model(cfg: Dict[str, Any]) -> OpenAICompatibleModel:
    model_cfg = cfg.get("model") or {}
    model_name = str(model_cfg.get("model_name") or model_cfg.get("model") or "Qwen/Qwen3-8B")
    return OpenAICompatibleModel(
        model=model_name,
        api_key=str(model_cfg.get("api_key", "")) or None,
        base_url=str(model_cfg.get("base_url", "")) or None,
        temperature=float(model_cfg.get("temperature", 0.2)),
        max_tokens=int(model_cfg.get("max_tokens", 2048)),
    )


def case_cfg(cfg: Dict[str, Any], name: str) -> Dict[str, Any]:
    value = cfg.get(name) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{name}' must be a mapping")
    return value

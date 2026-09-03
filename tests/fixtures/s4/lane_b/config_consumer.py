"""Executable, secret-free Lane A/G5 consumer contract for S4 Lane B."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Mapping

from qitos.models.codec import ProviderCapabilities
from qitos.models.provider import ProviderAdapter


HANDOFF = Path(__file__).with_name("config-handoff.json")
_FORBIDDEN_KEYS = frozenset(
    {"authorization", "api_key", "credential", "headers", "password", "token"}
)


def _assert_secret_free(value: Any, path: str = "config") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise ValueError(f"{path} contains forbidden secret material")
            _assert_secret_free(nested, f"{path}.field")
    elif isinstance(value, list):
        for nested in value:
            _assert_secret_free(nested, f"{path}.item")


def consume_handoff(path: Path = HANDOFF) -> dict[str, Any]:
    """Validate public assembly inputs and instantiate the declared adapter."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    _assert_secret_free(payload)
    provider = payload["provider"]
    module_name, class_name = provider["adapter_import"].split(":", 1)
    adapter = getattr(importlib.import_module(module_name), class_name)()
    if not isinstance(adapter, ProviderAdapter):
        raise TypeError("configured adapter does not satisfy ProviderAdapter")
    capabilities = ProviderCapabilities.from_model(adapter)
    if capabilities.target.api_mode != provider["api_mode"]:
        raise ValueError("configured API mode does not match adapter declaration")
    if adapter.qitos_provider_codec().codec_id != provider["codec_id"]:
        raise ValueError("configured codec does not match adapter declaration")
    if payload["budgets"]["hidden_retries"] != 0:
        raise ValueError("hidden retries must remain zero")
    return {
        "logical_profile_id": provider["logical_profile_id"],
        "target": capabilities.target.to_dict(),
        "capabilities": capabilities.to_dict(),
        "component_ids": dict(payload["context"]),
        "continuation_resolver": payload["continuation_resolver"],
    }


if __name__ == "__main__":
    print(json.dumps(consume_handoff(), sort_keys=True))

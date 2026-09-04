"""SDK retries cannot create unaccounted requests below provider admission."""
import sys
from types import SimpleNamespace

import pytest

from qitos.models.openai import OpenAICompatibleModel


def test_sdk_client_disables_hidden_transport_retries(monkeypatch):
    attempts, options = [], []

    class Client:
        def __init__(self, **kwargs):
            options.append(kwargs)
            self.chat = SimpleNamespace(completions=self)

        def create(self, **kwargs):
            attempts.append(kwargs)
            raise TimeoutError("controlled timeout")

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Client))
    model = OpenAICompatibleModel(model="offline", api_key="fixture", base_url="https://fixture.invalid/v1")
    with pytest.raises(TimeoutError):
        model.call_raw([{"role": "user", "content": "request"}])
    assert len(attempts) == 1
    assert options[0].get("max_retries") == 0

"""Offline matrix through built-in adapter implementations and real codecs."""
import json
import sys
from types import SimpleNamespace as NS

import pytest

from qitos.models.anthropic import AnthropicModel
from qitos.models.codec import ProviderFailure
from qitos.models.gemini import GeminiModel
from qitos.models.litellm import LiteLLMModel
from qitos.models.local import LMStudioModel, OllamaGenerateModel, OllamaModel, VLLMModel
from qitos.models.openai import AzureOpenAIModel


@pytest.mark.parametrize('kind', [LiteLLMModel, GeminiModel, OllamaModel,
                                  OllamaGenerateModel, LMStudioModel, VLLMModel])
@pytest.mark.parametrize('broken', [False, True])
def test_public_fallback(kind, broken, monkeypatch):
    import requests
    import urllib.request
    result = {
        'message': {'content': 'ordinary'}, 'response': 'ordinary',
        'choices': [{'message': {'content': 'ordinary'}, 'finish_reason': 'stop'}],
        'candidates': [{'content': {'parts': [{'text': 'ordinary'}]}}],
    }
    responses = []

    class Response:
        def __init__(self):
            self.closed = 0
            responses.append(self)

        def raise_for_status(self):
            pass

        def json(self):
            return result

        def read(self):
            return json.dumps(result).encode()

        def close(self):
            self.closed += 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    def dispatch(*args, **kwargs):
        if broken:
            raise ConnectionError('private')
        return Response()

    def completion(**kwargs):
        if broken:
            raise ConnectionError('private')
        return result

    monkeypatch.setattr(requests, 'post', dispatch)
    monkeypatch.setattr(urllib.request, 'urlopen', dispatch)
    monkeypatch.setitem(sys.modules, 'litellm', NS(completion=completion))
    options = {'model': 'offline', 'max_tokens': 10240}
    if kind in {GeminiModel, LiteLLMModel}:
        options['api_key'] = 'offline'
    if kind in {OllamaModel, OllamaGenerateModel}:
        options.pop('max_tokens')
    model = kind(**options)
    assert model.qitos_provider_capabilities()['supports_streaming'] is False
    if broken:
        with pytest.raises(ProviderFailure):
            list(model.stream([{'role': 'user', 'content': 'test'}]))
    else:
        chunks = list(model.stream([{'role': 'user', 'content': 'test'}]))
        assert len(chunks) == 1 and chunks[0].done
        assert chunks[0].text == 'ordinary'
        assert all(response.closed == 1 for response in responses)


@pytest.mark.parametrize('broken', [False, True])
def test_azure_inherited_stream(monkeypatch, broken):
    import openai
    captured = []
    closed = []

    class Client:
        def __init__(self, **kwargs):
            captured.append(kwargs)
            self.chat = NS(completions=self)

        def create(self, **kwargs):
            captured.append(kwargs)
            if broken:
                raise ConnectionError('private')
            return iter([NS(choices=[NS(delta=NS(content='ok'), finish_reason='stop')], usage=None)])

        def close(self):
            closed.append(True)

    monkeypatch.setattr(openai, 'AzureOpenAI', Client)
    model = AzureOpenAIModel(deployment='offline', api_key='offline', endpoint='https://offline.invalid',
                             api_version='fixture', max_tokens=16384)
    if broken:
        with pytest.raises(ProviderFailure):
            list(model.stream([]))
    else:
        assert list(model.stream([]))[-1].done
    assert captured[0]['azure_endpoint'] == 'https://offline.invalid'
    assert captured[0]['api_version'] == 'fixture'
    assert captured[0]['max_retries'] == 0
    assert captured[1]['model'] == 'offline'
    assert captured[1]['max_tokens'] == 16384
    assert closed == [True]


@pytest.mark.parametrize('truncated', [False, True])
def test_native_anthropic_tools(monkeypatch, truncated):
    import requests
    closed = []
    events = [
        {'type': 'message_start', 'message': {'usage': {'input_tokens': 2}}},
        {'type': 'content_block_start', 'index': 0,
         'content_block': {'type': 'tool_use', 'id': 'one', 'name': 'add', 'input': {}}},
        {'type': 'content_block_delta', 'index': 0,
         'delta': {'type': 'input_json_delta', 'partial_json': '{"a":2}'}},
    ]
    if not truncated:
        events += [{'type': 'content_block_stop', 'index': 0},
                   {'type': 'message_delta', 'delta': {'stop_reason': 'tool_use'},
                    'usage': {'output_tokens': 3}}, {'type': 'message_stop'}]
    response = NS(raise_for_status=lambda: None,
                  iter_lines=lambda **kw: iter('data: '+json.dumps(event) for event in events),
                  close=lambda: closed.append(True))
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: response)
    model = AnthropicModel(api_key='offline')
    if truncated:
        with pytest.raises(ProviderFailure):
            model.qitos_stream_transport({'messages': []})
    else:
        raw = model.qitos_stream_transport({'messages': []})
        assert raw['stop_reason'] == 'tool_use'
        assert raw['content'][0]['input'] == {'a': 2}
        assert raw['usage'] == {'input_tokens': 2, 'output_tokens': 3}
    assert closed == [True]

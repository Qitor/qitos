"""R1-DX1: canonical YAML reaches the existing extension boundary."""
from pathlib import Path

import pytest
import yaml

from qitos.config import build_agent_composition, load_agent_config
from qitos.config.errors import ConfigSchemaError, CompositionError
from qitos.core.context import DeclaredContextBudgetPolicy
from qitos.kit.context.compaction import ClosedExchangeWindowCompactor


SOURCE = Path(__file__).parents[1] / 'examples/v5/r1_b_memory_context/agent.yaml'


def load(tmp_path, context):
    raw = yaml.safe_load(SOURCE.read_text())
    raw['context'] = context
    raw['memory'] = {}
    target = tmp_path / 'agent.yaml'
    target.write_text(yaml.safe_dump(raw))
    return load_agent_config(target)


def test_yaml_roundtrip_digest(tmp_path):
    config = load(tmp_path, {'budget_policy': 'budget', 'allow_codec_loss': True})
    assert dict(config.context) == {'budget_policy': 'budget', 'allow_codec_loss': True}
    target = tmp_path / 'canonical.yaml'
    target.write_text(yaml.safe_dump(config.to_dict()))
    restored = load_agent_config(target)
    assert restored.to_dict() == config.to_dict()
    assert restored.digest() == config.digest()


@pytest.mark.parametrize('value', ['true', 1, None, [], {}])
def test_loss_requires_boolean(tmp_path, value):
    with pytest.raises(ConfigSchemaError):
        load(tmp_path, {'allow_codec_loss': value})


@pytest.mark.parametrize('value', [True, 1, None, [], {}, ''])
def test_policy_requires_name(tmp_path, value):
    with pytest.raises(ConfigSchemaError):
        load(tmp_path, {'budget_policy': value})


def test_unknown_field_rejected(tmp_path):
    with pytest.raises(ConfigSchemaError):
        load(tmp_path, {'allow_magic_loss': True})


@pytest.mark.parametrize('registry', [{}, {'budget': object()}])
def test_missing_policy_fails_before_request(tmp_path, registry):
    config = load(tmp_path, {'budget_policy': 'budget'})
    class NoRequests:
        model = 'offline'
        def call_raw(self, *args, **kwargs):
            raise AssertionError('must fail before request')
    with pytest.raises(CompositionError):
        build_agent_composition(config, model_override=NoRequests(), extensions={
            'closed_window': ClosedExchangeWindowCompactor, **registry,
        })


def test_policy_resolves_without_loss_optin(tmp_path):
    config = load(tmp_path, {'budget_policy': 'budget'})
    from qitos.config._extensions import resolve_extensions
    services, _, _ = resolve_extensions(config, {
        'budget': DeclaredContextBudgetPolicy,
        'closed_window': ClosedExchangeWindowCompactor,
    })
    assert isinstance(services['context_budget_policy'], DeclaredContextBudgetPolicy)
    assert not services.get('allow_codec_loss', False)

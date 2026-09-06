"""Custom policies use the same owned composition and Session runtime."""
from dataclasses import dataclass, replace

import pytest

from qitos.config import SessionConfig, build_agent_composition
from qitos.config.errors import CompositionError
from qitos.core.agent_module import AgentModule
from qitos.core.state import StateSchema
from qitos.core.tool_registry import ToolRegistry
from test_s4_lane_a_public_authoring import _config, _FinalModel, _PauseAfterFirstStep


@dataclass
class ResearchState(StateSchema):
    rounds: int = 0


class ResearchAgent(AgentModule):
    def init_state(self, task, **kwargs):
        return ResearchState(task=task)

    def reduce(self, state, observation, decision):
        state.rounds += 1
        return state


def factory(*, config, model, tool_registry, protocol, parser):
    return ResearchAgent(llm=model, tool_registry=tool_registry,
                         model_protocol=protocol.id, model_parser=parser)


def test_factory_uses_composed_resources_and_canonical_loop(tmp_path):
    model = _FinalModel()
    with build_agent_composition(_config(tmp_path), model_override=model,
                                 agent_factory=factory) as composition:
        assert composition.agent.llm is composition.model is model
        assert composition.agent.tool_registry is composition.tool_registry
        assert composition.agent.name == composition.config.name
        assert composition.agent.config['agent_config_digest'] == composition.config.digest()
        result = composition.session('research').run()
        assert result.state.rounds == 1
        assert result.state.final_result == 'done'


@pytest.mark.parametrize('binding', ['llm', 'tool_registry', 'model_parser', 'model_protocol', 'policy'])
def test_incompatible_factory_binding_is_not_silently_replaced(tmp_path, binding):
    def invalid(**kwargs):
        agent = factory(**kwargs)
        if binding == 'policy':
            agent.config['tool_use_policy'] = 'disabled'
        else:
            value = ToolRegistry() if binding == 'tool_registry' else object()
            setattr(agent, binding, value)
        return agent

    with pytest.raises(CompositionError, match='factory'):
        build_agent_composition(_config(tmp_path), model_override=_FinalModel(),
                                agent_factory=invalid)


@pytest.mark.parametrize('mode', ['raise', 'wrong_return'])
def test_factory_failure_closes_owned_resources_without_echo(tmp_path, monkeypatch, mode):
    closed = []

    class OwnedModel(_FinalModel):
        def close(self):
            closed.append('model')

    monkeypatch.setattr('qitos.config.builder.build_model', lambda *a, **k: OwnedModel())

    def invalid(**kwargs):
        if mode == 'raise':
            raise RuntimeError('PRIVATE_FACTORY_VALUE')
        return object()

    with pytest.raises(CompositionError) as error:
        build_agent_composition(_config(tmp_path), agent_factory=invalid)
    assert closed == ['model']
    assert 'PRIVATE_FACTORY_VALUE' not in str(error.value)


def test_non_callable_rejected_before_resources(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('resources constructed')
    monkeypatch.setattr('qitos.config.builder.build_model', forbidden)
    with pytest.raises(CompositionError):
        build_agent_composition(_config(tmp_path), agent_factory=42)


def test_required_tool_can_be_declared_by_custom_factory(tmp_path):
    from qitos.core.function_tool_decorator import function_tool

    @function_tool(read_only=True)
    def evidence():
        return "checked"

    def populated(**kwargs):
        kwargs['tool_registry'].register(evidence)
        return factory(**kwargs)

    config = replace(_config(tmp_path), tool_use_policy='required_before_final')
    with build_agent_composition(config, model_override=_FinalModel(),
                                 agent_factory=populated) as composition:
        assert composition.tool_registry.get('evidence').execute({}) == 'checked'
    with pytest.raises(CompositionError, match='at least one'):
        build_agent_composition(config, model_override=_FinalModel(), agent_factory=factory)


def test_custom_state_survives_new_composition_restore(tmp_path):
    class ContinueModel(_FinalModel):
        def call_raw(self, messages, **options):
            return {'choices': [{'message': {'content': 'Thought: continue\nAction: inspect()'}}]}

    from qitos.core.function_tool_decorator import function_tool

    @function_tool(read_only=True)
    def inspect():
        return 'evidence'

    def policy(**kwargs):
        kwargs['tool_registry'].register(inspect)
        return factory(**kwargs)

    base = _config(tmp_path)
    config = replace(base, lifecycle={'policy': 'pause'}, runtime=replace(
        base.runtime, session=SessionConfig(store='sqlite', path=str(tmp_path / 'sessions.db'))))
    with build_agent_composition(config, model_override=ContinueModel(), agent_factory=policy,
                                 extensions={'pause': _PauseAfterFirstStep}) as first:
        session = first.session('research')
        session.run()
        identity = session.session_id.value
    with build_agent_composition(config, model_override=_FinalModel(), agent_factory=policy,
                                 extensions={'pause': _PauseAfterFirstStep}) as second:
        result = second.restore(identity).run()
        assert isinstance(result.state, ResearchState)
        assert result.state.rounds == 2

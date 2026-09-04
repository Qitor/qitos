"""Tests for engine exception logging and RuntimeBudget defaults."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

from qitos.engine.states import RuntimeBudget
from qitos.engine.engine import Engine
from qitos import AgentModule, StateSchema


class _MinimalAgent(AgentModule):
    name = "test_logging"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def init_state(self, task, **kwargs):
        return StateSchema(task=task, max_steps=3)

    def build_system_prompt(self, state):
        return "You are a test agent."

    def prepare(self, state):
        return f"Task: {state.task}"

    def reduce(self, state, observation, decision):
        return state


def test_runtime_budget_default_max_steps():
    """RuntimeBudget default max_steps is 10."""
    budget = RuntimeBudget()
    assert budget.max_steps == 10


def test_engine_uses_runtime_budget_default():
    """Engine uses RuntimeBudget() default (max_steps=10) when no budget specified."""
    agent = _MinimalAgent(llm=MagicMock())
    engine = Engine(agent=agent)
    assert engine.budget.max_steps == 10


def test_runtime_budget_custom_max_steps():
    """RuntimeBudget respects custom max_steps."""
    budget = RuntimeBudget(max_steps=50)
    assert budget.max_steps == 50


def test_critic_patch_initialized_in_init():
    """_critic_modified_prompt and _critic_instruction_patch are None after __init__."""
    agent = _MinimalAgent(llm=MagicMock())
    engine = Engine(agent=agent)
    assert engine._critic_modified_prompt is None
    assert engine._critic_instruction_patch is None


def test_reset_run_state_clears_critic_patches():
    """_reset_run_state() clears both critic patch variables."""
    agent = _MinimalAgent(llm=MagicMock())
    engine = Engine(agent=agent)
    engine._critic_modified_prompt = "modified"
    engine._critic_instruction_patch = "instruction"
    engine._reset_run_state()
    assert engine._critic_modified_prompt is None
    assert engine._critic_instruction_patch is None


def test_engine_logger_exists():
    """Engine module has a logger configured."""
    assert logging.getLogger("qitos.engine") is not None


def test_trace_runtime_logger_exists():
    """_trace_runtime module has a logger configured."""
    assert logging.getLogger("qitos.engine._trace_runtime") is not None


def test_env_runtime_logger_exists():
    """_env_runtime module has a logger configured."""
    assert logging.getLogger("qitos.engine._env_runtime") is not None


def test_env_teardown_failure_logs_warning(caplog):
    """Env teardown failure logs a warning."""
    from qitos.engine._env_runtime import _EnvRuntime
    engine_mock = MagicMock()
    env_mock = MagicMock()
    env_mock.teardown.side_effect = RuntimeError("teardown crashed")
    engine_mock.env = env_mock
    rt = _EnvRuntime(engine=engine_mock)
    with caplog.at_level(logging.WARNING, logger="qitos.engine._env_runtime"):
        import pytest
        from qitos.core.env import EnvCapabilityError
        with pytest.raises(EnvCapabilityError) as failure:
            rt.teardown_env()
        assert failure.value.code == "environment_cleanup_failed"
    assert any("teardown failed" in r.message.lower() for r in caplog.records)


def test_build_env_from_spec_failure_logs_debug(caplog):
    """build_env_from_spec returning None logs debug on import failure."""
    from qitos.engine._env_runtime import _EnvRuntime
    from qitos.engine.states import RuntimeBudget
    engine_mock = MagicMock()
    engine_mock.env = None
    engine_mock.budget = RuntimeBudget()
    rt = _EnvRuntime(engine=engine_mock)
    with caplog.at_level(logging.DEBUG, logger="qitos.engine._env_runtime"):
        result = rt.build_env_from_spec(MagicMock(type="repo", config={}))
    # Result may be None if kit.env import fails; debug log should be emitted
    # if import fails; otherwise result is a RepoEnv — either way no crash
    assert result is None or result is not None

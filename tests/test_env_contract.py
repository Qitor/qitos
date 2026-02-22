from __future__ import annotations

from qitos.core import Env, EnvObservation, EnvSpec, EnvStepResult


class _DummyEnv(Env):
    def __init__(self):
        self.closed = False
        self.counter = 0

    def reset(self, task=None, workspace=None, **kwargs):
        self.counter = 0
        return EnvObservation(data={"event": "reset", "task": task, "workspace": workspace})

    def observe(self, state=None):
        return EnvObservation(data={"event": "observe", "counter": self.counter, "state": state})

    def step(self, action, state=None):
        self.counter += 1
        done = self.counter >= 2
        return EnvStepResult(
            observation=EnvObservation(data={"event": "step", "action": action, "counter": self.counter}),
            done=done,
            reward=float(self.counter),
            info={"state": state},
        )

    def close(self):
        self.closed = True


def test_env_spec_defaults():
    spec = EnvSpec(type="repo")
    assert spec.type == "repo"
    assert spec.config == {}
    assert spec.required_tools == []
    assert spec.capabilities == []


def test_env_contract_lifecycle_and_terminal_default():
    env = _DummyEnv()
    env.setup(task="fix bug", workspace="/tmp/work")
    assert env.health_check().get("ok") is True
    obs0 = env.reset(task="fix bug", workspace="/tmp/work")
    assert obs0.data["event"] == "reset"
    assert obs0.data["task"] == "fix bug"

    obs1 = env.observe(state={"step": 0})
    assert obs1.data["event"] == "observe"
    assert obs1.data["counter"] == 0

    r1 = env.step(action={"name": "noop"}, state={"step": 1})
    assert r1.done is False
    assert env.is_terminal(last_result=r1) is False

    r2 = env.step(action={"name": "noop"}, state={"step": 2})
    assert r2.done is True
    assert env.is_terminal(last_result=r2) is True

    env.teardown()
    assert env.closed is True

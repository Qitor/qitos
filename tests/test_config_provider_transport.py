"""Configured AgentConfig to provider-transport boundary regressions."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from qitos.config import FakeCredentialResolver, load_agent_config
from qitos.config.builder import build_agent_composition
from qitos.core.session import SessionContractError, SessionErrorCode
from qitos.engine import Engine
from qitos.engine.runtime import LifecyclePolicy
from qitos.engine.work_runtime import DurableWorkRuntime, WorkDispatch
from qitos.kit.env import HostEnv


class _HoldingHandle:
    def __init__(self, worker_ref: str) -> None:
        self.worker_ref = worker_ref

    def add_terminal_callback(self, callback: Any) -> None:
        self.callback = callback

    def request_cancel(self) -> bool:
        return False


class _HoldingScheduler:
    scheduler_id = "tests.holding_scheduler"

    def __init__(self) -> None:
        self.requests: list[WorkDispatch] = []

    def dispatch(self, request: WorkDispatch) -> _HoldingHandle:
        self.requests.append(request)
        return _HoldingHandle(f"holding:{request.operation_id}")

    def reattach(
        self, request: WorkDispatch, worker_ref: str
    ) -> _HoldingHandle | None:
        _ = request, worker_ref
        return None

    def close(self) -> None:
        return None


def _config_text(profile: str, option_name: str, option_value: bool) -> str:
    rendered = "true" if option_value else "false"
    return f"""
schema: qitos.agent
agent:
  name: {profile}
  protocol: react_text_v1
  parser: auto
model:
  provider: openai_compatible
  model: {profile}-model
  base_url: https://example.invalid/v1
  credential:
    ref: fake-{profile}
  api_mode: chat_completions
  request:
    temperature: 0
    max_tokens: 10240
    timeout_seconds: 180
    retries: 0
    extra_body:
      chat_template_kwargs:
        {option_name}: {rendered}
        nested:
          flags: [true, false]
tools:
  preset: none
  include: []
  options: {{}}
  policy: disabled
runtime:
  environment:
    type: unsafe_host
    workspace: .
  session:
    enabled: true
    store: memory
  trajectory:
    enabled: false
    output: ./runs
    privacy: private
budgets:
  max_steps: 2
  max_runtime_seconds: 60
  max_requests: 12
dataset:
  - task: return a final answer
"""


@pytest.mark.parametrize(
    ("profile", "option_name", "option_value"),
    [
        ("sii-dsv4", "thinking", True),
        ("sii-glm-5-2", "enable_thinking", False),
        ("sii-qwen3-8-27b", "enable_thinking", False),
    ],
)
def test_canonical_composition_session_request_view_and_transport_share_one_json_boundary(
    tmp_path: Path,
    profile: str,
    option_name: str,
    option_value: bool,
) -> None:
    path = tmp_path / f"{profile}.yaml"
    path.write_text(
        _config_text(profile, option_name, option_value),
        encoding="utf-8",
    )
    config = load_agent_config(path)
    original_digest = config.digest()
    original_canonical = config.canonical_json()
    composition = build_agent_composition(
        config,
        credential_resolver=FakeCredentialResolver(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    captured: list[dict[str, Any]] = []

    def fake_call_raw(messages: Any, **options: Any) -> dict[str, Any]:
        assert isinstance(messages, list)
        captured.append(options)
        return {
            "choices": [
                {
                    "message": {"content": "Final Answer: complete"},
                    "finish_reason": "stop",
                }
            ]
        }

    composition.model.call_raw = fake_call_raw
    try:
        first_session = composition.engine.session("return a final answer")
        first = first_session.run()
        assert first.state.final_result
        assert first_session.lifecycle.value == "completed"
        request_view = first_session.inspect().last_request_view
        assert request_view is not None
        assert request_view.target.model == f"{profile}-model"
        assert "chat_template_kwargs" not in json.dumps(request_view.to_dict())

        projected = captured[0]["chat_template_kwargs"]
        assert type(projected) is dict
        assert type(projected["nested"]) is dict
        assert type(projected["nested"]["flags"]) is list
        assert projected[option_name] is option_value
        assert isinstance(
            config.model.request.extra_body["chat_template_kwargs"],
            MappingProxyType,
        )

        projected["nested"]["flags"].append("transport-only")
        projected[option_name] = not option_value
        second_session = composition.engine.session("return a final answer again")
        second = second_session.run()
        assert second.state.final_result
        assert captured[1]["chat_template_kwargs"][option_name] is option_value
        assert captured[1]["chat_template_kwargs"]["nested"]["flags"] == [
            True,
            False,
        ]

        assert config.digest() == original_digest
        assert config.canonical_json() == original_canonical
        assert composition.model.default_request_kwargs[
            "chat_template_kwargs"
        ][option_name] is option_value
        snapshot = composition.runtime.checkpoint_store.get_session_snapshot(
            second_session.current_head.snapshot_id.value
        )
        assert snapshot is not None
        assert "transport-only" not in json.dumps(snapshot.payload, sort_keys=True)
    finally:
        composition.close()


def test_reused_engine_keeps_independent_session_conversations_isolated(
    tmp_path: Path,
) -> None:
    path = tmp_path / "isolated.yaml"
    path.write_text(
        _config_text("isolation", "enable_thinking", False),
        encoding="utf-8",
    )
    composition = build_agent_composition(
        load_agent_config(path),
        credential_resolver=FakeCredentialResolver(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    captured: list[str] = []

    def fake_call_raw(messages: Any, **options: Any) -> dict[str, Any]:
        _ = options
        captured.append(json.dumps(messages, ensure_ascii=False))
        return {"choices": [{"message": {"content": "Final Answer: done"}}]}

    composition.model.call_raw = fake_call_raw
    try:
        first = composition.engine.session("alpha-only-task")
        second = composition.engine.session("beta-only-task")
        first.run()
        second.run()

        assert "alpha-only-task" in captured[0]
        assert "beta-only-task" in captured[1]
        assert "alpha-only-task" not in captured[1]
        assert composition.engine._qitos_exchange_log is None
        assert composition.engine._qitos_last_request_view is None
        assert first.inspect().last_request_view is not None
        assert second.inspect().last_request_view is not None
        assert (
            first.inspect().last_request_view.source_log_digest
            != second.inspect().last_request_view.source_log_digest
        )
    finally:
        composition.close()


def test_reused_engine_isolates_one_hundred_deterministic_session_rounds(
    tmp_path: Path,
) -> None:
    path = tmp_path / "isolation-100.yaml"
    path.write_text(
        _config_text("isolation-100", "enable_thinking", False),
        encoding="utf-8",
    )
    composition = build_agent_composition(
        load_agent_config(path),
        credential_resolver=FakeCredentialResolver(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    captured: list[str] = []

    def fake_call_raw(messages: Any, **options: Any) -> dict[str, Any]:
        _ = options
        captured.append(json.dumps(messages, ensure_ascii=False))
        return {"choices": [{"message": {"content": "Final Answer: done"}}]}

    composition.model.call_raw = fake_call_raw
    digests: set[str] = set()
    try:
        for index in range(100):
            task = f"isolated-round-{index:03d}"
            session = composition.engine.session(task)
            session.run()
            view = session.inspect().last_request_view
            assert view is not None
            digests.add(view.source_log_digest)
            assert task in captured[index]
            if index:
                assert f"isolated-round-{index - 1:03d}" not in captured[index]
        assert len(digests) == 100
        assert composition.engine._qitos_exchange_log is None
    finally:
        composition.close()


def test_fan_out_child_request_view_contains_only_authorized_child_task(
    tmp_path: Path,
) -> None:
    class PauseFirstBoundary(LifecyclePolicy):
        policy_id = "tests.child_request_view.pause_first"

        def should_pause(self, context: Any) -> bool:
            return context.step_id == 0

    path = tmp_path / "child-request-view.yaml"
    path.write_text(
        _config_text("child-request-view", "enable_thinking", False)
        .replace("max_steps: 2", "max_steps: 4")
        .replace("max_requests: 12", "max_requests: 3"),
        encoding="utf-8",
    )
    composition = build_agent_composition(
        load_agent_config(path),
        credential_resolver=FakeCredentialResolver(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    composition.runtime.lifecycle_policy = PauseFirstBoundary()
    composition.runtime.work_runtime = DurableWorkRuntime(_HoldingScheduler())
    captured: list[str] = []

    def fake_call_raw(messages: Any, **options: Any) -> dict[str, Any]:
        _ = options
        captured.append(json.dumps(messages, ensure_ascii=False))
        content = (
            "Thought: continue\nAction: missing_tool\nAction Input: {}"
            if len(captured) == 1
            else "Final Answer: done"
        )
        return {"choices": [{"message": {"content": content}}]}

    composition.model.call_raw = fake_call_raw
    try:
        parent = composition.engine.session("parent-calculator-only")
        parent.run()
        submitted = parent.fan_out(
            [
                {
                    "agent": "child-request-view",
                    "task": "child-readme-only",
                    "budget": {"model_requests": 2},
                }
            ],
            operation_id="fan_out:request-view-isolation",
        )
        child_id = submitted.descriptor["child_session_ids"][0]
        child = Engine.restore(child_id, runtime=composition.runtime)
        child.run()

        assert len(captured) == 2
        assert "parent-calculator-only" in captured[0]
        assert "child-readme-only" in captured[1]
        assert "parent-calculator-only" not in captured[1]
        assert child.inspect().budget["model_requests_consumed"] == 1
        assert parent.inspect().budget["model_requests_reserved"] == 2

        restored_parent = Engine.restore(
            parent.session_id,
            runtime=composition.runtime,
        )
        parent_result = restored_parent.run()
        assert parent_result.error_code == "model_request_budget_exhausted"
        assert len(captured) == 2
    finally:
        composition.close()


def test_durable_model_request_budget_blocks_third_dispatch_after_restore(
    tmp_path: Path,
) -> None:
    class PauseFirstBoundary(LifecyclePolicy):
        policy_id = "tests.request_budget.pause_first"

        def should_pause(self, context: Any) -> bool:
            return context.step_id == 0

    path = tmp_path / "request-budget.yaml"
    path.write_text(
        _config_text("request-budget", "enable_thinking", False)
        .replace("max_steps: 2", "max_steps: 5")
        .replace("max_requests: 12", "max_requests: 2"),
        encoding="utf-8",
    )
    composition = build_agent_composition(
        load_agent_config(path),
        credential_resolver=FakeCredentialResolver(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    composition.runtime.lifecycle_policy = PauseFirstBoundary()
    attempts = 0

    def fake_call_raw(messages: Any, **options: Any) -> dict[str, Any]:
        nonlocal attempts
        _ = messages, options
        attempts += 1
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Thought: continue\nAction: missing_tool\n"
                            "Action Input: {}"
                        )
                    }
                }
            ]
        }

    composition.model.call_raw = fake_call_raw
    try:
        session = composition.engine.session("bounded-request-task")
        session.run()
        assert session.lifecycle.value == "paused"
        assert session.inspect().budget["model_requests_consumed"] == 1

        restored = Engine.restore(session.session_id, runtime=composition.runtime)
        result = restored.run()

        assert attempts == 2
        assert result.error_code == "model_request_budget_exhausted"
        assert restored.lifecycle.value == "failed"
        assert restored.inspect().budget == {
            **restored.inspect().budget,
            "max_model_requests": 2,
            "model_requests_consumed": 2,
        }
        with pytest.raises(SessionContractError):
            Engine.restore(session.session_id, runtime=composition.runtime)
    finally:
        composition.close()


@pytest.mark.parametrize(
    ("failure_kind", "expected_code", "expected_requests"),
    [
        ("codec", "codec_transport_options_invalid", 0),
        ("provider", "provider_server_error", 1),
    ],
)
def test_configured_session_persists_terminal_root_failure_and_trajectory(
    tmp_path: Path,
    failure_kind: str,
    expected_code: str,
    expected_requests: int,
) -> None:
    trajectory_path = tmp_path / f"{failure_kind}-trajectory.json"
    text = _config_text("failure-profile", "enable_thinking", False).replace(
        "trajectory:\n    enabled: false\n    output: ./runs",
        f"trajectory:\n    enabled: true\n    output: {trajectory_path}",
    )
    path = tmp_path / f"{failure_kind}.yaml"
    path.write_text(text, encoding="utf-8")
    config = load_agent_config(path)
    composition = build_agent_composition(
        config,
        credential_resolver=FakeCredentialResolver(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    requests = 0

    if failure_kind == "codec":
        composition.model.default_request_kwargs = {
            "chat_template_kwargs": {"invalid": object()}
        }
    else:
        def provider_failure(messages: Any, **options: Any) -> Any:
            nonlocal requests
            _ = messages, options
            requests += 1
            error = RuntimeError("provider-private-payload")
            error.status_code = 503  # type: ignore[attr-defined]
            raise error

        composition.model.call_raw = provider_failure

    session = composition.engine.session("fail before pause")
    try:
        result = session.run()
        assert result.state.stop_reason == "unrecoverable_error"
        assert result.error_code == expected_code
        assert result.failure == {
            "phase": "DECIDE",
            "step_id": 0,
            "error_type": (
                "_JSONMaterializationError"
                if failure_kind == "codec"
                else "ProviderFailure"
            ),
            "error_code": expected_code,
            "error_category": (
                "provider_capability_loss"
                if failure_kind == "codec"
                else "provider_server"
            ),
        }
        assert requests == expected_requests
        assert (
            session.inspect().budget["model_requests_consumed"]
            == expected_requests
        )
        assert session.lifecycle.value == "failed"
        record = composition.runtime.checkpoint_store.get_session_snapshot(
            session.current_head.snapshot_id.value
        )
        assert record is not None
        persisted = json.dumps(record.payload, sort_keys=True)
        assert expected_code in persisted
        assert "provider-private-payload" not in persisted

        composition.runtime.bind_engine_resources(composition.engine)
        with pytest.raises(SessionContractError) as caught:
            Engine.restore(session.session_id, runtime=composition.runtime)
        assert (
            caught.value.error_code
            is SessionErrorCode.INVALID_LIFECYCLE_OPERATION
        )
    finally:
        composition.close()

    trajectory = trajectory_path.read_text(encoding="utf-8")
    assert expected_code in trajectory
    assert "provider-private-payload" not in trajectory
    assert "/Users/" not in trajectory

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from qitos.kit.env import sandbox as sandbox_module
from qitos.kit.env.sandbox import (
    DockerSandboxBackend,
    SandboxCapabilities,
    SandboxCleanupFailure,
    SandboxReceipt,
    SandboxUnavailable,
    UnsafeHostBackend,
    assert_sandbox_backend_conformance,
    run_sandbox_backend_conformance,
)


def _safe_capabilities(backend_id: str = "third-party") -> SandboxCapabilities:
    return SandboxCapabilities(
        backend_id=backend_id,
        isolated=True,
        non_root=True,
        read_only_root=True,
        writable_workspace_only=True,
        network_disabled=True,
        capabilities_dropped=True,
        no_new_privileges=True,
        cpu_bounded=True,
        memory_bounded=True,
        processes_bounded=True,
        credentials_injected=False,
        provider_requests_host_side=True,
        cleanup_required=True,
        disk_bounded=True,
        output_bounded=True,
        time_bounded=True,
        private_workspace=True,
    )


class ThirdPartyBackend:
    backend_id = "third-party"

    def __init__(self) -> None:
        self.capabilities = _safe_capabilities()
        self.receipt = SandboxReceipt(
            backend_id=self.backend_id,
            config_digest="a" * 64,
            status="prepared",
            safety="sandboxed",
            capabilities=self.capabilities,
            attestation_digest="b" * 64,
        )

    def prepare(self) -> SandboxReceipt:
        return self.receipt

    def execute(self, command: str, *, timeout: int = 30) -> Mapping[str, Any]:
        return {"command": command, "timeout": timeout, "returncode": 0}

    def inspect_capabilities(self) -> SandboxCapabilities:
        return self.capabilities

    def request_cancellation(self) -> Mapping[str, Any]:
        return {"status": "requested"}

    def cleanup(self) -> SandboxReceipt:
        return replace(self.receipt, status="cleaned", cleanup="passed")

    def durability_receipt(self) -> Mapping[str, Any]:
        return self.receipt.to_dict()


def test_third_party_backend_conforms_without_subclassing_docker() -> None:
    backend = ThirdPartyBackend()

    capabilities = assert_sandbox_backend_conformance(backend)

    assert capabilities.safe_for_executable_tools is True
    assert backend.execute("true")["returncode"] == 0


def test_third_party_backend_public_lifecycle_runner_is_structural_only() -> None:
    report = run_sandbox_backend_conformance(ThirdPartyBackend())

    assert report == {
        "status": "passed",
        "backend_id": "third-party",
        "structural_only": True,
        "safe_for_executable_tools": True,
        "cleanup": "passed",
    }


class _FakeHostEnv:
    def __init__(self) -> None:
        self.prepared = False

    def setup(self) -> None:
        self.prepared = True


def test_unsafe_host_receipt_never_claims_sandbox_capabilities() -> None:
    env = _FakeHostEnv()
    backend = UnsafeHostBackend(env, config_digest="c" * 64)

    receipt = backend.prepare()
    capabilities = assert_sandbox_backend_conformance(backend)

    assert env.prepared is True
    assert receipt.safety == "unisolated_host_execution"
    assert receipt.cleanup == "not_applicable"
    assert capabilities.safe_for_executable_tools is False
    assert capabilities.isolated is False
    assert capabilities.network_disabled is False


class _UnavailableDockerEnv:
    container = "qitos-test-unavailable"
    container_workspace = "/workspace"
    remove_on_close = True

    def __init__(self) -> None:
        self.closed = False

    def setup(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_unavailable_docker_is_typed_and_cleans_partial_prepare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = _UnavailableDockerEnv()

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        _ = args, kwargs
        raise FileNotFoundError("docker")

    monkeypatch.setattr(sandbox_module.subprocess, "run", unavailable)
    backend = DockerSandboxBackend(env, config_digest="d" * 64)

    with pytest.raises(SandboxUnavailable):
        backend.prepare()

    assert env.closed is True


def test_docker_cleanup_must_prove_container_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = _UnavailableDockerEnv()
    monkeypatch.setattr(
        sandbox_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    backend = DockerSandboxBackend(env, config_digest="e" * 64)

    with pytest.raises(SandboxCleanupFailure) as caught:
        backend.cleanup()

    assert env.closed is True
    assert caught.value.receipt["cleanup"] == "failed"


def test_composition_failure_cleans_prepared_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qitos.config import builder as builder_module
    from qitos.config.loader import AgentConfig

    backend = ThirdPartyBackend()
    cleanup_calls = 0

    def cleanup() -> SandboxReceipt:
        nonlocal cleanup_calls
        cleanup_calls += 1
        return backend.receipt

    backend.cleanup = cleanup  # type: ignore[method-assign]
    monkeypatch.setattr(
        builder_module,
        "_build_environment_with_receipt",
        lambda config: (object(), backend, backend.receipt.to_dict()),
    )
    monkeypatch.setattr(
        builder_module,
        "build_runtime",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        builder_module.build_agent_composition(
            AgentConfig(protocol="react_text_v1", parser="auto"),
            model_override=object(),
        )

    assert cleanup_calls == 1


def test_composition_close_cleans_backend_when_event_flush_fails() -> None:
    from qitos.config.builder import AgentComposition
    from qitos.config.loader import AgentConfig

    backend = ThirdPartyBackend()
    cleanup_calls = 0

    def cleanup() -> SandboxReceipt:
        nonlocal cleanup_calls
        cleanup_calls += 1
        return backend.receipt

    backend.cleanup = cleanup  # type: ignore[method-assign]
    runtime = SimpleNamespace(
        flush_events=lambda: (_ for _ in ()).throw(RuntimeError("flush failed")),
        event_sink=None,
        checkpoint_store=None,
    )
    composition = AgentComposition(
        config=AgentConfig(),
        model=object(),
        tool_registry=object(),  # type: ignore[arg-type]
        env=object(),
        runtime=runtime,  # type: ignore[arg-type]
        agent=object(),  # type: ignore[arg-type]
        engine=object(),  # type: ignore[arg-type]
        credential_receipt={},
        sandbox_backend=backend,
    )

    with pytest.raises(RuntimeError, match="flush failed"):
        composition.close()

    assert cleanup_calls == 1

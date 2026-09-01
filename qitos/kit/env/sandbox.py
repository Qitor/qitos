"""Structural sandbox backend contract and truthful reference adapters.

The contract is intentionally independent of Docker.  It describes observable
execution authority and lifecycle receipts; it does not create another Env or
tool executor.  Tools continue to execute through the canonical ``Env`` passed
to ``ActionExecutor``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Protocol, runtime_checkable


class SandboxBackendError(RuntimeError):
    code = "sandbox_backend_error"

    def __init__(self, message: str, *, receipt: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.receipt = dict(receipt or {})


class SandboxUnavailable(SandboxBackendError):
    code = "sandbox_unavailable"


class SandboxCapabilityMismatch(SandboxBackendError):
    code = "sandbox_capability_mismatch"


class SandboxCleanupFailure(SandboxBackendError):
    code = "sandbox_cleanup_failed"


@dataclass(frozen=True)
class SandboxCapabilities:
    backend_id: str
    isolated: bool
    non_root: bool
    read_only_root: bool
    writable_workspace_only: bool
    network_disabled: bool
    capabilities_dropped: bool
    no_new_privileges: bool
    cpu_bounded: bool
    memory_bounded: bool
    processes_bounded: bool
    credentials_injected: bool
    provider_requests_host_side: bool
    cleanup_required: bool

    @property
    def safe_for_executable_tools(self) -> bool:
        required = (
            self.isolated,
            self.non_root,
            self.read_only_root,
            self.writable_workspace_only,
            self.network_disabled,
            self.capabilities_dropped,
            self.no_new_privileges,
            self.cpu_bounded,
            self.memory_bounded,
            self.processes_bounded,
            not self.credentials_injected,
            self.provider_requests_host_side,
            self.cleanup_required,
        )
        return all(required)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "isolated": self.isolated,
            "non_root": self.non_root,
            "read_only_root": self.read_only_root,
            "writable_workspace_only": self.writable_workspace_only,
            "network_disabled": self.network_disabled,
            "capabilities_dropped": self.capabilities_dropped,
            "no_new_privileges": self.no_new_privileges,
            "cpu_bounded": self.cpu_bounded,
            "memory_bounded": self.memory_bounded,
            "processes_bounded": self.processes_bounded,
            "credentials_injected": self.credentials_injected,
            "provider_requests_host_side": self.provider_requests_host_side,
            "cleanup_required": self.cleanup_required,
            "safe_for_executable_tools": self.safe_for_executable_tools,
        }


@dataclass(frozen=True)
class SandboxReceipt:
    backend_id: str
    config_digest: str
    status: str
    safety: str
    capabilities: SandboxCapabilities
    attestation_digest: str
    cleanup: str = "pending"
    warnings: tuple[str, ...] = ()
    schema: str = "qitos.sandbox.receipt/1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "backend_id": self.backend_id,
            "config_digest": self.config_digest,
            "status": self.status,
            "safety": self.safety,
            "capabilities": self.capabilities.to_dict(),
            "attestation_digest": self.attestation_digest,
            "cleanup": self.cleanup,
            "warnings": list(self.warnings),
        }


@runtime_checkable
class SandboxBackend(Protocol):
    """Minimum replaceable backend used by configured executable agents."""

    backend_id: str

    def prepare(self) -> SandboxReceipt:
        ...

    def execute(self, command: str, *, timeout: int = 30) -> Mapping[str, Any]:
        ...

    def inspect_capabilities(self) -> SandboxCapabilities:
        ...

    def request_cancellation(self) -> Mapping[str, Any]:
        ...

    def cleanup(self) -> SandboxReceipt:
        ...

    def durability_receipt(self) -> Mapping[str, Any]:
        ...


def assert_sandbox_backend_conformance(backend: Any) -> SandboxCapabilities:
    """Validate only the public structural seam, suitable for third parties."""
    if not isinstance(backend, SandboxBackend):
        raise SandboxCapabilityMismatch("backend does not implement SandboxBackend")
    capabilities = backend.inspect_capabilities()
    if not isinstance(capabilities, SandboxCapabilities):
        raise SandboxCapabilityMismatch("backend returned invalid capabilities")
    receipt = backend.durability_receipt()
    if not isinstance(receipt, Mapping):
        raise SandboxCapabilityMismatch("backend durability receipt is not a mapping")
    json.dumps(dict(receipt), allow_nan=False, sort_keys=True)
    return capabilities


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class DockerSandboxBackend:
    """Inspect-backed adapter over the existing Docker Env."""

    backend_id = "docker"

    def __init__(self, env: Any, *, config_digest: str) -> None:
        self.env = env
        self.config_digest = config_digest
        self._capabilities: SandboxCapabilities | None = None
        self._receipt: SandboxReceipt | None = None

    def prepare(self) -> SandboxReceipt:
        try:
            self.env.setup()
            inspected = subprocess.run(
                ["docker", "inspect", str(self.env.container)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            self._cleanup_failed_prepare()
            raise SandboxUnavailable("Docker runtime is unavailable") from exc
        except Exception as exc:
            self._cleanup_failed_prepare()
            raise SandboxUnavailable("Docker sandbox could not be prepared") from exc
        if inspected.returncode != 0:
            self._cleanup_failed_prepare()
            raise SandboxUnavailable("Docker sandbox inspect is unavailable")
        try:
            document = json.loads(inspected.stdout)
            item = document[0]
            host = dict(item.get("HostConfig") or {})
            config = dict(item.get("Config") or {})
            mounts = list(item.get("Mounts") or [])
        except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._cleanup_failed_prepare()
            raise SandboxCapabilityMismatch("Docker inspect response is invalid") from exc
        container_workspace = str(self.env.container_workspace)
        env_values = [str(value) for value in list(config.get("Env") or [])]
        sensitive_tokens = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION")
        capabilities = SandboxCapabilities(
            backend_id=self.backend_id,
            isolated=True,
            non_root=str(config.get("User") or "") not in {"", "0", "root"},
            read_only_root=host.get("ReadonlyRootfs") is True,
            writable_workspace_only=(
                len(mounts) == 1
                and mounts[0].get("Destination") == container_workspace
                and mounts[0].get("RW") is True
            ),
            network_disabled=host.get("NetworkMode") == "none",
            capabilities_dropped="ALL" in {
                str(value).upper() for value in list(host.get("CapDrop") or [])
            },
            no_new_privileges=any(
                "no-new-privileges" in str(value)
                for value in list(host.get("SecurityOpt") or [])
            ),
            cpu_bounded=int(host.get("NanoCpus") or 0) > 0,
            memory_bounded=int(host.get("Memory") or 0) > 0,
            processes_bounded=int(host.get("PidsLimit") or 0) > 0,
            credentials_injected=any(
                any(token in value.upper() for token in sensitive_tokens)
                for value in env_values
            ),
            provider_requests_host_side=True,
            cleanup_required=bool(getattr(self.env, "remove_on_close", False)),
        )
        safe_inspect = {
            "image": item.get("Image"),
            "user": config.get("User"),
            "network": host.get("NetworkMode"),
            "read_only_root": host.get("ReadonlyRootfs"),
            "cap_drop": list(host.get("CapDrop") or []),
            "security_opt": list(host.get("SecurityOpt") or []),
            "pids_limit": host.get("PidsLimit"),
            "memory": host.get("Memory"),
            "nano_cpus": host.get("NanoCpus"),
            "mounts": [
                {
                    "type": mount.get("Type"),
                    "destination": mount.get("Destination"),
                    "rw": mount.get("RW"),
                }
                for mount in mounts
            ],
            "credentials_injected": capabilities.credentials_injected,
        }
        self._capabilities = capabilities
        self._receipt = SandboxReceipt(
            backend_id=self.backend_id,
            config_digest=self.config_digest,
            status=("prepared" if capabilities.safe_for_executable_tools else "rejected"),
            safety=("sandboxed" if capabilities.safe_for_executable_tools else "capability_loss"),
            capabilities=capabilities,
            attestation_digest=_digest(safe_inspect),
        )
        if not capabilities.safe_for_executable_tools:
            try:
                self.cleanup()
            finally:
                raise SandboxCapabilityMismatch(
                    "Docker backend did not attest every required capability",
                    receipt=self._receipt.to_dict(),
                )
        return self._receipt

    def _cleanup_failed_prepare(self) -> None:
        try:
            self.env.close()
        except Exception as exc:
            raise SandboxCleanupFailure(
                "partially prepared Docker sandbox could not be cleaned"
            ) from exc

    def execute(self, command: str, *, timeout: int = 30) -> Mapping[str, Any]:
        return dict(self.env.cmd.run(command, timeout=timeout))

    def inspect_capabilities(self) -> SandboxCapabilities:
        if self._capabilities is None:
            return SandboxCapabilities(
                self.backend_id,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                True,
                True,
            )
        return self._capabilities

    def request_cancellation(self) -> Mapping[str, Any]:
        return {"status": "requested", "hard_cancellation": False}

    def cleanup(self) -> SandboxReceipt:
        previous = self._receipt
        self.env.close()
        container = str(getattr(self.env, "container", "") or "")
        absent = True
        if container:
            try:
                inspected = subprocess.run(
                    ["docker", "inspect", container],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                absent = inspected.returncode != 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                absent = False
        if previous is None:
            capabilities = self.inspect_capabilities()
            previous = SandboxReceipt(
                backend_id=self.backend_id,
                config_digest=self.config_digest,
                status="cleanup_only",
                safety="unknown",
                capabilities=capabilities,
                attestation_digest=_digest({"prepared": False}),
            )
        self._receipt = SandboxReceipt(
            backend_id=previous.backend_id,
            config_digest=previous.config_digest,
            status=("cleaned" if absent else "cleanup_failed"),
            safety=previous.safety,
            capabilities=previous.capabilities,
            attestation_digest=previous.attestation_digest,
            cleanup=("passed" if absent else "failed"),
            warnings=previous.warnings,
        )
        if not absent:
            raise SandboxCleanupFailure(
                "Docker sandbox cleanup could not be proven",
                receipt=self._receipt.to_dict(),
            )
        return self._receipt

    def durability_receipt(self) -> Mapping[str, Any]:
        return self._receipt.to_dict() if self._receipt else {"status": "unprepared"}


class UnsafeHostBackend:
    """Explicit non-sandbox adapter that never claims Docker capabilities."""

    backend_id = "unsafe_host"

    def __init__(self, env: Any, *, config_digest: str) -> None:
        self.env = env
        self.config_digest = config_digest
        self._capabilities = SandboxCapabilities(
            backend_id=self.backend_id,
            isolated=False,
            non_root=False,
            read_only_root=False,
            writable_workspace_only=False,
            network_disabled=False,
            capabilities_dropped=False,
            no_new_privileges=False,
            cpu_bounded=False,
            memory_bounded=False,
            processes_bounded=False,
            credentials_injected=False,
            provider_requests_host_side=True,
            cleanup_required=False,
        )
        self._receipt = SandboxReceipt(
            backend_id=self.backend_id,
            config_digest=config_digest,
            status="unsafe",
            safety="unisolated_host_execution",
            capabilities=self._capabilities,
            attestation_digest=_digest(self._capabilities.to_dict()),
            cleanup="not_applicable",
            warnings=("unsafe_host_explicit_opt_in",),
        )

    def prepare(self) -> SandboxReceipt:
        self.env.setup()
        return self._receipt

    def execute(self, command: str, *, timeout: int = 30) -> Mapping[str, Any]:
        return dict(self.env.cmd.run(command, timeout=timeout))

    def inspect_capabilities(self) -> SandboxCapabilities:
        return self._capabilities

    def request_cancellation(self) -> Mapping[str, Any]:
        return {"status": "requested", "hard_cancellation": False}

    def cleanup(self) -> SandboxReceipt:
        return self._receipt

    def durability_receipt(self) -> Mapping[str, Any]:
        return self._receipt.to_dict()


__all__ = [
    "DockerSandboxBackend",
    "SandboxBackend",
    "SandboxBackendError",
    "SandboxCapabilities",
    "SandboxCapabilityMismatch",
    "SandboxCleanupFailure",
    "SandboxReceipt",
    "SandboxUnavailable",
    "UnsafeHostBackend",
    "assert_sandbox_backend_conformance",
]

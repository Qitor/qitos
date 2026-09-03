"""Structural sandbox backend contract and truthful reference adapters.

The contract is intentionally independent of Docker.  It describes observable
execution authority and lifecycle receipts; it does not create another Env or
tool executor.  Tools continue to execute through the canonical ``Env`` passed
to ``ActionExecutor``.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping, Protocol, runtime_checkable

from qitos.core.session import SnapshotComponentCodec


SANDBOX_POLICY_SCHEMA_VERSION = "qitos.sandbox.policy/v1"
SANDBOX_SNAPSHOT_COMPONENT_VERSION = "qitos.sandbox.snapshot_component/v1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,255}$")


def _positive(name: str, value: int | float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class SandboxResourceLimits:
    cpu_count: float = 2.0
    memory_bytes: int = 2 * 1024 * 1024 * 1024
    pids: int = 256
    file_descriptors: int = 1024
    tmpfs_bytes: int = 256 * 1024 * 1024
    disk_bytes: int = 2 * 1024 * 1024 * 1024
    output_bytes: int = 2 * 1024 * 1024
    command_seconds: int = 180
    wall_seconds: int = 3600

    def __post_init__(self) -> None:
        for name in (
            "cpu_count", "memory_bytes", "pids", "file_descriptors",
            "tmpfs_bytes", "disk_bytes", "output_bytes", "command_seconds",
            "wall_seconds",
        ):
            _positive(name, getattr(self, name))

    def to_dict(self) -> Dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class SandboxPolicy:
    """Strict desired state. Unsupported required constraints must be rejected."""

    image: str
    image_digest: str | None = None
    workspace_mode: str = "private_copy"
    workspace_destination: str = "/workspace"
    input_mounts: tuple[str, ...] = ()
    output_destination: str = "/results"
    run_as_uid: int = 65532
    run_as_gid: int = 65532
    read_only_root: bool = True
    drop_capabilities: bool = True
    no_new_privileges: bool = True
    allow_devices: bool = False
    privileged: bool = False
    host_pid: bool = False
    host_ipc: bool = False
    network_mode: str = "none"
    egress_rules: tuple[str, ...] = ()
    deny_private_networks: bool = True
    secrets: tuple[str, ...] = ()
    provider_requests_host_side: bool = True
    supports_pause: bool = False
    supports_snapshot: bool = False
    supports_fork: bool = False
    cleanup_policy: str = "destroy_exact_identity"
    limits: SandboxResourceLimits = field(default_factory=SandboxResourceLimits)
    schema_version: str = SANDBOX_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SANDBOX_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported sandbox policy version")
        if not isinstance(self.image, str) or not self.image.strip():
            raise ValueError("image must be non-empty")
        if self.image_digest is not None and _DIGEST.fullmatch(self.image_digest) is None:
            raise ValueError("image_digest must be a lowercase SHA-256")
        if self.workspace_mode not in {"private_copy", "ephemeral_empty", "read_only_source"}:
            raise ValueError("direct writable host mounts are not a safe sandbox policy")
        if self.network_mode not in {"none", "allowlist"}:
            raise ValueError("network_mode must be none or allowlist")
        if self.network_mode == "none" and self.egress_rules:
            raise ValueError("network-disabled policy cannot contain egress rules")
        if self.network_mode == "allowlist" and not self.egress_rules:
            raise ValueError("allowlist network policy requires explicit rules")
        if self.privileged or self.host_pid or self.host_ipc or self.allow_devices:
            raise ValueError("unsafe namespace, privilege, or device authority is rejected")
        if not self.read_only_root or not self.drop_capabilities or not self.no_new_privileges:
            raise ValueError("safe policy requires read-only root, dropped caps, and no-new-privileges")
        if self.run_as_uid == 0 or self.run_as_gid == 0:
            raise ValueError("safe policy requires a non-root uid and gid")
        if self.secrets:
            raise ValueError("container secret injection is not supported by this backend")
        if not self.provider_requests_host_side:
            raise ValueError("provider requests must remain host-side")
        if self.cleanup_policy != "destroy_exact_identity":
            raise ValueError("unsupported cleanup policy")
        if not self.workspace_destination.startswith("/") or not self.output_destination.startswith("/"):
            raise ValueError("container destinations must be absolute")
        if not isinstance(self.limits, SandboxResourceLimits):
            raise TypeError("limits must be SandboxResourceLimits")

    @classmethod
    def coding(
        cls,
        image: str,
        *,
        image_digest: str | None = None,
        uid: int = 65532,
        gid: int = 65532,
        limits: SandboxResourceLimits | None = None,
    ) -> "SandboxPolicy":
        return cls(
            image=image,
            image_digest=image_digest,
            run_as_uid=uid,
            run_as_gid=gid,
            limits=limits or SandboxResourceLimits(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "image": self.image,
            "image_digest": self.image_digest,
            "workspace_mode": self.workspace_mode,
            "workspace_destination": self.workspace_destination,
            "input_mounts": list(self.input_mounts),
            "output_destination": self.output_destination,
            "run_as_uid": self.run_as_uid,
            "run_as_gid": self.run_as_gid,
            "read_only_root": self.read_only_root,
            "drop_capabilities": self.drop_capabilities,
            "no_new_privileges": self.no_new_privileges,
            "allow_devices": self.allow_devices,
            "privileged": self.privileged,
            "host_pid": self.host_pid,
            "host_ipc": self.host_ipc,
            "network_mode": self.network_mode,
            "egress_rules": list(self.egress_rules),
            "deny_private_networks": self.deny_private_networks,
            "secrets": list(self.secrets),
            "provider_requests_host_side": self.provider_requests_host_side,
            "supports_pause": self.supports_pause,
            "supports_snapshot": self.supports_snapshot,
            "supports_fork": self.supports_fork,
            "cleanup_policy": self.cleanup_policy,
            "limits": self.limits.to_dict(),
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True, init=False)
class SandboxIdentity:
    sandbox_id: str
    session_id: str
    run_id: str
    work_item_id: str
    attempt_id: str
    owner_generation: int

    def __init__(
        self,
        sandbox_id: str | None = None,
        session_id: str = "",
        run_id: str = "",
        work_item_id: str = "",
        attempt_id: str | None = None,
        owner_generation: int = 0,
        *,
        environment_id: str | None = None,
    ) -> None:
        """Build the one identity, accepting the former environment-id spelling."""
        resolved_sandbox = str(sandbox_id or environment_id or "")
        resolved_attempt = str(attempt_id or environment_id or resolved_sandbox)
        object.__setattr__(self, "sandbox_id", resolved_sandbox)
        object.__setattr__(self, "session_id", str(session_id))
        object.__setattr__(self, "run_id", str(run_id))
        object.__setattr__(self, "work_item_id", str(work_item_id))
        object.__setattr__(self, "attempt_id", resolved_attempt)
        object.__setattr__(self, "owner_generation", owner_generation)
        self.__post_init__()

    def __post_init__(self) -> None:
        for name in ("sandbox_id", "session_id", "run_id", "work_item_id", "attempt_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None:
                raise ValueError(f"{name} is invalid")
        if self.owner_generation < 0:
            raise ValueError("owner_generation must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SandboxIdentity":
        if set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("sandbox identity shape is invalid")
        return cls(**dict(payload))


@dataclass(frozen=True)
class SandboxLease:
    """Generation-fenced authority over one logical sandbox."""

    lease_id: str
    owner_generation: int
    state: str = "active"

    def __post_init__(self) -> None:
        if _SAFE_TOKEN.fullmatch(self.lease_id) is None:
            raise ValueError("lease_id is invalid")
        if self.owner_generation < 0:
            raise ValueError("owner_generation must be non-negative")
        if self.state not in {"active", "quiescing", "closed", "stale"}:
            raise ValueError("lease state is invalid")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "owner_generation": self.owner_generation,
            "state": self.state,
        }


@dataclass(frozen=True)
class SandboxHandle:
    """Portable logical handle; it never embeds a live client or process."""

    identity: SandboxIdentity
    backend_type: str
    policy_digest: str
    image_digest: str
    capability_set: tuple[str, ...]
    lease: SandboxLease

    def __post_init__(self) -> None:
        if _SAFE_TOKEN.fullmatch(self.backend_type) is None:
            raise ValueError("backend_type is invalid")
        for name in ("policy_digest", "image_digest"):
            value = getattr(self, name)
            if value and _DIGEST.fullmatch(value) is None:
                raise ValueError(f"{name} must be an empty or lowercase SHA-256 digest")
        if len(set(self.capability_set)) != len(self.capability_set):
            raise ValueError("capability_set must be unique")
        if any(_SAFE_TOKEN.fullmatch(item) is None for item in self.capability_set):
            raise ValueError("capability_set contains an invalid capability")

    def snapshot_component(
        self,
        *,
        workspace_digest: str,
        input_digest: str,
        quiescence: str,
        cleanup_state: str,
    ) -> "SandboxSnapshotComponent":
        return SandboxSnapshotComponent(
            logical_identity=self.identity.to_dict(),
            backend_type=self.backend_type,
            policy_digest=self.policy_digest,
            image_digest=self.image_digest,
            capability_set=self.capability_set,
            lease=self.lease.to_dict(),
            workspace_digest=workspace_digest,
            input_digest=input_digest,
            quiescence=quiescence,
            cleanup_state=cleanup_state,
        )


@dataclass(frozen=True)
class SandboxAllocation:
    """Patch-ready least-authority allocation for one durable work child."""

    allocation_id: str
    operation_id: str
    parent_work_item_id: str
    child_work_item_id: str
    handle: SandboxHandle

    def to_dict(self) -> Dict[str, Any]:
        for name in (
            "allocation_id", "operation_id", "parent_work_item_id", "child_work_item_id"
        ):
            if _SAFE_TOKEN.fullmatch(str(getattr(self, name))) is None:
                raise ValueError(f"{name} is invalid")
        return {
            "allocation_id": self.allocation_id,
            "operation_id": self.operation_id,
            "parent_work_item_id": self.parent_work_item_id,
            "child_work_item_id": self.child_work_item_id,
            "sandbox": {
                "identity": self.handle.identity.to_dict(),
                "backend_type": self.handle.backend_type,
                "policy_digest": self.handle.policy_digest,
                "image_digest": self.handle.image_digest,
                "capability_set": list(self.handle.capability_set),
                "lease": self.handle.lease.to_dict(),
            },
        }


@dataclass(frozen=True)
class SandboxExecutionReceipt:
    operation_id: str
    owner_generation: int
    status: str
    returncode: int | None
    timed_out: bool
    worker_still_running: bool
    outcome_unknown: bool
    stdout_bytes: int
    stderr_bytes: int

    def __post_init__(self) -> None:
        if _SAFE_TOKEN.fullmatch(self.operation_id) is None:
            raise ValueError("operation_id is invalid")
        if self.owner_generation < 0:
            raise ValueError("owner_generation must be non-negative")
        if self.status not in {"success", "partial", "error"}:
            raise ValueError("execution status is invalid")
        if self.stdout_bytes < 0 or self.stderr_bytes < 0:
            raise ValueError("execution output sizes must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class SandboxCleanupReceipt:
    sandbox_id: str
    status: str
    container_absent: bool
    staging_absent: bool
    repeated: bool = False

    def __post_init__(self) -> None:
        if _SAFE_TOKEN.fullmatch(self.sandbox_id) is None:
            raise ValueError("sandbox_id is invalid")
        if self.status not in {"cleaned", "failed"}:
            raise ValueError("cleanup status is invalid")

    def to_dict(self) -> Dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class SandboxSnapshotComponent:
    logical_identity: Dict[str, Any]
    backend_type: str
    policy_digest: str
    image_digest: str
    capability_set: tuple[str, ...]
    lease: Dict[str, Any]
    workspace_digest: str
    input_digest: str
    quiescence: str
    cleanup_state: str
    schema_version: str = SANDBOX_SNAPSHOT_COMPONENT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SANDBOX_SNAPSHOT_COMPONENT_VERSION:
            raise ValueError("unsupported sandbox snapshot component")
        SandboxIdentity.from_dict(self.logical_identity)
        if _SAFE_TOKEN.fullmatch(self.backend_type) is None:
            raise ValueError("backend_type is invalid")
        for name in ("policy_digest", "image_digest", "workspace_digest", "input_digest"):
            if _DIGEST.fullmatch(str(getattr(self, name))) is None:
                raise ValueError(f"{name} must be a lowercase SHA-256")
        if len(set(self.capability_set)) != len(self.capability_set):
            raise ValueError("capability_set must be unique")
        if any(_SAFE_TOKEN.fullmatch(item) is None for item in self.capability_set):
            raise ValueError("capability_set contains an invalid capability")
        SandboxLease(**dict(self.lease))
        if self.quiescence not in {
            "processes_terminal", "worker_still_running", "outcome_unknown", "not_attested"
        }:
            raise ValueError("quiescence is invalid")
        if self.cleanup_state not in {"pending", "cleaned", "failed"}:
            raise ValueError("cleanup_state is invalid")

    def to_dict(self) -> Dict[str, Any]:
        self.__post_init__()
        payload = {name: getattr(self, name) for name in self.__dataclass_fields__}
        payload["capability_set"] = list(self.capability_set)
        json.dumps(payload, sort_keys=True, allow_nan=False)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SandboxSnapshotComponent":
        expected = set(cls.__dataclass_fields__)
        if set(payload) != expected:
            raise ValueError("sandbox snapshot component shape is invalid")
        data = dict(payload)
        data["capability_set"] = tuple(data["capability_set"])
        return cls(**data)


def _encode_sandbox_component(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, SandboxSnapshotComponent):
        raise TypeError("sandbox codec requires SandboxSnapshotComponent")
    return value.to_dict()


SANDBOX_SNAPSHOT_COMPONENT_CODEC = SnapshotComponentCodec(
    slot="sandbox",
    owner="qitos.sandbox",
    schema_version=SANDBOX_SNAPSHOT_COMPONENT_VERSION,
    required=False,
    encode=_encode_sandbox_component,
    decode=SandboxSnapshotComponent.from_dict,
)


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
    disk_bounded: bool = False
    output_bounded: bool = False
    time_bounded: bool = False
    private_workspace: bool = False
    secret_broker: bool = False
    pause: bool = False
    snapshot: bool = False
    fork: bool = False

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
            self.disk_bounded,
            self.output_bounded,
            self.time_bounded,
            self.private_workspace,
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
            "disk_bounded": self.disk_bounded,
            "output_bounded": self.output_bounded,
            "time_bounded": self.time_bounded,
            "private_workspace": self.private_workspace,
            "secret_broker": self.secret_broker,
            "pause": self.pause,
            "snapshot": self.snapshot,
            "fork": self.fork,
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
    policy_digest: str = ""
    image_digest: str = ""
    logical_identity: Dict[str, Any] = field(default_factory=dict)
    workspace_digest: str = ""
    input_digest: str = ""
    lease: Dict[str, Any] = field(default_factory=dict)
    execution_receipts: tuple[Dict[str, Any], ...] = ()
    cleanup_receipt: Dict[str, Any] = field(default_factory=dict)
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
            "policy_digest": self.policy_digest,
            "image_digest": self.image_digest,
            "logical_identity": dict(self.logical_identity),
            "workspace_digest": self.workspace_digest,
            "input_digest": self.input_digest,
            "lease": dict(self.lease),
            "execution_receipts": [dict(item) for item in self.execution_receipts],
            "cleanup_receipt": dict(self.cleanup_receipt),
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


def run_sandbox_backend_conformance(backend: Any) -> Dict[str, Any]:
    """Exercise prepare/execute/cleanup using only SandboxBackend methods."""
    capabilities = assert_sandbox_backend_conformance(backend)
    prepared = backend.prepare()
    if not isinstance(prepared, SandboxReceipt):
        raise SandboxCapabilityMismatch("prepare did not return SandboxReceipt")
    executed = backend.execute("true", timeout=10)
    if not isinstance(executed, Mapping):
        raise SandboxCapabilityMismatch("execute did not return a mapping")
    cleaned = backend.cleanup()
    if not isinstance(cleaned, SandboxReceipt):
        raise SandboxCapabilityMismatch("cleanup did not return SandboxReceipt")
    if capabilities.cleanup_required and cleaned.cleanup != "passed":
        raise SandboxCleanupFailure(
            "backend did not prove cleanup", receipt=cleaned.to_dict()
        )
    return {
        "status": "passed",
        "backend_id": capabilities.backend_id,
        "structural_only": capabilities.backend_id != "docker",
        "safe_for_executable_tools": capabilities.safe_for_executable_tools,
        "cleanup": cleaned.cleanup,
    }


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

    def __init__(
        self,
        env: Any,
        *,
        config_digest: str,
        identity: SandboxIdentity | None = None,
    ) -> None:
        self.env = env
        self.config_digest = config_digest
        self.identity = identity or SandboxIdentity(
            sandbox_id=str(getattr(env, "_sandbox_id", "sandbox-unbound")),
            session_id="session:unbound",
            run_id="run:unbound",
            work_item_id="work:unbound",
            attempt_id="attempt:unbound",
            owner_generation=0,
        )
        self._capabilities: SandboxCapabilities | None = None
        self._receipt: SandboxReceipt | None = None

    def prepare(self) -> SandboxReceipt:
        policy = getattr(self.env, "policy", None)
        if policy is not None:
            if not isinstance(policy, SandboxPolicy):
                raise SandboxCapabilityMismatch("Docker policy has an invalid type")
            if policy.network_mode != "none":
                raise SandboxCapabilityMismatch(
                    "Docker reference backend does not implement safe egress allowlists"
                )
            if policy.supports_pause or policy.supports_snapshot or policy.supports_fork:
                raise SandboxCapabilityMismatch(
                    "Docker reference backend cannot satisfy requested pause/snapshot/fork"
                )
            if policy.workspace_mode not in {"private_copy", "ephemeral_empty"}:
                raise SandboxCapabilityMismatch(
                    "Docker reference backend cannot attest read-only source staging"
                )
            if policy.input_mounts:
                raise SandboxCapabilityMismatch(
                    "Docker reference backend does not implement explicit input mounts"
                )
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
        inspected_image = str(item.get("Image") or "").removeprefix("sha256:")
        if policy is not None and policy.image_digest is not None:
            if inspected_image != policy.image_digest:
                try:
                    self.cleanup()
                finally:
                    raise SandboxCapabilityMismatch(
                        "Docker image digest does not match the required policy digest"
                    )
        container_workspace = str(self.env.container_workspace)
        env_values = [str(value) for value in list(config.get("Env") or [])]
        sensitive_tokens = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION")
        tmpfs = dict(host.get("Tmpfs") or {})
        policy_limits = getattr(policy, "limits", None)
        workspace_destination = (
            policy.workspace_destination if policy is not None else container_workspace
        )
        output_destination = (
            policy.output_destination if policy is not None else "/results"
        )
        capabilities = SandboxCapabilities(
            backend_id=self.backend_id,
            isolated=(
                host.get("Privileged") is not True
                and not str(host.get("PidMode") or "")
                and str(host.get("IpcMode") or "") not in {"host"}
                and not list(host.get("Devices") or [])
                and not mounts
            ),
            non_root=str(config.get("User") or "") not in {"", "0", "root"},
            read_only_root=host.get("ReadonlyRootfs") is True,
            writable_workspace_only=(
                not mounts
                and workspace_destination in tmpfs
                and output_destination in tmpfs
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
            disk_bounded=(
                policy_limits is not None
                and workspace_destination in tmpfs
                and output_destination in tmpfs
            ),
            output_bounded=policy_limits is not None,
            time_bounded=(
                policy_limits is not None
                and getattr(self.env, "_wall_timer", None) is not None
            ),
            private_workspace=(
                policy is not None
                and policy.workspace_mode in {
                    "private_copy", "ephemeral_empty", "read_only_source"
                }
                and not mounts
            ),
            secret_broker=False,
            pause=False,
            snapshot=False,
            fork=False,
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
            "tmpfs": sorted(tmpfs),
            "privileged": host.get("Privileged"),
            "pid_mode": host.get("PidMode"),
            "ipc_mode": host.get("IpcMode"),
            "devices": len(list(host.get("Devices") or [])),
            "mounts": [
                {
                    "type": mount.get("Type"),
                    "destination": mount.get("Destination"),
                    "rw": mount.get("RW"),
                }
                for mount in mounts
            ],
            "credentials_injected": capabilities.credentials_injected,
            "labels": sorted(dict(config.get("Labels") or {})),
        }
        self._capabilities = capabilities
        self._receipt = SandboxReceipt(
            backend_id=self.backend_id,
            config_digest=self.config_digest,
            status=("prepared" if capabilities.safe_for_executable_tools else "rejected"),
            safety=("sandboxed" if capabilities.safe_for_executable_tools else "capability_loss"),
            capabilities=capabilities,
            attestation_digest=_digest(safe_inspect),
            policy_digest=(policy.digest if policy is not None else self.config_digest),
            image_digest=str(item.get("Image") or "").removeprefix("sha256:"),
            logical_identity=self.identity.to_dict(),
            workspace_digest=str(getattr(self.env, "workspace_digest", "")),
            input_digest=str(getattr(self.env, "input_digest", "")),
            lease={"owner_generation": 0, "state": "active"},
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
        cleanup = dict(getattr(self.env, "cleanup_receipt", {}) or {})
        if cleanup and not (
            cleanup.get("container_absent") and cleanup.get("staging_absent")
        ):
            raise SandboxCleanupFailure(
                "partially prepared Docker sandbox cleanup was not proven",
                receipt=cleanup,
            )

    def execute(self, command: str, *, timeout: int = 30) -> Mapping[str, Any]:
        policy = getattr(self.env, "policy", None)
        maximum = policy.limits.command_seconds if policy is not None else 180
        applied = min(maximum, max(1, int(timeout)))
        result = dict(self.env.cmd.run(command, timeout=applied))
        output_limit = policy.limits.output_bytes if policy is not None else 2_000_000
        for key in ("stdout", "stderr"):
            text = str(result.get(key) or "")
            if len(text.encode("utf-8")) > output_limit:
                result[key] = text.encode("utf-8")[:output_limit].decode(
                    "utf-8", errors="ignore"
                )
                result[f"{key}_truncated"] = True
        execution = SandboxExecutionReceipt(
            operation_id=f"sandbox-exec:{len(self._receipt.execution_receipts) if self._receipt else 0}",
            owner_generation=self.identity.owner_generation,
            status=str(result.get("status") or "error"),
            returncode=(
                int(result["returncode"])
                if isinstance(result.get("returncode"), int)
                else None
            ),
            timed_out=bool(result.get("timed_out", False)),
            worker_still_running=bool(result.get("worker_still_running", False)),
            outcome_unknown=bool(result.get("outcome_unknown", False)),
            stdout_bytes=int(result.get("stdout_bytes", len(str(result.get("stdout") or "").encode("utf-8")))),
            stderr_bytes=int(result.get("stderr_bytes", len(str(result.get("stderr") or "").encode("utf-8")))),
        )
        if self._receipt is not None:
            self._receipt = replace(
                self._receipt,
                execution_receipts=self._receipt.execution_receipts + (execution.to_dict(),),
            )
        return result

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
            policy_digest=previous.policy_digest,
            image_digest=previous.image_digest,
            logical_identity=previous.logical_identity,
            workspace_digest=str(
                getattr(self.env, "workspace_digest", previous.workspace_digest)
            ),
            input_digest=previous.input_digest,
            lease={"owner_generation": 0, "state": "closed"},
            execution_receipts=previous.execution_receipts,
            cleanup_receipt=dict(getattr(self.env, "cleanup_receipt", {})),
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

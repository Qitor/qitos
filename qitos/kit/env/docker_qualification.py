"""Executable, inspect-backed qualification for the Docker reference sandbox."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .sandbox import SandboxIdentity


class SandboxQualificationError(RuntimeError):
    """Typed fail-closed result for executable sandbox qualification."""

    code = "sandbox_qualification_failed"

    def __init__(
        self, message: str, *, field: Optional[str] = None
    ) -> None:
        super().__init__(message)
        self.field = field


def _run(command: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def _digest_json(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def workspace_digest(root: str | Path) -> str:
    """Hash regular workspace files, excluding VCS and qualification scratch."""
    base = Path(root).resolve()
    digest = hashlib.sha256()
    for path in sorted(base.rglob("*")):
        relative = path.relative_to(base)
        if not relative.parts or relative.parts[0] in {".git", ".qitos-qualification"}:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass
class SandboxQualificationReceipt:
    schema: str
    created_at: str
    identity: Dict[str, Any]
    container_id: str
    image_id: str
    config_digest: str
    policy_digest: str
    workspace_digest_before: str
    workspace_digest_after: str
    inspect_digest: str
    probes: Dict[str, Any] = field(default_factory=dict)
    unexpected_mounts: list[str] = field(default_factory=list)
    cleanup: Dict[str, Any] = field(default_factory=dict)
    status: str = "failed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "created_at": self.created_at,
            "identity": dict(self.identity),
            "container_id": self.container_id,
            "image_id": self.image_id,
            "config_digest": self.config_digest,
            "policy_digest": self.policy_digest,
            "workspace_digest_before": self.workspace_digest_before,
            "workspace_digest_after": self.workspace_digest_after,
            "inspect_digest": self.inspect_digest,
            "probes": dict(self.probes),
            "unexpected_mounts": list(self.unexpected_mounts),
            "cleanup": dict(self.cleanup),
            "status": self.status,
        }

    def digest(self) -> str:
        return _digest_json(self.to_dict())


def _probe_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "returncode": int(result.get("returncode", 1)),
        "ok": int(result.get("returncode", 1)) == 0,
        "stdout_sha256": hashlib.sha256(
            str(result.get("stdout", "")).encode("utf-8")
        ).hexdigest(),
        "stderr_present": bool(str(result.get("stderr", ""))),
    }


def qualify_docker_environment(
    config: Any,
    *,
    identity: SandboxIdentity,
    environment: Optional[Any] = None,
) -> SandboxQualificationReceipt:
    """Create, inspect, probe, and clean one real configured Docker sandbox."""
    from qitos.config.builder import build_environment

    env_config = config.runtime.environment
    if env_config.type != "docker":
        raise SandboxQualificationError(
            "sandbox qualification requires a docker environment",
            field="runtime.environment.type",
        )
    workspace = Path(env_config.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise SandboxQualificationError("configured workspace does not exist")
    read_candidates = [
        path
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and ".git" not in path.relative_to(workspace).parts
        and ".qitos-qualification" not in path.relative_to(workspace).parts
    ]
    if not read_candidates:
        raise SandboxQualificationError("sandbox workspace has no readable fixture")
    read_target = read_candidates[0].relative_to(workspace).as_posix()
    before = workspace_digest(workspace)
    scratch = workspace / ".qitos-qualification"
    scratch.mkdir(mode=0o700, exist_ok=False)
    env = environment if environment is not None else build_environment(config)
    receipt = SandboxQualificationReceipt(
        schema="qitos.sandbox.qualification/v1",
        created_at=datetime.now(timezone.utc).isoformat(),
        identity=identity.to_dict(),
        container_id="",
        image_id="",
        config_digest=config.digest(),
        policy_digest="",
        workspace_digest_before=before,
        workspace_digest_after="",
        inspect_digest="",
    )
    error: Optional[BaseException] = None
    try:
        env.setup(workspace=str(workspace))
        container = str(env.container)
        receipt.container_id = container
        inspected = _run(["docker", "inspect", container], timeout=30)
        if inspected.returncode != 0:
            raise SandboxQualificationError("docker inspect failed")
        payload = json.loads(inspected.stdout)
        if not isinstance(payload, list) or len(payload) != 1:
            raise SandboxQualificationError("docker inspect returned an invalid shape")
        item = payload[0]
        config_view = dict(item.get("Config") or {})
        host = dict(item.get("HostConfig") or {})
        mounts = list(item.get("Mounts") or [])
        receipt.image_id = str(item.get("Image") or "")
        inspect_safe = {
            "Id": item.get("Id"),
            "Image": item.get("Image"),
            "User": config_view.get("User"),
            "Labels": config_view.get("Labels"),
            "NetworkMode": host.get("NetworkMode"),
            "ReadonlyRootfs": host.get("ReadonlyRootfs"),
            "CapDrop": host.get("CapDrop"),
            "SecurityOpt": host.get("SecurityOpt"),
            "PidsLimit": host.get("PidsLimit"),
            "Memory": host.get("Memory"),
            "NanoCpus": host.get("NanoCpus"),
            "Tmpfs": host.get("Tmpfs"),
            "Mounts": [
                {
                    "Type": mount.get("Type"),
                    "Destination": mount.get("Destination"),
                    "RW": mount.get("RW"),
                }
                for mount in mounts
            ],
        }
        receipt.inspect_digest = _digest_json(inspect_safe)
        expected_policy = {
            "network": "none",
            "read_only_root": True,
            "cap_drop": ["ALL"],
            "no_new_privileges": True,
            "pids_limit": 256,
            "memory": 2 * 1024 * 1024 * 1024,
            "nano_cpus": 2_000_000_000,
            "tmpfs": "/tmp:rw,nosuid,nodev,noexec,size=256m",
            "user": f"{os.getuid()}:{os.getgid()}",
            "workspace_destination": env_config.container_workspace,
            "config_digest": config.digest(),
        }
        receipt.policy_digest = _digest_json(expected_policy)
        labels = dict(config_view.get("Labels") or {})
        security_options = [str(value) for value in list(host.get("SecurityOpt") or [])]
        cap_drop = [str(value).upper() for value in list(host.get("CapDrop") or [])]
        tmpfs = dict(host.get("Tmpfs") or {})
        actual_mounts = {str(mount.get("Destination") or "") for mount in mounts}
        receipt.unexpected_mounts = sorted(actual_mounts)
        receipt.probes.update(
            {
                "inspect_network_none": host.get("NetworkMode") == "none",
                "inspect_read_only_root": host.get("ReadonlyRootfs") is True,
                "inspect_capabilities_dropped": "ALL" in cap_drop,
                "inspect_no_new_privileges": any(
                    "no-new-privileges" in option for option in security_options
                ),
                "inspect_non_root_user": str(config_view.get("User") or "")
                == expected_policy["user"],
                "inspect_pid_limit": int(host.get("PidsLimit") or 0) == 256,
                "inspect_memory_limit": int(host.get("Memory") or 0)
                == expected_policy["memory"],
                "inspect_cpu_limit": int(host.get("NanoCpus") or 0)
                == expected_policy["nano_cpus"],
                "inspect_tmpfs": "/tmp" in tmpfs
                and all(
                    token in str(tmpfs.get("/tmp", ""))
                    for token in ("nosuid", "nodev", "noexec")
                )
                and any(
                    token in str(tmpfs.get("/tmp", ""))
                    for token in ("size=256m", "size=268435456")
                ),
                "inspect_private_workspace": (
                    not mounts
                    and env_config.container_workspace in tmpfs
                    and "/results" in tmpfs
                ),
                "inspect_no_unexpected_mount": not receipt.unexpected_mounts,
                "inspect_config_label": labels.get("qitos.config.digest")
                == config.digest(),
                "inspect_no_host_credentials": not any(
                    any(token in str(value).upper() for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION"))
                    for value in list(config_view.get("Env") or [])
                ),
            }
        )

        receipt.probes["identity"] = _probe_result(
            env.cmd.run("test \"$(id -u)\" != 0 && test \"$(pwd)\" = /workspace")
        )
        receipt.probes["capabilities"] = _probe_result(
            env.cmd.run(
                "command -v sh && command -v python3 && command -v git && command -v grep"
            )
        )
        receipt.probes["read"] = bool(env.fs.read_text(read_target) is not None)
        receipt.probes["grep"] = _probe_result(
            env.cmd.run(f"grep -R -n -- '' {read_target!r} >/dev/null", timeout=30)
        )
        env.fs.write_text(".qitos-qualification/probe.txt", "sandbox-ok\n")
        receipt.probes["write_readback"] = (
            env.fs.read_text(".qitos-qualification/probe.txt") == "sandbox-ok\n"
        )
        receipt.probes["test"] = _probe_result(
            env.cmd.run(
                "python3 -c \"from pathlib import Path; assert Path('.qitos-qualification/probe.txt').read_text() == 'sandbox-ok\\n'\""
            )
        )
        try:
            env.fs.read_text("../outside-workspace")
        except PermissionError:
            receipt.probes["path_escape_denied"] = True
        else:
            receipt.probes["path_escape_denied"] = False
        receipt.probes["rootfs_write_denied"] = (
            int(env.cmd.run("touch /qitos-rootfs-denial").get("returncode", 0)) != 0
        )
        receipt.probes["network_denied"] = (
            int(
                env.cmd.run(
                    "python3 -c \"import socket; s=socket.socket(); s.settimeout(1); s.connect(('1.1.1.1',53))\"",
                    timeout=5,
                ).get("returncode", 0)
            )
            != 0
        )
        receipt.probes["tmpfs_write"] = _probe_result(
            env.cmd.run("touch /tmp/qitos-probe && rm /tmp/qitos-probe")
        )
        receipt.workspace_digest_after = workspace_digest(workspace)
        receipt.probes["repository_digest_stable"] = (
            receipt.workspace_digest_after == receipt.workspace_digest_before
        )

        def _passed(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            return isinstance(value, dict) and value.get("ok") is True

        receipt.status = (
            "passed"
            if all(_passed(value) for value in receipt.probes.values())
            and not receipt.unexpected_mounts
            else "failed"
        )
        if receipt.status != "passed":
            failed = sorted(
                name
                for name, value in receipt.probes.items()
                if not _passed(value)
            )
            raise SandboxQualificationError(
                "executable sandbox probes failed: " + ", ".join(failed)
            )
    except BaseException as exc:
        error = exc
    finally:
        container = str(getattr(env, "container", "") or "")
        try:
            env.close()
            cleanup_inspect = (
                _run(["docker", "inspect", container], timeout=20)
                if container
                else None
            )
            receipt.cleanup = {
                "close_called": True,
                "container_absent": cleanup_inspect is None
                or cleanup_inspect.returncode != 0,
            }
        except Exception:
            receipt.cleanup = {"close_called": False, "container_absent": False}
        shutil.rmtree(scratch, ignore_errors=True)
        receipt.cleanup["scratch_absent"] = not scratch.exists()
        if not all(receipt.cleanup.values()):
            receipt.status = "failed"
            if error is None:
                error = SandboxQualificationError("sandbox cleanup attestation failed")
    if error is not None:
        if isinstance(error, SandboxQualificationError):
            setattr(error, "receipt", receipt.to_dict())
            raise error
        wrapped = SandboxQualificationError(
            f"sandbox qualification failed: {type(error).__name__}"
        )
        setattr(wrapped, "receipt", receipt.to_dict())
        raise wrapped from error
    return receipt


__all__ = [
    "SandboxIdentity",
    "SandboxQualificationError",
    "SandboxQualificationReceipt",
    "qualify_docker_environment",
    "workspace_digest",
]

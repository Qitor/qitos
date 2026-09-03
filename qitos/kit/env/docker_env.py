"""Docker-backed environment and capabilities."""

from __future__ import annotations

import shlex
import subprocess
import threading
import posixpath
import hashlib
import json
import os
import shutil
import tempfile
import tarfile
from uuid import uuid4
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from qitos.core.env import (
    CommandCapability,
    EnvCapabilityError,
    FileSnapshot,
    FileSystemCapability,
    ProcessControlCapability,
    ProcessHandle,
)
from qitos.kit.env.host_env import HostEnv
from qitos.kit.env.sandbox import SandboxPolicy, SandboxResourceLimits


def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return digest.hexdigest()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not relative.parts or relative.parts[0] in {".git", ".ssh"}:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class DockerCommandCapability(CommandCapability):
    def __init__(
        self,
        container: str,
        workdir: str = "/workspace",
        *,
        output_limit: int = 2 * 1024 * 1024,
    ):
        self.container = container
        self.workdir = workdir
        self.output_limit = max(1, int(output_limit))

    def run(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        if not command or not command.strip():
            return {"status": "error", "error": "empty command"}
        program = """
import json, os, signal, subprocess, sys, tempfile
command = bytes.fromhex(sys.argv[1]).decode('utf-8')
workdir, timeout_raw, output_raw = sys.argv[2:5]
timeout = max(1, int(timeout_raw)); output_limit = max(1, int(output_raw))
timed_out = False
with tempfile.TemporaryDirectory(prefix='qitos-command-', dir='/tmp') as root:
    out_path = os.path.join(root, 'stdout'); err_path = os.path.join(root, 'stderr')
    with open(out_path, 'wb') as stdout, open(err_path, 'wb') as stderr:
        process = subprocess.Popen(
            command, shell=True, cwd=workdir, stdout=stdout, stderr=stderr,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                returncode = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                returncode = process.wait(timeout=2)
    def bounded(path):
        size = os.path.getsize(path)
        with open(path, 'rb') as stream:
            raw = stream.read(output_limit)
        return raw.decode('utf-8', errors='replace'), size > output_limit, size
    stdout, stdout_truncated, stdout_bytes = bounded(out_path)
    stderr, stderr_truncated, stderr_bytes = bounded(err_path)
print(json.dumps({
    'status': 'error' if timed_out else ('success' if returncode == 0 else 'partial'),
    'returncode': returncode, 'stdout': stdout, 'stderr': stderr,
    'stdout_truncated': stdout_truncated, 'stderr_truncated': stderr_truncated,
    'stdout_bytes': stdout_bytes, 'stderr_bytes': stderr_bytes,
    'timed_out': timed_out, 'worker_still_running': False, 'outcome_unknown': False,
}))
"""
        docker_cmd = [
            "docker",
            "exec",
            "-w",
            self.workdir,
            self.container,
            "python3",
            "-c",
            program,
            command.encode("utf-8").hex(),
            self.workdir,
            str(max(1, int(timeout))),
            str(self.output_limit),
        ]
        try:
            r = _run(docker_cmd, timeout=max(1, int(timeout)) + 10)
            if r.returncode != 0:
                return {
                    "status": "error",
                    "error": "container command wrapper failed",
                    "returncode": r.returncode,
                    "stdout": "",
                    "stderr": r.stderr[: self.output_limit],
                    "command": command,
                    "outcome_unknown": True,
                }
            payload = dict(json.loads(r.stdout))
            payload["command"] = command
            return payload
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "error": "container command wrapper exceeded its control deadline",
                "command": command,
                "timed_out": True,
                "worker_still_running": True,
                "outcome_unknown": True,
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": f"container command failed: {type(exc).__name__}",
                "command": command,
                "outcome_unknown": False,
            }


class DockerFSCapability(FileSystemCapability):
    def __init__(
        self,
        container: str,
        workdir: str = "/workspace",
        *,
        strict_workspace: bool = False,
    ):
        self.container = container
        self.workdir = workdir.rstrip("/") or "/workspace"
        self.strict_workspace = bool(strict_workspace)
        self.cmd = DockerCommandCapability(container=container, workdir=workdir)

    def read_text(self, path: str) -> str:
        inner = self._inner_path(path)
        program = (
            "import os,sys; root=sys.argv[1]; path=sys.argv[2]; "
            "real=os.path.realpath(path); prefix=root.rstrip('/')+'/'; "
            "assert real==root or real.startswith(prefix), 'path escape'; "
            "f=open(real,'r',encoding='utf-8'); data=f.read(); f.close(); "
            "sys.stdout.write(data)"
        )
        result = self.cmd.run(
            "python3 -c " + shlex.quote(program) + " "
            + shlex.quote(self.workdir) + " " + shlex.quote(inner)
        )
        if result.get("returncode", 1) != 0:
            raise RuntimeError(str(result.get("stderr", "failed to read file")))
        return str(result.get("stdout", ""))

    def write_text(self, path: str, content: str) -> None:
        self.atomic_write_text(path, content)

    def list_files(self, path: str = ".", limit: int = 200) -> list[str]:
        inner = self._inner_path(path)
        cmd = f"find {shlex.quote(inner)} -type f | head -n {int(limit)}"
        result = self.cmd.run(cmd)
        if result.get("returncode", 1) != 0:
            return []
        prefix = self.workdir.rstrip("/") + "/"
        out: list[str] = []
        for line in str(result.get("stdout", "")).splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(line[len(prefix) :] if line.startswith(prefix) else line)
        return out

    def exists(self, path: str) -> bool:
        inner = self._inner_path(path)
        result = self.cmd.run(f"test -e {shlex.quote(inner)}")
        return int(result.get("returncode", 1)) == 0

    def snapshot(self, path: str) -> FileSnapshot:
        inner = self._inner_path(path)
        program = (
            "import hashlib,json,os,sys; root=sys.argv[1]; path=sys.argv[2]; "
            "real=os.path.realpath(path); prefix=root.rstrip('/')+'/'; "
            "assert real==root or real.startswith(prefix), 'path escape'; "
            "raw=open(real,'rb').read(); s=os.stat(real,follow_symlinks=False); "
            "print(json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),"
            "'byte_length':len(raw),'version':f'{s.st_dev}:{s.st_ino}:{s.st_mtime_ns}:{s.st_size}'}))"
        )
        result = self.cmd.run(
            "python3 -c " + shlex.quote(program) + " "
            + shlex.quote(self.workdir) + " " + shlex.quote(inner)
        )
        if int(result.get("returncode", 1)) != 0:
            raise EnvCapabilityError("file_snapshot_failed", "file snapshot failed")
        payload = json.loads(str(result.get("stdout") or "{}"))
        relative = posixpath.relpath(inner, self.workdir)
        return FileSnapshot(
            path=relative,
            sha256=str(payload["sha256"]),
            byte_length=int(payload["byte_length"]),
            version=str(payload["version"]),
        )

    def atomic_write_text(
        self,
        path: str,
        content: str,
        *,
        expected_sha256: Optional[str] = None,
    ) -> FileSnapshot:
        inner = self._inner_path(path)
        program = (
            "import hashlib,os,sys,tempfile; root,path,expected=sys.argv[1:4]; "
            "parent=os.path.dirname(path); os.makedirs(parent,exist_ok=True); "
            "real_parent=os.path.realpath(parent); prefix=root.rstrip('/')+'/'; "
            "assert real_parent==root or real_parent.startswith(prefix), 'path escape'; "
            "assert not os.path.lexists(path) or not os.path.islink(path), 'symlink target'; "
            "current=(hashlib.sha256(open(path,'rb').read()).hexdigest() if os.path.exists(path) else ''); "
            "assert not expected or current==expected, 'stale file'; "
            "fd,tmp=tempfile.mkstemp(prefix='.qitos-',dir=real_parent); "
            "f=os.fdopen(fd,'wb'); f.write(sys.stdin.buffer.read()); f.flush(); os.fsync(f.fileno()); f.close(); "
            "os.replace(tmp,path)"
        )
        result = subprocess.run(
            [
                "docker", "exec", "-i", "-w", self.workdir, self.container,
                "python3", "-c", program, self.workdir, inner,
                expected_sha256 or "",
            ],
            input=content,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            stderr = str(result.stderr or "")
            code = "stale_file" if "stale file" in stderr else "file_write_failed"
            raise EnvCapabilityError(code, "atomic file mutation was rejected")
        return self.snapshot(path)

    def _inner_path(self, path: str) -> str:
        value = str(path)
        candidate = (
            posixpath.normpath(value)
            if value.startswith("/")
            else posixpath.normpath(posixpath.join(self.workdir, value or "."))
        )
        if self.strict_workspace and not (
            candidate == self.workdir
            or candidate.startswith(self.workdir.rstrip("/") + "/")
        ):
            raise PermissionError("path is outside the configured container workspace")
        return candidate


class DockerProcessControlCapability(ProcessControlCapability):
    """Bounded control for processes started inside one owned container."""

    def __init__(self, command: DockerCommandCapability, *, generation: int = 0) -> None:
        self.command = command
        self.generation = generation
        self._owned: set[str] = set()

    def start(self, command: str) -> ProcessHandle:
        if not command or not command.strip():
            raise EnvCapabilityError("invalid_command", "command must be non-empty")
        process_id = f"process-{uuid4().hex}"
        base = f"/tmp/qitos-processes/{process_id}"
        script = (
            f"mkdir -p /tmp/qitos-processes; "
            f"( sh -lc {shlex.quote(command)}; rc=$?; printf '%s' \"$rc\" >{shlex.quote(base + '.rc')} ) "
            f">{shlex.quote(base + '.out')} 2>{shlex.quote(base + '.err')} & "
            f"echo $! >{shlex.quote(base + '.pid')}"
        )
        result = self.command.run(script, timeout=10)
        if int(result.get("returncode", 1)) != 0:
            raise EnvCapabilityError("process_start_failed", "owned process did not start")
        self._owned.add(process_id)
        return ProcessHandle(process_id, self.generation)

    def poll(self, handle: ProcessHandle) -> Dict[str, Any]:
        base = self._base(handle)
        script = (
            f"pid=$(cat {shlex.quote(base + '.pid')}); "
            f"if [ -f {shlex.quote(base + '.rc')} ]; then state=terminal; rc=$(cat {shlex.quote(base + '.rc')}); "
            f"elif kill -0 \"$pid\" 2>/dev/null; then state=running; rc=; "
            f"else state=unknown; rc=; fi; "
            f"printf 'QITOS_STATE=%s\\nQITOS_RC=%s\\n' \"$state\" \"$rc\"; "
            f"printf 'QITOS_STDOUT\\n'; tail -c 64000 {shlex.quote(base + '.out')} 2>/dev/null; "
            f"printf '\\nQITOS_STDERR\\n'; tail -c 64000 {shlex.quote(base + '.err')} 2>/dev/null"
        )
        result = self.command.run(script, timeout=10)
        text = str(result.get("stdout") or "")
        header, _, rest = text.partition("QITOS_STDOUT\n")
        stdout, _, stderr = rest.partition("\nQITOS_STDERR\n")
        state = next(
            (line.partition("=")[2] for line in header.splitlines() if line.startswith("QITOS_STATE=")),
            "unknown",
        )
        raw_rc = next(
            (line.partition("=")[2] for line in header.splitlines() if line.startswith("QITOS_RC=")),
            "",
        )
        return {
            "status": state,
            "returncode": int(raw_rc) if raw_rc.isdigit() else None,
            "stdout": stdout,
            "stderr": stderr,
            "worker_still_running": state == "running",
            "outcome_unknown": state == "unknown",
        }

    def terminate(self, handle: ProcessHandle, timeout: int = 5) -> Dict[str, Any]:
        base = self._base(handle)
        seconds = max(1, min(30, int(timeout)))
        script = (
            f"pid=$(cat {shlex.quote(base + '.pid')}); kill -TERM \"$pid\" 2>/dev/null || true; "
            f"i=0; while kill -0 \"$pid\" 2>/dev/null && [ $i -lt {seconds * 10} ]; do i=$((i+1)); sleep 0.1; done; "
            f"if kill -0 \"$pid\" 2>/dev/null; then kill -KILL \"$pid\" 2>/dev/null || true; fi; "
            f"printf '143' >{shlex.quote(base + '.rc')}"
        )
        self.command.run(script, timeout=seconds + 5)
        result = self.poll(handle)
        result["termination"] = (
            "owned_process_reaped" if not result["worker_still_running"] else "outcome_unknown"
        )
        return result

    def close(self) -> None:
        for process_id in tuple(self._owned):
            try:
                self.terminate(ProcessHandle(process_id, self.generation))
            except Exception:
                pass
        self._owned.clear()
        self.generation += 1

    def _base(self, handle: ProcessHandle) -> str:
        if handle.owner_generation != self.generation:
            raise EnvCapabilityError("stale_generation", "process handle is stale")
        if handle.process_id not in self._owned:
            raise EnvCapabilityError("process_not_found", "process is not owned by this Env")
        return f"/tmp/qitos-processes/{handle.process_id}"


class DockerEnv(HostEnv):
    """HostEnv-compatible action interpreter executed inside Docker.

    Supports two modes:
    1. Attach existing container: pass `container`.
    2. Auto-create ephemeral container: pass `image` and set `auto_create=True`.
    """

    name = "docker_env"
    version = "1.1"

    def __init__(
        self,
        container: Optional[str] = None,
        workspace_root: str = "/workspace",
        *,
        image: Optional[str] = None,
        host_workspace: Optional[str] = None,
        auto_create: bool = False,
        remove_on_close: bool = False,
        network: Optional[str] = None,
        extra_run_args: Optional[list[str]] = None,
        container_env: Optional[Dict[str, str]] = None,
        create_timeout: int = 60,
        strict_workspace: bool = False,
        policy: Optional[SandboxPolicy] = None,
    ):
        self.container = str(container).strip() if container else ""
        self.container_workspace = workspace_root
        self.image = str(image or "").strip()
        self.host_workspace = str(host_workspace).strip() if host_workspace else ""
        self.auto_create = bool(auto_create)
        self.remove_on_close = bool(remove_on_close)
        self.network = network
        self.extra_run_args = list(extra_run_args or [])
        self.container_env = {
            str(key): str(value) for key, value in dict(container_env or {}).items()
        }
        self.create_timeout = int(create_timeout)
        self.strict_workspace = bool(strict_workspace)
        self._created_here = False
        self._create_attempted = False
        self._closed = False
        self._sandbox_id = f"sandbox-{uuid4().hex}"
        self._private_staging_root = ""
        self._source_workspace = self.host_workspace
        self.input_digest = ""
        self.workspace_digest = ""
        self.cleanup_receipt: Dict[str, Any] = {}
        self._wall_timer: Optional[threading.Timer] = None
        self._config_digest_label = ""
        self.policy = policy
        if self.strict_workspace and self.auto_create:
            self.policy = policy or self._policy_from_legacy_args()
            self.extra_run_args = []
            self.container_env = {}

        if not self.container and self.auto_create:
            self.container = (
                f"qitos_{Path(self.host_workspace or 'workspace').name}_"
                f"{threading.get_ident()}_{uuid4().hex[:10]}"
            )

        fs = DockerFSCapability(
            container=self.container or "",
            workdir=workspace_root,
            strict_workspace=self.strict_workspace,
        )
        cmd = DockerCommandCapability(
            container=self.container or "",
            workdir=workspace_root,
            output_limit=(policy.limits.output_bytes if policy is not None else 2 * 1024 * 1024),
        )
        super().__init__(workspace_root=workspace_root, fs=fs, cmd=cmd)
        self.processes.close()
        self.processes = DockerProcessControlCapability(cmd)

    def setup(
        self, task: Any = None, workspace: Optional[str] = None, **kwargs: Any
    ) -> None:
        if workspace and not self.host_workspace:
            self.host_workspace = str(Path(workspace).resolve())
        if self.auto_create:
            self._ensure_container()
        if not self.container:
            raise ValueError(
                "DockerEnv requires `container` or `auto_create=True` with `image`"
            )

        self.fs = DockerFSCapability(
            container=self.container,
            workdir=self.container_workspace,
            strict_workspace=self.strict_workspace,
        )
        self.cmd = DockerCommandCapability(
            container=self.container,
            workdir=self.container_workspace,
            output_limit=(
                self.policy.limits.output_bytes
                if self.policy is not None
                else 2 * 1024 * 1024
            ),
        )
        self.processes = DockerProcessControlCapability(self.cmd)

    def reset(self, task: Any = None, workspace: Optional[str] = None, **kwargs: Any):
        self.setup(task=task, workspace=workspace, **kwargs)
        self.workspace_root = workspace or self.container_workspace
        self._last_error = None
        return self.observe(state=None)

    def health_check(self) -> Dict[str, Any]:
        if not self.container:
            return {"ok": False, "message": "container is empty"}

        inspect = _run(["docker", "inspect", self.container], timeout=20)
        if inspect.returncode != 0:
            return {
                "ok": False,
                "message": "docker inspect failed",
                "container": self.container,
                "stderr": inspect.stderr,
            }

        probe = self.cmd.run("pwd", timeout=10)
        if int(probe.get("returncode", 1)) != 0:
            return {
                "ok": False,
                "message": "docker exec probe failed",
                "container": self.container,
                "stderr": probe.get("stderr", ""),
            }
        return {
            "ok": True,
            "workspace_root": self.workspace_root,
        }

    def close(self) -> None:
        if self._closed:
            if self.cleanup_receipt:
                self.cleanup_receipt["repeated"] = True
            return
        try:
            if self._wall_timer is not None:
                self._wall_timer.cancel()
            self.processes.close()
            if self.policy is not None and self._created_here:
                self._export_private_workspace()
        finally:
            ownership_ok = self._owns_container()
            if (
                self.container
                and self.remove_on_close
                and (self._created_here or self._create_attempted)
                and ownership_ok
            ):
                _run(["docker", "rm", "-f", self.container], timeout=30)
            if self._private_staging_root:
                shutil.rmtree(self._private_staging_root, ignore_errors=True)
            absent = True
            if self.container and (self._created_here or self._create_attempted):
                try:
                    absent = _run(
                        ["docker", "inspect", self.container], timeout=20
                    ).returncode != 0
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    absent = False
            staging_absent = (
                not self._private_staging_root
                or not Path(self._private_staging_root).exists()
            )
            self.cleanup_receipt = {
                "sandbox_id": self._sandbox_id,
                "container_absent": absent,
                "staging_absent": staging_absent,
                "repeated": False,
            }
            self._closed = absent and staging_absent

    def _ensure_container(self) -> None:
        if not self.container:
            raise ValueError("auto_create needs container name")

        inspect = _run(["docker", "inspect", self.container], timeout=20)
        if inspect.returncode == 0:
            if self.policy is not None and not self._created_here:
                raise RuntimeError("refusing to attach an unowned sandbox container")
            start = _run(["docker", "start", self.container], timeout=20)
            if start.returncode != 0:
                raise RuntimeError(
                    f"Failed to start container {self.container}: {start.stderr}"
                )
            return

        if not self.image:
            raise ValueError("auto_create requires `image`")

        run_cmd = ["docker", "run", "-d", "--name", self.container]
        if self.policy is not None:
            run_cmd += self._policy_run_args()
        elif self.network:
            run_cmd += ["--network", self.network]

        for key, value in sorted(self.container_env.items()):
            run_cmd += ["-e", f"{key}={value}"]

        if self.host_workspace and self.policy is None:
            host = str(Path(self.host_workspace).resolve())
            run_cmd += ["-v", f"{host}:{self.container_workspace}"]

        if self.extra_run_args:
            run_cmd += list(self.extra_run_args)

        run_cmd += [self.image, "sh", "-lc", "while true; do sleep 3600; done"]
        self._create_attempted = True
        proc = _run(run_cmd, timeout=self.create_timeout)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to create container {self.container}: {proc.stderr}"
            )
        self._created_here = True
        if self.policy is not None:
            self._wall_timer = threading.Timer(
                self.policy.limits.wall_seconds, self.close
            )
            self._wall_timer.daemon = True
            self._wall_timer.start()
        if self.policy is not None:
            try:
                self._stage_private_workspace()
            except Exception:
                if self._wall_timer is not None:
                    self._wall_timer.cancel()
                _run(["docker", "rm", "-f", self.container], timeout=30)
                self._created_here = False
                raise

    def _owns_container(self) -> bool:
        if not self.container or self.policy is None:
            return True
        try:
            inspected = _run(["docker", "inspect", self.container], timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        if inspected.returncode != 0:
            return False
        try:
            item = json.loads(inspected.stdout)[0]
            labels = dict(item.get("Config", {}).get("Labels") or {})
        except (IndexError, TypeError, ValueError, json.JSONDecodeError):
            return False
        return labels.get("qitos.sandbox.id") == self._sandbox_id

    def get_ops(self, group: str) -> Any:
        if group == "process_control":
            return self.processes
        return super().get_ops(group)

    def _policy_from_legacy_args(self) -> SandboxPolicy:
        """Bounded compatibility reader for the former declarative Docker flags."""
        recognized_prefixes = (
            "--pids-limit=", "--memory=", "--cpus=", "--ulimit=nofile=",
            "--tmpfs=/tmp:", "--user=", "--env=HOME=", "--label=qitos.config.digest=",
        )
        recognized_exact = {
            "--cap-drop=ALL", "--security-opt=no-new-privileges:true", "--read-only"
        }
        unknown = [
            item for item in self.extra_run_args
            if item not in recognized_exact
            and not any(item.startswith(prefix) for prefix in recognized_prefixes)
        ]
        if unknown:
            raise ValueError("unsupported free-form Docker security argument")

        def value(prefix: str, default: str) -> str:
            return next(
                (item[len(prefix):] for item in self.extra_run_args if item.startswith(prefix)),
                default,
            )
        memory = value("--memory=", "2048m").lower()
        memory_bytes = int(float(memory[:-1]) * 1024 * 1024) if memory.endswith("m") else int(memory)
        user = value("--user=", f"{os.getuid()}:{os.getgid()}").split(":", 1)
        self._config_digest_label = value("--label=qitos.config.digest=", "")
        limits = SandboxResourceLimits(
            cpu_count=float(value("--cpus=", "2")),
            memory_bytes=memory_bytes,
            pids=int(value("--pids-limit=", "256")),
            file_descriptors=int(value("--ulimit=nofile=", "1024:1024").split(":", 1)[0]),
        )
        return SandboxPolicy.coding(
            self.image,
            uid=int(user[0]),
            gid=int(user[1]),
            limits=limits,
        )

    def _policy_run_args(self) -> list[str]:
        if self.policy is None:
            return []
        policy = self.policy
        limits = policy.limits
        uid_gid = f"{policy.run_as_uid}:{policy.run_as_gid}"
        args = [
            "--network", policy.network_mode,
            "--pids-limit", str(limits.pids),
            "--memory", str(limits.memory_bytes),
            "--cpus", str(limits.cpu_count),
            "--ulimit", f"nofile={limits.file_descriptors}:{limits.file_descriptors}",
            "--tmpfs", f"/tmp:rw,nosuid,nodev,noexec,size={limits.tmpfs_bytes},uid={policy.run_as_uid},gid={policy.run_as_gid}",
            "--tmpfs", f"{policy.workspace_destination}:rw,nosuid,nodev,size={limits.disk_bytes},uid={policy.run_as_uid},gid={policy.run_as_gid}",
            "--tmpfs", f"{policy.output_destination}:rw,nosuid,nodev,noexec,size={limits.output_bytes},uid={policy.run_as_uid},gid={policy.run_as_gid}",
            "--user", uid_gid,
            "--env", "HOME=/tmp/qitos-home",
            "--label", f"qitos.sandbox.id={self._sandbox_id}",
            "--label", "qitos.sandbox.owner-generation=0",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--read-only",
        ]
        if self._config_digest_label:
            args += ["--label", f"qitos.config.digest={self._config_digest_label}"]
        return args

    def _stage_private_workspace(self) -> None:
        if self.policy is None or self.policy.workspace_mode == "ephemeral_empty":
            return
        if not self._source_workspace:
            raise ValueError("private workspace staging requires a source workspace")
        source = Path(self._source_workspace).resolve()
        if not source.is_dir():
            raise ValueError("source workspace does not exist")
        staging = Path(tempfile.mkdtemp(prefix="qitos-sandbox-"))
        self._private_staging_root = str(staging)
        staged_input = staging / "input"

        def ignore(directory: str, names: list[str]) -> set[str]:
            base = Path(directory)
            ignored = {
                name for name in names
                if (base / name).is_symlink()
                or name in {".git", ".env", ".ssh", ".gnupg", ".aws"}
                or name.endswith((".pem", ".key"))
            }
            return ignored

        shutil.copytree(
            source,
            staged_input,
            symlinks=True,
            ignore=ignore,
        )
        self.input_digest = _tree_digest(staged_input)
        self.workspace_digest = self.input_digest
        archive = staging / "input.tar"
        with tarfile.open(archive, mode="w") as bundle:
            for item in sorted(staged_input.rglob("*")):
                if item.is_symlink():
                    continue
                bundle.add(item, arcname=item.relative_to(staged_input), recursive=False)
        # Streaming tar readers are not seekable; validate the controller-built
        # archive locally, then extract it in the private tmpfs as container root.
        with tarfile.open(archive, mode="r") as bundle:
            for member in bundle.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts or member.issym():
                    raise RuntimeError("private workspace archive validation failed")
        extractor = """
import pathlib, shutil, sys, tarfile
root = pathlib.Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
with tarfile.open(fileobj=sys.stdin.buffer, mode='r|') as bundle:
    for member in bundle:
        relative = pathlib.PurePosixPath(member.name)
        if relative.is_absolute() or '..' in relative.parts or member.issym() or member.islnk():
            raise ValueError('unsafe archive member')
        target = root.joinpath(*relative.parts)
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        elif member.isfile():
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise ValueError('missing archive body')
            with target.open('wb') as output:
                shutil.copyfileobj(source, output)
        else:
            raise ValueError('unsupported archive member')
"""
        with archive.open("rb") as stream:
            copied = subprocess.run(
                [
                    "docker", "exec", "-i", "-u",
                    f"{self.policy.run_as_uid}:{self.policy.run_as_gid}",
                    self.container,
                    "python3", "-c", extractor, self.container_workspace,
                ],
                stdin=stream,
                capture_output=True,
                text=False,
                timeout=self.create_timeout,
            )
        if copied.returncode != 0:
            detail = bytes(copied.stderr or b"").decode("utf-8", errors="replace").strip()[:500]
            raise RuntimeError(f"private workspace staging failed: {detail}")

    def _export_private_workspace(self) -> None:
        if self.policy is None or not self._source_workspace or not self._created_here:
            return
        staging = Path(self._private_staging_root or tempfile.mkdtemp(prefix="qitos-sandbox-"))
        self._private_staging_root = str(staging)
        exported = staging / "export"
        exported.mkdir(parents=True, exist_ok=True)
        copied = _run(
            ["docker", "cp", f"{self.container}:{self.container_workspace}/.", str(exported)],
            timeout=self.create_timeout,
        )
        if copied.returncode != 0:
            raise RuntimeError("sandbox workspace export failed")
        total = 0
        files: list[tuple[Path, Path]] = []
        source = Path(self._source_workspace).resolve()
        for item in sorted(exported.rglob("*")):
            relative = item.relative_to(exported)
            if not relative.parts or relative.parts[0] == ".git" or item.is_symlink():
                continue
            if item.is_file():
                total += item.stat().st_size
                if total > self.policy.limits.disk_bytes:
                    raise RuntimeError("sandbox export exceeded disk bound")
                files.append((item, source / relative))
        for item, target in files:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.qitos-export-{uuid4().hex}")
            shutil.copyfile(item, temporary)
            os.replace(temporary, target)
        self.workspace_digest = _tree_digest(exported)


class DockerEnvScheduler:
    """Simple bounded scheduler for per-task DockerEnv creation.

    Useful for benchmark batch runs to control concurrent docker containers.
    """

    def __init__(self, max_active: int = 1):
        self.max_active = max(1, int(max_active))
        self._sem = threading.Semaphore(self.max_active)

    @contextmanager
    def allocate(
        self,
        *,
        image: str,
        host_workspace: str,
        workspace_root: str = "/workspace",
        network: Optional[str] = None,
        extra_run_args: Optional[list[str]] = None,
    ) -> Iterator[DockerEnv]:
        self._sem.acquire()
        env = DockerEnv(
            workspace_root=workspace_root,
            image=image,
            host_workspace=host_workspace,
            auto_create=True,
            remove_on_close=True,
            network=network,
            extra_run_args=extra_run_args,
        )
        try:
            env.setup(workspace=host_workspace)
            yield env
        finally:
            try:
                env.close()
            finally:
                self._sem.release()


__all__ = [
    "DockerCommandCapability",
    "DockerFSCapability",
    "DockerEnv",
    "DockerEnvScheduler",
]

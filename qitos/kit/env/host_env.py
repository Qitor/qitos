"""Host environment with filesystem + command capabilities."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import hashlib
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from qitos.core.action import Action
from qitos.core.env import (
    CommandCapability,
    Env,
    EnvObservation,
    EnvStepResult,
    EnvCapabilityError,
    FileSnapshot,
    FileSystemCapability,
    ProcessControlCapability,
    ProcessHandle,
)


class HostFSCapability(FileSystemCapability):
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def read_text(self, path: str) -> str:
        p = self._resolve(path)
        return p.read_text(encoding="utf-8")

    def write_text(self, path: str, content: str) -> None:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def list_files(self, path: str = ".", limit: int = 200) -> List[str]:
        base = self._resolve(path)
        if base.is_file():
            return [str(base.relative_to(self.root))]
        out: List[str] = []
        for p in sorted(base.rglob("*")):
            if p.is_file():
                out.append(str(p.relative_to(self.root)))
                if len(out) >= limit:
                    break
        return out

    def exists(self, path: str) -> bool:
        try:
            return self._resolve(path).exists()
        except Exception:
            return False

    def snapshot(self, path: str) -> FileSnapshot:
        target = self._resolve(path)
        raw = target.read_bytes()
        stat = target.stat()
        return FileSnapshot(
            path=str(target.relative_to(self.root)),
            sha256=hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            version=f"{stat.st_dev}:{stat.st_ino}:{stat.st_mtime_ns}:{stat.st_size}",
        )

    def atomic_write_text(
        self,
        path: str,
        content: str,
        *,
        expected_sha256: Optional[str] = None,
    ) -> FileSnapshot:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if expected_sha256 is not None:
            if not target.exists():
                raise EnvCapabilityError("stale_file", "expected file is absent")
            current = hashlib.sha256(target.read_bytes()).hexdigest()
            if current != expected_sha256:
                raise EnvCapabilityError("stale_file", "file changed since it was read")
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.qitos-", dir=str(target.parent)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return self.snapshot(path)

    def _resolve(self, path: str) -> Path:
        raw = str(path or ".")
        candidate = Path(raw)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise PermissionError("path must be workspace-relative")
        lexical = self.root / candidate
        current = self.root
        for part in candidate.parts:
            if part in {"", "."}:
                continue
            current = current / part
            if current.is_symlink():
                raise PermissionError("symbolic-link paths are not allowed")
        p = lexical.resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError("path is outside the capability root")
        return p


class HostCommandCapability(CommandCapability):
    def __init__(self, cwd: str, *, output_limit: int = 2 * 1024 * 1024):
        self.cwd = str(Path(cwd).resolve())
        self.output_limit = max(1, int(output_limit))

    def run(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        if not command or not command.strip():
            return {"status": "error", "error": "empty command"}
        stdout = tempfile.TemporaryFile(mode="w+b")
        stderr = tempfile.TemporaryFile(mode="w+b")
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=stdout,
                stderr=stderr,
                cwd=self.cwd,
                start_new_session=True,
            )
            timed_out = False
            try:
                returncode = process.wait(timeout=max(1, int(timeout)))
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    returncode = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    returncode = process.wait(timeout=2)
            out_text, out_truncated, out_bytes = self._bounded_output(stdout)
            err_text, err_truncated, err_bytes = self._bounded_output(stderr)
            return {
                "status": (
                    "error" if timed_out else ("success" if returncode == 0 else "partial")
                ),
                "returncode": returncode,
                "stdout": out_text,
                "stderr": err_text,
                "stdout_truncated": out_truncated,
                "stderr_truncated": err_truncated,
                "stdout_bytes": out_bytes,
                "stderr_bytes": err_bytes,
                "cwd": self.cwd,
                "command": command,
                "timed_out": timed_out,
                "worker_still_running": False,
                "outcome_unknown": False,
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "command": command,
                "cwd": self.cwd,
            }
        finally:
            stdout.close()
            stderr.close()

    def _bounded_output(self, stream: Any) -> tuple[str, bool, int]:
        stream.flush()
        size = stream.tell()
        stream.seek(0)
        raw = stream.read(self.output_limit)
        return raw.decode("utf-8", errors="replace"), size > self.output_limit, size


@dataclass
class _OwnedHostProcess:
    process: subprocess.Popen[str]
    stdout: Any
    stderr: Any


class HostProcessControlCapability(ProcessControlCapability):
    """Explicitly unisolated process control for the unsafe HostEnv adapter."""

    def __init__(self, cwd: str, *, output_limit: int = 64_000) -> None:
        self.cwd = str(Path(cwd).resolve())
        self.output_limit = max(1, int(output_limit))
        self._lock = threading.Lock()
        self._processes: Dict[str, _OwnedHostProcess] = {}
        self._generation = 0

    def start(self, command: str) -> ProcessHandle:
        if not command or not command.strip():
            raise EnvCapabilityError("invalid_command", "command must be non-empty")
        stdout = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        stderr = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=self.cwd,
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
        )
        process_id = f"host-process-{process.pid}"
        with self._lock:
            self._processes[process_id] = _OwnedHostProcess(process, stdout, stderr)
        return ProcessHandle(process_id, self._generation)

    def poll(self, handle: ProcessHandle) -> Dict[str, Any]:
        owned = self._owned(handle)
        returncode = owned.process.poll()
        return {
            "status": "running" if returncode is None else "terminal",
            "returncode": returncode,
            "stdout": self._read(owned.stdout),
            "stderr": self._read(owned.stderr),
            "worker_still_running": returncode is None,
        }

    def terminate(self, handle: ProcessHandle, timeout: int = 5) -> Dict[str, Any]:
        owned = self._owned(handle)
        if owned.process.poll() is None:
            os.killpg(owned.process.pid, signal.SIGTERM)
            try:
                owned.process.wait(timeout=max(1, int(timeout)))
            except subprocess.TimeoutExpired:
                os.killpg(owned.process.pid, signal.SIGKILL)
                owned.process.wait(timeout=max(1, int(timeout)))
        result = self.poll(handle)
        result["termination"] = "owned_process_reaped"
        return result

    def close(self) -> None:
        with self._lock:
            handles = [ProcessHandle(key, self._generation) for key in self._processes]
        for handle in handles:
            try:
                self.terminate(handle)
            except Exception:
                pass
        with self._lock:
            for owned in self._processes.values():
                owned.stdout.close()
                owned.stderr.close()
            self._processes.clear()
            self._generation += 1

    def _owned(self, handle: ProcessHandle) -> _OwnedHostProcess:
        if handle.owner_generation != self._generation:
            raise EnvCapabilityError("stale_generation", "process handle is stale")
        with self._lock:
            owned = self._processes.get(handle.process_id)
        if owned is None:
            raise EnvCapabilityError("process_not_found", "owned process is unavailable")
        return owned

    def _read(self, stream: Any) -> str:
        stream.flush()
        stream.seek(0)
        value = stream.read(self.output_limit + 1)
        stream.seek(0, os.SEEK_END)
        return value[: self.output_limit]


class HostEnv(Env):
    """Host-based env that interprets common file/shell actions directly."""

    name = "host_env"
    version = "1.0"

    def __init__(
        self,
        workspace_root: str = ".",
        fs: Optional[FileSystemCapability] = None,
        cmd: Optional[CommandCapability] = None,
    ):
        self.workspace_root = str(Path(workspace_root).resolve())
        self.fs = fs or HostFSCapability(self.workspace_root)
        self.cmd = cmd or HostCommandCapability(self.workspace_root)
        self.processes: ProcessControlCapability = HostProcessControlCapability(
            self.workspace_root
        )
        self._last_error: Optional[str] = None

    def setup(
        self, task: Any = None, workspace: Optional[str] = None, **kwargs: Any
    ) -> None:
        if workspace:
            self.workspace_root = str(Path(workspace).resolve())
            self.fs = HostFSCapability(self.workspace_root)
            self.cmd = HostCommandCapability(self.workspace_root)
            self.processes.close()
            self.processes = HostProcessControlCapability(self.workspace_root)
        Path(self.workspace_root).mkdir(parents=True, exist_ok=True)

    def reset(
        self, task: Any = None, workspace: Optional[str] = None, **kwargs: Any
    ) -> EnvObservation:
        if workspace:
            self.workspace_root = str(Path(workspace).resolve())
            self.fs = HostFSCapability(self.workspace_root)
            self.cmd = HostCommandCapability(self.workspace_root)
            self.processes.close()
            self.processes = HostProcessControlCapability(self.workspace_root)
        Path(self.workspace_root).mkdir(parents=True, exist_ok=True)
        self._last_error = None
        return self.observe(state=None)

    def health_check(self) -> Dict[str, Any]:
        root = Path(self.workspace_root)
        if not root.exists():
            return {
                "ok": False,
                "message": f"workspace not found: {self.workspace_root}",
            }
        if not os.access(str(root), os.R_OK):
            return {
                "ok": False,
                "message": f"workspace not readable: {self.workspace_root}",
            }
        if not os.access(str(root), os.W_OK):
            return {
                "ok": False,
                "message": f"workspace not writable: {self.workspace_root}",
            }
        return {"ok": True, "workspace_root": self.workspace_root}

    def observe(self, state: Any = None) -> EnvObservation:
        files = self.fs.list_files(limit=200)
        return EnvObservation(
            data={
                "workspace_root": self.workspace_root,
                "file_count": len(files),
                "files": files,
                "last_error": self._last_error,
            },
            metadata={"state_step": getattr(state, "current_step", None)},
        )

    def step(self, action: Any, state: Any = None) -> EnvStepResult:
        # step() captures env transition. action execution is done by execute_action().
        return EnvStepResult(
            observation=self.observe(state=state),
            done=False,
            reward=None,
            info={"action_seen": self._to_action_name(action)},
            error=self._last_error,
        )

    def get_ops(self, group: str) -> Any:
        if group == "file":
            return self.fs
        if group == "process":
            return self.cmd
        if group == "process_control":
            return self.processes
        return None

    def close(self) -> None:
        self.processes.close()

    def supports_action(self, action: Any) -> bool:
        name = self._to_action_name(action)
        return name in {
            "view",
            "read_file",
            "write_file",
            "replace_lines",
            "run_command",
            "list_files",
            "search",
        }

    def execute_action(self, action: Any, state: Any = None) -> Any:
        act = action if isinstance(action, Action) else Action.from_dict(action)
        name = act.name
        args = act.args or {}
        try:
            if name in {"view", "read_file"}:
                path = str(args.get("path") or args.get("filename") or "")
                content = self.fs.read_text(path)
                return {"status": "success", "path": path, "content": content}
            if name == "write_file":
                path = str(args.get("path") or args.get("filename") or "")
                content = str(args.get("content", ""))
                self.fs.write_text(path, content)
                return {"status": "success", "path": path, "size": len(content)}
            if name == "list_files":
                path = str(args.get("path", "."))
                files = self.fs.list_files(path=path, limit=int(args.get("limit", 200)))
                return {
                    "status": "success",
                    "path": path,
                    "files": files,
                    "count": len(files),
                }
            if name == "search":
                path = str(args.get("path") or "")
                query = str(args.get("query") or "")
                return self._search(
                    path=path, query=query, limit=int(args.get("limit", 50))
                )
            if name == "replace_lines":
                return self._replace_lines(
                    path=str(args.get("path", "")),
                    start_line=int(args.get("start_line", 1)),
                    end_line=int(args.get("end_line", 1)),
                    replacement=str(args.get("replacement", "")),
                )
            if name == "run_command":
                return self.cmd.run(
                    str(args.get("command", "")), timeout=int(args.get("timeout", 30))
                )
            return {"status": "error", "error": f"unsupported action: {name}"}
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": "error", "error": str(exc), "action": name}

    def _replace_lines(
        self, path: str, start_line: int, end_line: int, replacement: str
    ) -> Dict[str, Any]:
        text = self.fs.read_text(path)
        lines = text.splitlines()
        if start_line < 1 or end_line < start_line or end_line > len(lines):
            return {"status": "error", "error": "invalid line range", "path": path}
        new_lines = (
            lines[: start_line - 1] + replacement.splitlines() + lines[end_line:]
        )
        self.fs.write_text(
            path, "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
        )
        return {
            "status": "success",
            "path": path,
            "start_line": start_line,
            "end_line": end_line,
        }

    def _search(self, path: str, query: str, limit: int = 50) -> Dict[str, Any]:
        if not query:
            return {"status": "error", "error": "empty query"}
        text = self.fs.read_text(path)
        out: List[Dict[str, Any]] = []
        for idx, line in enumerate(text.splitlines(), start=1):
            if re.search(re.escape(query), line):
                out.append({"line": idx, "text": line})
                if len(out) >= limit:
                    break
        return {
            "status": "success",
            "path": path,
            "query": query,
            "matches": out,
            "count": len(out),
        }

    def _to_action_name(self, action: Any) -> str:
        if isinstance(action, Action):
            return action.name
        if isinstance(action, dict):
            return str(action.get("name", ""))
        return ""


__all__ = ["HostFSCapability", "HostCommandCapability", "HostEnv"]

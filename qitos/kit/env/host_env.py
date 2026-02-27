"""Host environment with filesystem + command capabilities."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from qitos.core.action import Action
from qitos.core.env import CommandCapability, Env, EnvObservation, EnvStepResult, FileSystemCapability


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

    def _resolve(self, path: str) -> Path:
        rel = path.lstrip("/")
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root)):
            raise PermissionError(f"path outside root: {path}")
        return p


class HostCommandCapability(CommandCapability):
    def __init__(self, cwd: str):
        self.cwd = str(Path(cwd).resolve())

    def run(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        if not command or not command.strip():
            return {"status": "error", "error": "empty command"}
        try:
            r = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.cwd,
            )
            return {
                "status": "success" if r.returncode == 0 else "partial",
                "returncode": r.returncode,
                "stdout": r.stdout,
                "stderr": r.stderr,
                "cwd": self.cwd,
                "command": command,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc), "command": command, "cwd": self.cwd}


class HostEnv(Env):
    """Host-based env that interprets common file/shell actions directly."""

    name = "host_env"
    version = "1.0"

    def __init__(self, workspace_root: str = ".", fs: Optional[FileSystemCapability] = None, cmd: Optional[CommandCapability] = None):
        self.workspace_root = str(Path(workspace_root).resolve())
        self.fs = fs or HostFSCapability(self.workspace_root)
        self.cmd = cmd or HostCommandCapability(self.workspace_root)
        self._last_error: Optional[str] = None

    def setup(self, task: Any = None, workspace: Optional[str] = None, **kwargs: Any) -> None:
        if workspace:
            self.workspace_root = str(Path(workspace).resolve())
            self.fs = HostFSCapability(self.workspace_root)
            self.cmd = HostCommandCapability(self.workspace_root)
        Path(self.workspace_root).mkdir(parents=True, exist_ok=True)

    def reset(self, task: Any = None, workspace: Optional[str] = None, **kwargs: Any) -> EnvObservation:
        if workspace:
            self.workspace_root = str(Path(workspace).resolve())
            self.fs = HostFSCapability(self.workspace_root)
            self.cmd = HostCommandCapability(self.workspace_root)
        Path(self.workspace_root).mkdir(parents=True, exist_ok=True)
        self._last_error = None
        return self.observe(state=None)

    def health_check(self) -> Dict[str, Any]:
        root = Path(self.workspace_root)
        if not root.exists():
            return {"ok": False, "message": f"workspace not found: {self.workspace_root}"}
        if not os.access(str(root), os.R_OK):
            return {"ok": False, "message": f"workspace not readable: {self.workspace_root}"}
        if not os.access(str(root), os.W_OK):
            return {"ok": False, "message": f"workspace not writable: {self.workspace_root}"}
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
        return None

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
                return {"status": "success", "path": path, "files": files, "count": len(files)}
            if name == "search":
                path = str(args.get("path") or "")
                query = str(args.get("query") or "")
                return self._search(path=path, query=query, limit=int(args.get("limit", 50)))
            if name == "replace_lines":
                return self._replace_lines(
                    path=str(args.get("path", "")),
                    start_line=int(args.get("start_line", 1)),
                    end_line=int(args.get("end_line", 1)),
                    replacement=str(args.get("replacement", "")),
                )
            if name == "run_command":
                return self.cmd.run(str(args.get("command", "")), timeout=int(args.get("timeout", 30)))
            return {"status": "error", "error": f"unsupported action: {name}"}
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": "error", "error": str(exc), "action": name}

    def _replace_lines(self, path: str, start_line: int, end_line: int, replacement: str) -> Dict[str, Any]:
        text = self.fs.read_text(path)
        lines = text.splitlines()
        if start_line < 1 or end_line < start_line or end_line > len(lines):
            return {"status": "error", "error": "invalid line range", "path": path}
        new_lines = lines[: start_line - 1] + replacement.splitlines() + lines[end_line:]
        self.fs.write_text(path, "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""))
        return {"status": "success", "path": path, "start_line": start_line, "end_line": end_line}

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
        return {"status": "success", "path": path, "query": query, "matches": out, "count": len(out)}

    def _to_action_name(self, action: Any) -> str:
        if isinstance(action, Action):
            return action.name
        if isinstance(action, dict):
            return str(action.get("name", ""))
        return ""


__all__ = ["HostFSCapability", "HostCommandCapability", "HostEnv"]

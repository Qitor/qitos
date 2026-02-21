"""Shell command tool."""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, Optional

from qitos.core.tool import BaseTool, ToolPermission, ToolSpec


class RunCommand(BaseTool):
    def __init__(self, timeout: int = 30, cwd: str = ".", env: Optional[Dict[str, str]] = None):
        self._timeout = timeout
        self._cwd = os.path.abspath(cwd) if cwd else os.getcwd()
        self._env = env
        super().__init__(
            ToolSpec(
                name="run_command",
                description="Execute shell command in working directory",
                parameters={"command": {"type": "string"}},
                required=["command"],
                permissions=ToolPermission(command=True),
                required_ops=["process"],
            )
        )

    def run(self, command: str, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        runtime_context = runtime_context or {}
        ops = runtime_context.get("ops", {})
        process_ops = ops.get("process")
        if process_ops is not None and hasattr(process_ops, "run"):
            return process_ops.run(command=command, timeout=self._timeout)
        if not command or not command.strip():
            return {"status": "error", "message": "Command cannot be empty"}
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=self._cwd,
                env=self._env,
            )
            return {
                "status": "success" if result.returncode == 0 else "partial",
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "cwd": self._cwd,
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "command": command}


__all__ = ["RunCommand"]

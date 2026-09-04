"""Owned Docker exec channel; mutable sandbox files cannot confirm completion."""

import json
import subprocess
import threading
from typing import Any

from ._process_supervisor import SUPERVISOR


class _DockerProcessTask:
    def __init__(self, container: str, workdir: str, base: str, command: str):
        self._lock = threading.Lock()
        self._latest: dict[str, Any] = {}
        self._invalid = False
        self._drained = threading.Event()
        self._process = subprocess.Popen(
            ["docker", "exec", "-w", workdir, container, "python3", "-I", "-c", SUPERVISOR,
             base, command, "0", "64000", "stdio"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        stream = self._process.stdout
        assert stream is not None
        try:
            while line := stream.readline(1024 * 1024 + 1):
                if len(line) > 1024 * 1024 or not line.endswith(b"\n"):
                    self._invalid = True
                    continue
                value = json.loads(line)
                if not isinstance(value, dict) or value.get("completion_source") != "backend_supervisor":
                    self._invalid = True
                    continue
                with self._lock:
                    self._latest = value
        except (OSError, ValueError):
            self._invalid = True
        finally:
            stream.close()
            self._drained.set()

    def poll(self) -> dict[str, Any]:
        exitcode = self._process.poll()
        with self._lock:
            value = dict(self._latest)
        confirmed = (exitcode == 0 and self._drained.is_set() and not self._invalid
                     and value.get("status") == "terminal" and value.get("worker_still_running") is False)
        if confirmed:
            value["completion_confirmation"] = "owned_docker_exec_exit"
            return value
        unknown = exitcode is not None or self._invalid or value.get("status") == "unknown"
        value.update(status="unknown" if unknown else "running", returncode=None,
                     worker_still_running=True, outcome_unknown=unknown)
        value.setdefault("stdout", "")
        value.setdefault("stderr", "")
        return value

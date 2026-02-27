"""Repository environment built on top of HostEnv capabilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from qitos.core.env import EnvObservation, EnvStepResult
from qitos.core.task import Task
from qitos.kit.env.host_env import HostEnv


class RepoEnv(HostEnv):
    """Coding/SWE-focused env with required-resource validation."""

    name = "repo_env"
    version = "1.1"

    def __init__(self, workspace_root: str = ".", max_list_files: int = 200):
        super().__init__(workspace_root=workspace_root)
        self.max_list_files = max_list_files
        self.task: Optional[Task] = None

    def reset(self, task: Any = None, workspace: Optional[str] = None, **kwargs: Any) -> EnvObservation:
        self.task = task if isinstance(task, Task) else None
        obs = super().reset(task=task, workspace=workspace, **kwargs)
        missing = self._missing_required_resources()
        obs.data["required_missing"] = missing
        obs.data["file_count"] = len(self.fs.list_files(limit=self.max_list_files))
        return obs

    def observe(self, state: Any = None) -> EnvObservation:
        obs = super().observe(state=state)
        files = self.fs.list_files(limit=self.max_list_files)
        obs.data["files"] = files
        obs.data["file_count"] = len(files)
        return obs

    def step(self, action: Any, state: Any = None) -> EnvStepResult:
        result = super().step(action=action, state=state)
        # Repo env terminates on explicit final action only.
        decision_mode = None
        if isinstance(action, dict):
            decision_mode = action.get("decision_mode")
        result.done = bool(decision_mode == "final")
        return result

    def _missing_required_resources(self) -> List[str]:
        if self.task is None:
            return []
        out: List[str] = []
        root = Path(self.workspace_root)
        for r in self.task.resources:
            if not r.required:
                continue
            if not r.path:
                continue
            if not (root / r.path).exists():
                out.append(r.path)
        return out


__all__ = ["RepoEnv"]

"""Canonical task schema for QitOS agentic workloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .env import EnvSpec


@dataclass
class TaskResource:
    """One resource entry required by a task."""

    kind: str  # file | dir | url | artifact
    path: Optional[str] = None
    uri: Optional[str] = None
    mount_to: Optional[str] = None
    required: bool = True
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskBudget:
    """Task-level budget contract."""

    max_steps: Optional[int] = None
    max_runtime_seconds: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class Task:
    """Task package with objective, resources, and environment requirements."""

    id: str
    objective: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    resources: List[TaskResource] = field(default_factory=list)
    env_spec: Optional[EnvSpec] = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    success_criteria: List[str] = field(default_factory=list)
    budget: TaskBudget = field(default_factory=TaskBudget)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ValueError("Task.id must be a non-empty string")
        if not self.objective or not isinstance(self.objective, str):
            raise ValueError("Task.objective must be a non-empty string")
        for item in self.resources:
            if item.kind not in {"file", "dir", "url", "artifact"}:
                raise ValueError(f"Unsupported TaskResource.kind: {item.kind}")
            if not item.path and not item.uri:
                raise ValueError("TaskResource requires path or uri")

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.env_spec is not None:
            payload["env_spec"] = asdict(self.env_spec)
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Task":
        resources_raw = payload.get("resources", [])
        resources: List[TaskResource] = []
        if isinstance(resources_raw, list):
            for item in resources_raw:
                if isinstance(item, TaskResource):
                    resources.append(item)
                elif isinstance(item, dict):
                    resources.append(TaskResource(**item))

        budget_raw = payload.get("budget", {})
        if isinstance(budget_raw, TaskBudget):
            budget = budget_raw
        elif isinstance(budget_raw, dict):
            budget = TaskBudget(**budget_raw)
        else:
            budget = TaskBudget()

        env_raw = payload.get("env_spec")
        if isinstance(env_raw, EnvSpec):
            env_spec = env_raw
        elif isinstance(env_raw, dict):
            env_spec = EnvSpec(**env_raw)
        else:
            env_spec = None

        obj = cls(
            id=str(payload.get("id", "")),
            objective=str(payload.get("objective", "")),
            inputs=payload.get("inputs", {}) if isinstance(payload.get("inputs", {}), dict) else {},
            resources=resources,
            env_spec=env_spec,
            constraints=payload.get("constraints", {}) if isinstance(payload.get("constraints", {}), dict) else {},
            success_criteria=[
                str(x) for x in payload.get("success_criteria", []) if isinstance(payload.get("success_criteria", []), list)
            ],
            budget=budget,
            metadata=payload.get("metadata", {}) if isinstance(payload.get("metadata", {}), dict) else {},
        )
        obj.validate()
        return obj


__all__ = ["Task", "TaskResource", "TaskBudget"]

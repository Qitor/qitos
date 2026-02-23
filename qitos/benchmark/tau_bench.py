"""Tau-Bench adapter for converting Tau tasks into canonical QitOS Task objects.

This implementation is self-contained and uses vendored Tau assets in
`qitos.benchmark.tau_port` (no external `tau_bench` package dependency).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional

from qitos.core.env import EnvSpec
from qitos.core.task import Task, TaskBudget

from .base import BenchmarkAdapter, BenchmarkSource


def _action_to_dict(action: Any) -> Dict[str, Any]:
    if hasattr(action, "model_dump"):
        obj = action.model_dump()
        if isinstance(obj, dict):
            return obj
    if isinstance(action, dict):
        out = dict(action)
        if "kwargs" not in out and "arguments" in out:
            out["kwargs"] = dict(out.get("arguments") or {})
        return out
    return {"name": str(getattr(action, "name", "")), "kwargs": dict(getattr(action, "kwargs", {}) or {})}


def _task_to_dict(task: Any) -> Dict[str, Any]:
    if hasattr(task, "model_dump"):
        obj = task.model_dump()
        if isinstance(obj, dict):
            return obj
    if isinstance(task, dict):
        return dict(task)
    return {
        "instruction": str(getattr(task, "instruction", "")),
        "outputs": list(getattr(task, "outputs", []) or []),
        "actions": [_action_to_dict(x) for x in list(getattr(task, "actions", []) or [])],
        "user_id": str(getattr(task, "user_id", "")),
    }


@dataclass
class TauBenchAdapter(BenchmarkAdapter):
    """Convert Tau-Bench task objects/rows into canonical QitOS Task."""

    env_name: str = "retail"  # retail | airline
    task_split: str = "test"  # train | dev | test
    task_prefix: str = "tau"
    include_raw_record: bool = True
    default_max_steps: int = 30
    source: BenchmarkSource = field(init=False)
    default_env_spec: EnvSpec = field(
        default_factory=lambda: EnvSpec(
            type="tau_bench",
            capabilities=["tau.step", "tau.reward", "tau.tool_call"],
            metadata={"benchmark": "tau-bench"},
        )
    )

    def __post_init__(self) -> None:
        self.source = BenchmarkSource(name="tau-bench", split=self.task_split, subset=self.env_name)

    def load_records(self, env_name: Optional[str] = None, split: Optional[str] = None) -> list[dict[str, Any]]:
        env = str(env_name or self.env_name)
        sp = str(split or self.task_split)
        records = self._load_task_constants(env=env, split=sp)
        return [self._normalize_record(r) for r in records]

    def to_tasks(self, records: Iterable[Mapping[str, Any]], split: str, limit: Optional[int] = None) -> list[Task]:
        out: list[Task] = []
        for idx, row in enumerate(records):
            if limit is not None and idx >= int(limit):
                break
            out.append(self.to_task(row, split=split, idx=idx))
        return out

    def to_task(self, record: Mapping[str, Any], split: str, idx: int) -> Task:
        rec = self._normalize_record(record)
        instruction = str(rec.get("instruction", "")).strip() or "Solve the Tau-Bench task."
        task_id = str(rec.get("task_id") or f"{self.task_prefix}_{self.env_name}_{split}_{idx:05d}")
        outputs = list(rec.get("outputs", []) or [])
        actions = list(rec.get("actions", []) or [])

        criteria = ["Complete the task according to Tau-Bench environment reward."]
        if outputs:
            criteria.append("Expected outputs should be covered in agent responses.")

        metadata: Dict[str, Any] = {
            "benchmark": "tau-bench",
            "env": self.env_name,
            "split": split,
            "task_index": idx,
            "reference_outputs": outputs,
            "reference_actions": actions,
        }
        if self.include_raw_record:
            metadata["raw_record"] = dict(rec)

        return Task(
            id=task_id,
            objective=instruction,
            inputs={
                "benchmark": "tau-bench",
                "env": self.env_name,
                "split": split,
                "instruction": instruction,
                "reference_outputs": outputs,
                "reference_actions": actions,
                "user_id": rec.get("user_id"),
            },
            env_spec=self.default_env_spec,
            success_criteria=criteria,
            budget=TaskBudget(max_steps=self.default_max_steps),
            metadata=metadata,
        )

    def _load_task_constants(self, env: str, split: str) -> list[Any]:
        """Load vendored Tau task constants."""
        from importlib import import_module

        if env == "retail":
            if split == "test":
                mod = import_module("qitos.benchmark.tau_port.envs.retail.tasks_test")
                return list(getattr(mod, "TASKS_TEST"))
            if split == "train":
                mod = import_module("qitos.benchmark.tau_port.envs.retail.tasks_train")
                return list(getattr(mod, "TASKS_TRAIN"))
            if split == "dev":
                mod = import_module("qitos.benchmark.tau_port.envs.retail.tasks_dev")
                return list(getattr(mod, "TASKS_DEV"))
            raise ValueError(f"Unsupported retail split: {split}")

        if env == "airline":
            if split == "test":
                mod = import_module("qitos.benchmark.tau_port.envs.airline.tasks_test")
                return list(getattr(mod, "TASKS"))
            raise ValueError(f"Unsupported airline split: {split}")

        raise ValueError(f"Unsupported Tau-Bench env: {env}")

    def _normalize_record(self, row: Mapping[str, Any] | Any) -> Dict[str, Any]:
        rec = _task_to_dict(row)
        actions = [_action_to_dict(a) for a in list(rec.get("actions", []) or [])]
        outputs = list(rec.get("outputs", []) or [])
        return {
            "instruction": str(rec.get("instruction", "")),
            "outputs": [str(x) for x in outputs],
            "actions": actions,
            "user_id": rec.get("user_id"),
            "task_id": rec.get("task_id"),
        }


def load_tau_bench_tasks(env_name: str = "retail", split: str = "test", limit: Optional[int] = None) -> list[Task]:
    adapter = TauBenchAdapter(env_name=env_name, task_split=split)
    rows = adapter.load_records(env_name=env_name, split=split)
    return adapter.to_tasks(rows, split=split, limit=limit)

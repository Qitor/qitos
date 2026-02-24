"""CyBench benchmark adapter (self-contained, no cybench package dependency)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from qitos.core.env import EnvSpec
from qitos.core.task import Task, TaskBudget, TaskResource

from ..base import BenchmarkAdapter, BenchmarkSource


@dataclass
class CyBenchAdapter(BenchmarkAdapter):
    """Load CyBench task metadata and convert them to QitOS Tasks."""

    cybench_root: str = "references/cybench"
    run_with_subtasks: bool = True
    task_prefix: str = "cybench"
    include_raw_record: bool = True
    default_max_steps: int = 20
    source: BenchmarkSource = field(init=False)
    default_env_spec: EnvSpec = field(
        default_factory=lambda: EnvSpec(
            type="docker",
            capabilities=["file", "process", "docker"],
            metadata={"benchmark": "cybench"},
        )
    )

    def __post_init__(self) -> None:
        split = "guided" if self.run_with_subtasks else "unguided"
        self.source = BenchmarkSource(name="cybench", split=split)

    def load_records(
        self,
        cybench_root: Optional[str] = None,
        run_with_subtasks: Optional[bool] = None,
        task_list_file: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        root = Path(cybench_root or self.cybench_root).expanduser().resolve()
        guided = self.run_with_subtasks if run_with_subtasks is None else bool(run_with_subtasks)

        rel_paths = self._load_task_paths(root=root, run_with_subtasks=guided, task_list_file=task_list_file)
        out: list[dict[str, Any]] = []
        for idx, rel in enumerate(rel_paths):
            if limit is not None and idx >= int(limit):
                break
            task_dir = (root / rel).resolve()
            metadata_path = task_dir / "metadata" / "metadata.json"
            if not metadata_path.exists():
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            out.append(
                {
                    "task_relative_path": rel,
                    "task_dir": str(task_dir),
                    "metadata_path": str(metadata_path),
                    "metadata": metadata,
                    "run_with_subtasks": guided,
                }
            )
        return out

    def to_tasks(self, records: Iterable[Mapping[str, Any]], split: str, limit: Optional[int] = None) -> list[Task]:
        tasks: list[Task] = []
        for idx, row in enumerate(records):
            if limit is not None and idx >= int(limit):
                break
            tasks.append(self.to_task(row, split=split, idx=idx))
        return tasks

    def to_task(self, record: Mapping[str, Any], split: str, idx: int) -> Task:
        rec = dict(record)
        meta = dict(rec.get("metadata") or {})
        subtasks = list(meta.get("subtasks") or [])

        rel_path = str(rec.get("task_relative_path") or "")
        task_dir = str(rec.get("task_dir") or "")
        guided = bool(rec.get("run_with_subtasks", self.run_with_subtasks))

        task_id = rec.get("task_id")
        if not task_id:
            short = rel_path.replace("/", "_").replace(" ", "_")
            if not short:
                short = hashlib.sha1(task_dir.encode("utf-8")).hexdigest()[:10]
            task_id = f"{self.task_prefix}_{short}"

        if guided:
            objective = str(meta.get("hard_prompt") or "Solve each subtask and submit answers.")
        else:
            objective = str(meta.get("hard_prompt") or "Capture the flag and submit the final answer.")

        inputs: Dict[str, Any] = {
            "benchmark": "cybench",
            "split": split,
            "task_relative_path": rel_path,
            "task_dir": task_dir,
            "categories": list(meta.get("categories") or []),
            "difficulty": meta.get("difficulty"),
            "target_host": str(meta.get("target_host") or ""),
            "hard_prompt": str(meta.get("hard_prompt") or ""),
            "easy_prompt": str(meta.get("easy_prompt") or ""),
            "subtasks": subtasks,
            "run_with_subtasks": guided,
        }

        criteria: list[str] = ["Follow CyBench task objective and submit a valid answer."]
        if guided:
            criteria.append("Guided score: average solved subtasks.")
            criteria.append("Guided-final score: last subtask solved.")
        else:
            criteria.append("Unguided score: final task solved.")

        resources = [
            TaskResource(
                kind="dir",
                path=task_dir,
                required=True,
                description="CyBench task directory",
            )
        ]

        metadata: Dict[str, Any] = {
            "benchmark": "cybench",
            "split": split,
            "task_relative_path": rel_path,
            "task_dir": task_dir,
            "guided": guided,
            "target_host": str(meta.get("target_host") or ""),
        }
        if self.include_raw_record:
            metadata["raw_record"] = rec

        return Task(
            id=str(task_id),
            objective=objective,
            inputs=inputs,
            resources=resources,
            env_spec=self.default_env_spec,
            success_criteria=criteria,
            budget=TaskBudget(max_steps=self.default_max_steps),
            metadata=metadata,
        )

    def _load_task_paths(self, root: Path, run_with_subtasks: bool, task_list_file: Optional[str]) -> list[str]:
        file_name = task_list_file or ("subtask_list.txt" if run_with_subtasks else "task_list.txt")
        list_path = root / file_name
        if not list_path.exists():
            raise FileNotFoundError(f"CyBench list file not found: {list_path}")

        out: list[str] = []
        for line in list_path.read_text(encoding="utf-8").splitlines():
            rel = line.strip()
            if not rel or rel.startswith("#"):
                continue
            out.append(rel)
        return out


def load_cybench_tasks(
    cybench_root: str = "references/cybench",
    run_with_subtasks: bool = True,
    limit: Optional[int] = None,
) -> list[Task]:
    adapter = CyBenchAdapter(cybench_root=cybench_root, run_with_subtasks=run_with_subtasks)
    rows = adapter.load_records(limit=limit)
    split = "guided" if run_with_subtasks else "unguided"
    return adapter.to_tasks(rows, split=split, limit=limit)

"""GAIA benchmark adapter.

Ported with design cues from:
references/smolagents/examples/open_deep_research/run_gaia.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from qitos.core.env import EnvSpec
from qitos.core.task import Task, TaskBudget, TaskResource

from .base import BenchmarkAdapter, BenchmarkSource


def _first_non_empty(record: Mapping[str, Any], keys: list[str]) -> Optional[Any]:
    for key in keys:
        if key not in record:
            continue
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _normalize_files(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    return []


@dataclass
class GaiaAdapter(BenchmarkAdapter):
    """Convert GAIA dataset rows to canonical QitOS Task objects."""

    dataset_name: str = "gaia-benchmark/GAIA"
    annotated_dataset_name: str = "smolagents/GAIA-annotated"
    local_dir: str = "data/gaia"
    config_name: str = "2023_all"
    default_subset: Optional[str] = None
    task_prefix: str = "gaia"
    include_raw_record: bool = True
    default_max_steps: int = 24
    default_env_spec: EnvSpec = field(
        default_factory=lambda: EnvSpec(
            type="host",
            capabilities=["fs.read_text", "fs.write_text", "cmd.run", "network.http"],
            metadata={"benchmark": "gaia"},
        )
    )

    source: BenchmarkSource = field(init=False)

    def __post_init__(self) -> None:
        self.source = BenchmarkSource(name="GAIA", split="validation", subset=self.default_subset)

    def load_huggingface_records(
        self,
        split: str = "validation",
        subset: Optional[str] = None,
        cache_dir: Optional[str] = None,
        use_annotated_dataset: bool = False,
    ) -> list[dict[str, Any]]:
        """Load GAIA rows from Hugging Face datasets."""
        try:
            from datasets import load_dataset  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency gate
            raise RuntimeError("Missing optional dependency: datasets. Install with `pip install datasets`.") from exc

        ds_kwargs: dict[str, Any] = {"split": split}
        if cache_dir:
            ds_kwargs["cache_dir"] = cache_dir
        selected_subset = subset if subset is not None else self.default_subset
        repo_name = self.annotated_dataset_name if use_annotated_dataset else self.dataset_name

        if selected_subset:
            dataset = load_dataset(repo_name, selected_subset, **ds_kwargs)
        else:
            dataset = load_dataset(repo_name, **ds_kwargs)
        return [dict(row) for row in dataset]

    def snapshot_dataset(
        self,
        use_raw_dataset: bool = True,
        local_dir: Optional[str] = None,
        hf_token: Optional[str] = None,
    ) -> str:
        """Download GAIA dataset snapshot to local dir and return its path."""
        target_dir = str(Path(local_dir or self.local_dir).expanduser())
        path = Path(target_dir)
        if path.exists() and any(path.iterdir()):
            return target_dir
        try:
            from huggingface_hub import snapshot_download  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency gate
            raise RuntimeError(
                "Missing optional dependency: huggingface_hub. Install with `pip install huggingface_hub`."
            ) from exc

        repo_id = self.dataset_name if use_raw_dataset else self.annotated_dataset_name
        kwargs: dict[str, Any] = {
            "repo_id": repo_id,
            "repo_type": "dataset",
            "local_dir": target_dir,
            "ignore_patterns": [".gitattributes", "README.md"],
        }
        if hf_token:
            kwargs["token"] = hf_token
        snapshot_download(**kwargs)
        return target_dir

    def load_local_records(
        self,
        split: str = "validation",
        local_dir: Optional[str] = None,
        config_name: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Load GAIA rows from local snapshot directory when available."""
        try:
            from datasets import load_dataset  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency gate
            raise RuntimeError("Missing optional dependency: datasets. Install with `pip install datasets`.") from exc

        ds_root = Path(local_dir or self.local_dir).expanduser()
        script_path = ds_root / "GAIA.py"
        cfg = config_name or self.config_name
        if script_path.exists():
            dataset = load_dataset(str(script_path), name=cfg, split=split)
        else:
            dataset = load_dataset(self.dataset_name, cfg, split=split)
        rows: list[dict[str, Any]] = []
        for row in dataset:
            rec = dict(row)
            normalized = self._normalize_record(rec, split=split, local_dir=str(ds_root))
            rows.append(normalized)
        return rows

    def to_tasks(self, records: Iterable[Mapping[str, Any]], split: str, limit: Optional[int] = None) -> list[Task]:
        tasks: list[Task] = []
        for idx, row in enumerate(records):
            if limit is not None and idx >= int(limit):
                break
            tasks.append(self.to_task(row, split=split, idx=idx))
        return tasks

    def to_task(self, record: Mapping[str, Any], split: str, idx: int) -> Task:
        normalized = self._normalize_record(dict(record), split=split, local_dir=self.local_dir)
        question = _first_non_empty(
            record,
            ["question", "Question", "problem", "prompt", "task", "query", "instruction"],
        )
        if question is None:
            question = normalized.get("question")
        objective = str(question or "").strip()
        if not objective:
            objective = "Solve this GAIA benchmark task and provide the final answer."

        raw_id = _first_non_empty(normalized, ["task_id", "id", "sample_id", "qid"])
        task_id = str(raw_id).strip() if raw_id is not None else ""
        if not task_id:
            task_id = f"{self.task_prefix}_{split}_{idx:05d}"

        ref_answer = _first_non_empty(
            normalized, ["true_answer", "final_answer", "Final answer", "answer", "gold_answer", "label"]
        )
        level = _first_non_empty(normalized, ["task", "level", "Level", "difficulty"])
        files = _normalize_files(
            _first_non_empty(normalized, ["file_name", "file", "files", "attachments", "attachment"])
        )

        resources = [
            TaskResource(
                kind="file",
                path=item,
                required=False,
                description="Optional GAIA attachment file",
            )
            for item in files
        ]

        criteria = ["Provide a concise final answer."]
        if ref_answer is not None:
            criteria.append(f"Reference answer (for evaluation): {ref_answer}")

        inputs: dict[str, Any] = {
            "benchmark": "GAIA",
            "split": split,
            "question": objective,
            "reference_answer": ref_answer,
            "level": level,
            "attachments": files,
        }

        metadata: dict[str, Any] = {
            "benchmark": "GAIA",
            "split": split,
            "dataset_name": self.dataset_name,
            "level": level,
            "source_id": raw_id,
        }
        if self.include_raw_record:
            metadata["raw_record"] = dict(normalized)

        return Task(
            id=task_id,
            objective=objective,
            inputs=inputs,
            resources=resources,
            env_spec=self.default_env_spec,
            success_criteria=criteria,
            budget=TaskBudget(max_steps=self.default_max_steps),
            metadata=metadata,
        )

    def _normalize_record(self, record: dict[str, Any], split: str, local_dir: Optional[str]) -> dict[str, Any]:
        """Normalize mixed GAIA schemas to one stable shape."""
        rec = dict(record)
        if "Question" in rec and "question" not in rec:
            rec["question"] = rec.get("Question")
        if "Final answer" in rec and "true_answer" not in rec:
            rec["true_answer"] = rec.get("Final answer")
        if "Level" in rec and "task" not in rec:
            rec["task"] = rec.get("Level")
        file_name = rec.get("file_name")
        if isinstance(file_name, str) and file_name.strip():
            value = file_name.strip()
            if local_dir:
                p = Path(value)
                if not p.is_absolute():
                    rec["file_name"] = str(Path(local_dir) / split / value)
        return rec


def load_gaia_tasks(
    split: str = "validation",
    subset: Optional[str] = None,
    limit: Optional[int] = None,
    cache_dir: Optional[str] = None,
) -> list[Task]:
    """Convenience loader: Hugging Face GAIA -> list[Task]."""
    adapter = GaiaAdapter(default_subset=subset)
    rows = adapter.load_huggingface_records(split=split, subset=subset, cache_dir=cache_dir)
    return adapter.to_tasks(rows, split=split, limit=limit)

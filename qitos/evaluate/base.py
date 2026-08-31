"""Evaluation contracts for trajectory/task success judgement."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, runtime_checkable

from qitos.core.task import Task


EVALUATION_SCHEMA_VERSION = "qitos.evaluation/1"


@runtime_checkable
class DeclarativeRunView(Protocol):
    """Structural evaluator input; evaluators never depend on a store."""

    schema_version: str
    records: Any
    provenance: Dict[str, Any]
    loss: Any


@dataclass
class EvaluationContext:
    task: Task
    run: Any = None
    run_dir: Optional[str] = None
    manifest: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)
    view: Optional[DeclarativeRunView] = None


@dataclass
class EvaluationResult:
    name: str
    success: bool
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = EVALUATION_SCHEMA_VERSION
    provenance: Dict[str, Any] = field(default_factory=dict)
    loss: Dict[str, Any] = field(
        default_factory=lambda: {
            "policy_id": "qitos.loss/none",
            "is_lossless": True,
            "entries": [],
        }
    )


class TrajectoryEvaluator(ABC):
    name: str = "evaluator"

    @abstractmethod
    def evaluate(self, context: EvaluationContext) -> EvaluationResult:
        raise NotImplementedError


@dataclass
class SuiteEvaluationResult:
    success: bool
    score: float
    results: List[EvaluationResult]
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = EVALUATION_SCHEMA_VERSION
    provenance: Dict[str, Any] = field(default_factory=dict)
    loss: Dict[str, Any] = field(
        default_factory=lambda: {
            "policy_id": "qitos.loss/none",
            "is_lossless": True,
            "entries": [],
        }
    )


class EvaluationSuite:
    """Compose multiple evaluators into one judgement."""

    def __init__(
        self,
        evaluators: Optional[Iterable[TrajectoryEvaluator]] = None,
        mode: str = "all",
    ):
        self.evaluators = list(evaluators or [])
        self.mode = mode  # all | any | mean_score

    def evaluate(self, context: EvaluationContext) -> SuiteEvaluationResult:
        results = [e.evaluate(context) for e in self.evaluators]
        if not results:
            return SuiteEvaluationResult(
                success=False,
                score=0.0,
                results=[],
                metadata={"reason": "no_evaluators"},
            )

        success_flags = [r.success for r in results]
        scores = [float(r.score) for r in results]
        mean_score = sum(scores) / float(len(scores))

        if self.mode == "any":
            success = any(success_flags)
        elif self.mode == "mean_score":
            success = mean_score >= 1.0
        else:
            success = all(success_flags)

        return SuiteEvaluationResult(
            success=success,
            score=mean_score,
            results=results,
            metadata={"mode": self.mode, "count": len(results)},
            provenance={
                "evaluators": [result.name for result in results],
                "input_schema": (
                    context.view.schema_version if context.view is not None else None
                ),
            },
            loss=_merge_evaluation_loss(results),
        )


class EvaluatorRegistry:
    """Explicit third-party evaluator registry with no global state."""

    def __init__(
        self, evaluators: Optional[Iterable[TrajectoryEvaluator]] = None
    ) -> None:
        self._evaluators: Dict[str, TrajectoryEvaluator] = {}
        for evaluator in evaluators or ():
            self.register(evaluator)

    def register(self, evaluator: TrajectoryEvaluator) -> "EvaluatorRegistry":
        name = str(getattr(evaluator, "name", "")).strip()
        if not name:
            raise ValueError("evaluator name must not be empty")
        if name in self._evaluators:
            raise ValueError(f"evaluator already registered: {name}")
        self._evaluators[name] = evaluator
        return self

    def get(self, name: str) -> TrajectoryEvaluator:
        try:
            return self._evaluators[name]
        except KeyError as exc:
            raise KeyError(f"unknown evaluator: {name}") from exc

    def evaluate(
        self, name: str, context: EvaluationContext
    ) -> EvaluationResult:
        result = self.get(name).evaluate(context)
        if result.schema_version != EVALUATION_SCHEMA_VERSION:
            raise ValueError("unsupported evaluation result schema")
        return result

    @property
    def names(self) -> List[str]:
        return sorted(self._evaluators)


def _merge_evaluation_loss(results: Iterable[EvaluationResult]) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    policies: List[str] = []
    for result in results:
        loss = result.loss if isinstance(result.loss, dict) else {}
        policies.append(str(loss.get("policy_id", "qitos.loss/unknown")))
        raw_entries = loss.get("entries")
        if isinstance(raw_entries, list):
            entries.extend(item for item in raw_entries if isinstance(item, dict))
    return {
        "policy_id": "+".join(dict.fromkeys(policies)) or "qitos.loss/none",
        "is_lossless": not entries,
        "entries": entries,
    }


def context_from_reader(
    reader: Any,
    *,
    task: Task,
    run_id: str,
    extras: Optional[Dict[str, Any]] = None,
) -> EvaluationContext:
    """Build an evaluator context from any structural trajectory reader."""
    view = reader.read_run(run_id)
    return EvaluationContext(
        task=task,
        view=view,
        extras=dict(extras or {}),
    )


def load_run_artifacts(run_dir: str | Path) -> Dict[str, Any]:
    """Load manifest/events/steps from a run directory with tolerant parsing."""
    run_path = Path(run_dir)
    out: Dict[str, Any] = {"manifest": {}, "events": [], "steps": []}

    manifest_path = run_path / "manifest.json"
    if manifest_path.exists():
        out["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))

    for key, filename in (("events", "events.jsonl"), ("steps", "steps.jsonl")):
        p = run_path / filename
        if not p.exists():
            continue
        rows: List[Dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                continue
        out[key] = rows

    return out

"""Evaluation contracts for trajectory/task success judgement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from qitos.core.task import Task


@dataclass
class EvaluationContext:
    task: Task
    run: Any = None
    run_dir: Optional[str] = None
    manifest: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    name: str
    success: bool
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


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


class EvaluationSuite:
    """Compose multiple evaluators into one judgement."""

    def __init__(self, evaluators: Optional[Iterable[TrajectoryEvaluator]] = None, mode: str = "all"):
        self.evaluators = list(evaluators or [])
        self.mode = mode  # all | any | mean_score

    def evaluate(self, context: EvaluationContext) -> SuiteEvaluationResult:
        results = [e.evaluate(context) for e in self.evaluators]
        if not results:
            return SuiteEvaluationResult(success=False, score=0.0, results=[], metadata={"reason": "no_evaluators"})

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
        )


def load_run_artifacts(run_dir: str | Path) -> Dict[str, Any]:
    """Load manifest/events/steps from a run directory with tolerant parsing."""
    run_path = Path(run_dir)
    out: Dict[str, Any] = {"manifest": {}, "events": [], "steps": []}

    manifest_path = run_path / "manifest.json"
    if manifest_path.exists():
        import json

        out["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))

    for key, filename in (("events", "events.jsonl"), ("steps", "steps.jsonl")):
        p = run_path / filename
        if not p.exists():
            continue
        import json

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

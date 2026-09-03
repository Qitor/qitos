"""Evaluation contracts for trajectory/task success judgement."""

from __future__ import annotations

import copy
import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple, runtime_checkable

from qitos.core.task import Task


EVALUATION_SCHEMA_VERSION = "qitos.evaluation/1"
EVALUATOR_VIEW_SCHEMA_VERSION = "qitos.evaluator-view/1"


@runtime_checkable
class DeclarativeRunView(Protocol):
    """Structural evaluator input; evaluators never depend on a store."""

    @property
    def schema_version(self) -> str:
        ...

    @property
    def records(self) -> Any:
        ...

    @property
    def provenance(self) -> Dict[str, Any]:
        ...

    @property
    def loss(self) -> Any:
        ...


@dataclass(frozen=True)
class EvaluationSelection:
    """Exactly one explicit run, Session, or work-item selection."""

    run_id: Optional[str] = None
    session_id: Optional[str] = None
    work_item_id: Optional[str] = None

    def __post_init__(self) -> None:
        values = (self.run_id, self.session_id, self.work_item_id)
        if sum(value is not None and bool(str(value).strip()) for value in values) != 1:
            raise ValueError("exactly one evaluation selection is required")

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "work_item_id": self.work_item_id,
        }


@dataclass(frozen=True)
class EvaluationLossView:
    """Store-independent fidelity envelope passed to evaluators."""

    policy_id: str
    entries: Tuple[Dict[str, Any], ...] = ()

    @property
    def is_lossless(self) -> bool:
        return not self.entries

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "is_lossless": self.is_lossless,
            "entries": copy.deepcopy(list(self.entries)),
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "EvaluationLossView":
        raw_entries = value.get("entries")
        entries = (
            tuple(copy.deepcopy(item) for item in raw_entries if isinstance(item, dict))
            if isinstance(raw_entries, list)
            else ()
        )
        return cls(
            policy_id=str(value.get("policy_id", "qitos.loss/unknown")),
            entries=entries,
        )


@dataclass(frozen=True)
class EvaluationView:
    """Stable, store-independent evaluator input."""

    records: Tuple[Any, ...]
    selection: EvaluationSelection
    source_schema: str
    provenance: Dict[str, Any]
    loss: EvaluationLossView
    schema_version: str = EVALUATOR_VIEW_SCHEMA_VERSION


@dataclass(frozen=True)
class _ReaderQuery:
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    work_item_id: Optional[str] = None
    kinds: Tuple[Any, ...] = ()
    after_sequence: Optional[int] = None
    limit: Optional[int] = None


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
        if result.name != name:
            raise ValueError("evaluation result name mismatch")
        if not isinstance(result.success, bool):
            raise ValueError("evaluation success must be boolean")
        if not math.isfinite(float(result.score)):
            raise ValueError("evaluation score must be finite")
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
    view = evaluation_view_from_reader(
        reader,
        selection=EvaluationSelection(run_id=run_id),
    )
    return EvaluationContext(
        task=task,
        view=view,
        extras=dict(extras or {}),
    )


def evaluation_view_from_reader(
    reader: Any,
    *,
    selection: EvaluationSelection,
    view: Any = None,
    limit: int = 10_000,
) -> EvaluationView:
    """Read one bounded selection without coupling evaluators to a store."""
    if limit <= 0:
        raise ValueError("evaluation view limit must be positive")
    if selection.run_id is not None:
        source = (
            reader.read_run(selection.run_id)
            if view is None
            else reader.read_run(selection.run_id, view=view)
        )
        records = tuple(source.records[:limit])
        source_schema = str(source.schema_version)
        provenance = copy.deepcopy(dict(source.provenance))
        loss_value = source.loss.to_dict()
    elif selection.session_id is not None:
        if not bool(getattr(reader.capabilities, "session_query", False)):
            raise LookupError("session_query_unavailable")
        source = (
            reader.read_session(selection.session_id)
            if view is None
            else reader.read_session(selection.session_id, view=view)
        )
        records = tuple(source.records[:limit])
        source_schema = str(source.schema_version)
        provenance = copy.deepcopy(dict(source.provenance))
        loss_value = source.loss.to_dict()
    else:
        query = _ReaderQuery(work_item_id=selection.work_item_id, limit=limit)
        records = tuple(
            reader.replay(query) if view is None else reader.replay(query, view=view)
        )
        source_schema = str(
            getattr(reader.capabilities, "source_kind", "unknown_source")
        )
        provenance = {
            "reader_id": str(getattr(reader.capabilities, "reader_id", "unknown")),
            "source_kind": source_schema,
        }
        loss_value = {
            "policy_id": "qitos.loss/unknown",
            "is_lossless": False,
            "entries": [
                {
                    "code": "selection_level_loss_unknown",
                    "scope": "work_item",
                    "count": 1,
                    "consequence": "reader_did_not_return_trajectory_envelope",
                }
            ],
        }
    provenance["selection"] = selection.to_dict()
    provenance["source_schema"] = source_schema
    return EvaluationView(
        records=tuple(copy.deepcopy(records)),
        selection=selection,
        source_schema=source_schema,
        provenance=provenance,
        loss=EvaluationLossView.from_dict(copy.deepcopy(dict(loss_value))),
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

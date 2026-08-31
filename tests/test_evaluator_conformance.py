from __future__ import annotations

from typing import Iterable

from qitos.core.task import Task
from qitos.evaluate import (
    EVALUATION_SCHEMA_VERSION,
    EvaluationContext,
    EvaluationResult,
    EvaluationSuite,
    EvaluatorRegistry,
    TrajectoryEvaluator,
)
from qitos.metric import Metric, MetricInput, MetricReport, MetricRegistry
from qitos.tracing.trajectory import RecordKind, Trajectory, TrajectoryRecord


def _view() -> Trajectory:
    record = TrajectoryRecord.create(
        RecordKind.STOP,
        record_id="stop-1",
        run_id="run-1",
        payload={"reason": "final"},
    ).with_sequence(0)
    return Trajectory(
        records=(record,),
        provenance={"reader_id": "third_party.reader"},
    )


class ThirdPartyEvaluator(TrajectoryEvaluator):
    """Custom evaluator using only the declared run-view boundary."""

    name = "third_party.stop_present"

    def evaluate(self, context: EvaluationContext) -> EvaluationResult:
        assert context.view is not None
        stop_present = any(
            record.kind == RecordKind.STOP for record in context.view.records
        )
        return EvaluationResult(
            name=self.name,
            success=stop_present,
            score=1.0 if stop_present else 0.0,
            provenance={
                "input_schema": context.view.schema_version,
                "reader": context.view.provenance.get("reader_id"),
            },
            loss=context.view.loss.to_dict(),
        )


def test_custom_evaluator_registry_conformance() -> None:
    evaluator = ThirdPartyEvaluator()
    registry = EvaluatorRegistry().register(evaluator)
    context = EvaluationContext(
        task=Task(id="task-1", objective="inspect trajectory"),
        view=_view(),
    )
    result = registry.evaluate(evaluator.name, context)

    assert registry.names == [evaluator.name]
    assert result.success
    assert result.schema_version == EVALUATION_SCHEMA_VERSION
    assert result.provenance["reader"] == "third_party.reader"
    assert result.loss["is_lossless"] is True


def test_evaluation_suite_preserves_provenance_and_loss() -> None:
    context = EvaluationContext(
        task=Task(id="task-1", objective="inspect trajectory"),
        view=_view(),
    )
    result = EvaluationSuite([ThirdPartyEvaluator()]).evaluate(context)
    assert result.success
    assert result.schema_version == EVALUATION_SCHEMA_VERSION
    assert result.provenance["input_schema"] == context.view.schema_version
    assert result.loss["is_lossless"] is True


class CountRows(Metric):
    name = "count_rows"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        cached = list(rows)
        return MetricReport(
            name=self.name,
            value=len(cached),
            provenance={"input_schemas": sorted({row.schema_version for row in cached})},
            loss={
                "policy_id": "qitos.loss/none",
                "is_lossless": True,
                "entries": [],
            },
        )


def test_metric_contract_stays_store_independent() -> None:
    rows = [
        MetricInput(
            task_id="task-1",
            success=True,
            provenance={"trajectory_digest": "a" * 64},
        )
    ]
    report = MetricRegistry([CountRows()]).compute_all(rows)[0]
    assert report.value == 1
    assert report.provenance["input_schemas"] == ["qitos.metric-input/1"]
    assert report.loss["is_lossless"] is True

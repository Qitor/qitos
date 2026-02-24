"""CyBench built-in scoring evaluators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from qitos.evaluate import EvaluationContext, EvaluationResult, TrajectoryEvaluator
from qitos.benchmark.cybench.runtime import score_cybench_submission


@dataclass
class CyBenchEvaluator(TrajectoryEvaluator):
    """Evaluate one run using CyBench guided/unguided semantics."""

    name: str = "cybench"
    run_with_subtasks: bool = True

    def evaluate(self, context: EvaluationContext) -> EvaluationResult:
        extras = dict(context.extras or {})
        predictions = list(extras.get("predictions") or [])
        references = list(extras.get("references") or [])
        run_with_subtasks = bool(extras.get("run_with_subtasks", self.run_with_subtasks))

        score = score_cybench_submission(
            predictions=[str(x) for x in predictions],
            references=[str(x) for x in references],
            run_with_subtasks=run_with_subtasks,
        )

        if run_with_subtasks:
            success = float(score.get("guided_final_score", 0.0)) >= 1.0
            overall_score = float(score.get("guided_subtask_score", 0.0))
            reasons: List[str] = []
            if not success:
                reasons.append("final_subtask_not_solved")
        else:
            success = bool(score.get("unguided_success", False))
            overall_score = 1.0 if success else 0.0
            reasons = [] if success else ["unguided_answer_mismatch"]

        return EvaluationResult(
            name=self.name,
            success=success,
            score=overall_score,
            reasons=reasons,
            evidence=score,
            metadata={"run_with_subtasks": run_with_subtasks},
        )


__all__ = ["CyBenchEvaluator"]

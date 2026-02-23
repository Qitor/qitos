"""Basic predefined metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import comb
from typing import Dict, Iterable, List

from qitos.metric import Metric, MetricInput, MetricReport


@dataclass
class SuccessRateMetric(Metric):
    name: str = "success_rate"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        data = list(rows)
        total = len(data)
        success = sum(1 for r in data if bool(r.success))
        value = (float(success) / float(total)) if total else 0.0
        return MetricReport(name=self.name, value=value, details={"success": success, "total": total})


@dataclass
class AverageRewardMetric(Metric):
    name: str = "avg_reward"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        vals = [float(r.reward) for r in rows if r.reward is not None]
        value = (sum(vals) / float(len(vals))) if vals else 0.0
        return MetricReport(name=self.name, value=value, details={"count": len(vals)})


@dataclass
class MeanStepsMetric(Metric):
    name: str = "mean_steps"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        vals = [int(r.steps) for r in rows if r.steps is not None]
        value = (sum(vals) / float(len(vals))) if vals else 0.0
        return MetricReport(name=self.name, value=value, details={"count": len(vals)})


@dataclass
class StopReasonDistributionMetric(Metric):
    name: str = "stop_reason_distribution"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        counter = Counter(str(r.stop_reason or "") for r in rows)
        return MetricReport(name=self.name, value=dict(counter), details={"count": sum(counter.values())})


@dataclass
class PassAtKMetric(Metric):
    """Tau-style pass^k over multiple trials per task_id."""

    k: int = 1
    name: str = "pass_at_k"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        grouped: Dict[str, List[MetricInput]] = defaultdict(list)
        for row in rows:
            grouped[str(row.task_id)].append(row)

        task_scores: List[float] = []
        for items in grouped.values():
            n = len(items)
            if n == 0 or self.k <= 0 or self.k > n:
                continue
            c = sum(1 for r in items if bool(r.success))
            if c < self.k:
                task_scores.append(0.0)
                continue
            # identical to tau-bench pass^k form for repeated trials
            score = comb(c, self.k) / float(comb(n, self.k))
            task_scores.append(float(score))

        value = (sum(task_scores) / float(len(task_scores))) if task_scores else 0.0
        return MetricReport(name=f"{self.name}_{self.k}", value=value, details={"task_count": len(task_scores)})


@dataclass
class CustomFieldMetric(Metric):
    field: str = ""
    name: str = "custom_field_mean"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        vals = []
        for row in rows:
            value = row.payload.get(self.field)
            if isinstance(value, (int, float)):
                vals.append(float(value))
        mean = (sum(vals) / float(len(vals))) if vals else 0.0
        return MetricReport(name=f"{self.name}:{self.field}", value=mean, details={"count": len(vals)})

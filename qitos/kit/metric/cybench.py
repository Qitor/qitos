"""CyBench-oriented benchmark metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

from qitos.metric import Metric, MetricInput, MetricReport


def _as_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


@dataclass
class CyBenchUnguidedSuccessMetric(Metric):
    name: str = "cybench_unguided_success_rate"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        data = list(rows)
        if not data:
            return MetricReport(name=self.name, value=0.0, details={"count": 0})
        flags = []
        for r in data:
            payload = dict(r.payload or {})
            flags.append(bool(payload.get("unguided_success", r.success or False)))
        value = float(sum(1 for x in flags if x)) / float(len(flags))
        return MetricReport(name=self.name, value=value, details={"count": len(flags)})


@dataclass
class CyBenchGuidedSubtaskScoreMetric(Metric):
    name: str = "cybench_guided_subtask_score"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        vals = []
        for r in rows:
            payload = dict(r.payload or {})
            vals.append(_as_float(payload.get("guided_subtask_score", 0.0)))
        value = (sum(vals) / float(len(vals))) if vals else 0.0
        return MetricReport(name=self.name, value=value, details={"count": len(vals)})


@dataclass
class CyBenchGuidedFinalScoreMetric(Metric):
    name: str = "cybench_guided_final_score"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        vals = []
        for r in rows:
            payload = dict(r.payload or {})
            vals.append(_as_float(payload.get("guided_final_score", 0.0)))
        value = (sum(vals) / float(len(vals))) if vals else 0.0
        return MetricReport(name=self.name, value=value, details={"count": len(vals)})


@dataclass
class CyBenchPartialMatchRateMetric(Metric):
    name: str = "cybench_partial_match_rate"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        matched = 0
        total = 0
        for r in rows:
            payload: Dict[str, object] = dict(r.payload or {})
            bits = payload.get("partial_matches")
            if not isinstance(bits, list):
                continue
            total += len(bits)
            matched += sum(1 for b in bits if bool(b))
        value = (float(matched) / float(total)) if total else 0.0
        return MetricReport(name=self.name, value=value, details={"matched": matched, "total": total})


__all__ = [
    "CyBenchUnguidedSuccessMetric",
    "CyBenchGuidedSubtaskScoreMetric",
    "CyBenchGuidedFinalScoreMetric",
    "CyBenchPartialMatchRateMetric",
]

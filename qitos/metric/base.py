"""Metric contracts for benchmark-level aggregation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class MetricInput:
    task_id: str
    trial: int = 0
    success: Optional[bool] = None
    reward: Optional[float] = None
    steps: Optional[int] = None
    latency_seconds: Optional[float] = None
    stop_reason: Optional[str] = None
    cost: Optional[float] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "qitos.metric-input/1"
    provenance: Dict[str, Any] = field(default_factory=dict)
    loss: Dict[str, Any] = field(
        default_factory=lambda: {
            "policy_id": "qitos.loss/none",
            "is_lossless": True,
            "entries": [],
        }
    )


@dataclass
class MetricReport:
    name: str
    value: Any
    details: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "qitos.metric-report/1"
    provenance: Dict[str, Any] = field(default_factory=dict)
    loss: Dict[str, Any] = field(
        default_factory=lambda: {
            "policy_id": "qitos.loss/none",
            "is_lossless": True,
            "entries": [],
        }
    )


class Metric(ABC):
    name: str = "metric"

    @abstractmethod
    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        raise NotImplementedError


class MetricRegistry:
    def __init__(self, metrics: Optional[Iterable[Metric]] = None):
        self.metrics: List[Metric] = []
        for metric in metrics or ():
            self.register(metric)

    def register(self, metric: Metric) -> "MetricRegistry":
        name = str(getattr(metric, "name", "")).strip()
        if not name:
            raise ValueError("metric name must not be empty")
        if any(existing.name == name for existing in self.metrics):
            raise ValueError(f"metric already registered: {name}")
        self.metrics.append(metric)
        return self

    def compute_all(self, rows: Iterable[MetricInput]) -> List[MetricReport]:
        cached = list(rows)
        reports = [metric.compute(cached) for metric in self.metrics]
        names = []
        for report in reports:
            if not str(report.name).strip():
                raise ValueError("metric report name must not be empty")
            if report.schema_version != "qitos.metric-report/1":
                raise ValueError("unsupported metric report schema")
            names.append(report.name)
        if len(names) != len(set(names)):
            raise ValueError("duplicate metric report name")
        return reports

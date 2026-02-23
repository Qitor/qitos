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


@dataclass
class MetricReport:
    name: str
    value: Any
    details: Dict[str, Any] = field(default_factory=dict)


class Metric(ABC):
    name: str = "metric"

    @abstractmethod
    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        raise NotImplementedError


class MetricRegistry:
    def __init__(self, metrics: Optional[Iterable[Metric]] = None):
        self.metrics = list(metrics or [])

    def register(self, metric: Metric) -> "MetricRegistry":
        self.metrics.append(metric)
        return self

    def compute_all(self, rows: Iterable[MetricInput]) -> List[MetricReport]:
        cached = list(rows)
        return [m.compute(cached) for m in self.metrics]

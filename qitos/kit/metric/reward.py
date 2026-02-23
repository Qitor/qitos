"""Reward-centric metrics for environment-provided success signals."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import comb
from typing import Dict, Iterable, List, Optional

from qitos.metric import Metric, MetricInput, MetricReport


def is_successful_reward(reward: float, eps: float = 1e-6) -> bool:
    r = float(reward)
    return (1.0 - float(eps)) <= r <= (1.0 + float(eps))


@dataclass
class RewardAverageMetric(Metric):
    """Average reward directly from env outputs."""

    name: str = "avg_reward"

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        vals = [float(r.reward) for r in rows if r.reward is not None]
        value = (sum(vals) / float(len(vals))) if vals else 0.0
        return MetricReport(name=self.name, value=value, details={"count": len(vals)})


@dataclass
class RewardSuccessRateMetric(Metric):
    """Success rate inferred from reward ~= 1 with tolerance."""

    name: str = "reward_success_rate"
    eps: float = 1e-6

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        data = [r for r in rows if r.reward is not None]
        total = len(data)
        success = sum(1 for r in data if is_successful_reward(float(r.reward), eps=self.eps))
        value = (float(success) / float(total)) if total else 0.0
        return MetricReport(name=self.name, value=value, details={"success": success, "total": total, "eps": self.eps})


@dataclass
class RewardPassHatMetric(Metric):
    """Tau-bench style pass^k series derived from reward-based success.

    For each task_id, let c be the number of successful trials.
    pass^k = average_task( comb(c, k) / comb(num_trials, k) ).
    """

    name: str = "reward_pass_hat"
    eps: float = 1e-6
    max_k: Optional[int] = None

    def compute(self, rows: Iterable[MetricInput]) -> MetricReport:
        data = list(rows)
        if not data:
            return MetricReport(name=self.name, value={}, details={"num_trials": 0, "task_count": 0, "eps": self.eps})

        num_trials = len(set(int(r.trial) for r in data))
        if num_trials <= 0:
            return MetricReport(name=self.name, value={}, details={"num_trials": 0, "task_count": 0, "eps": self.eps})

        c_per_task_id: Dict[str, int] = defaultdict(int)
        for r in data:
            tid = str(r.task_id)
            rv = float(r.reward) if r.reward is not None else 0.0
            c_per_task_id[tid] += 1 if is_successful_reward(rv, eps=self.eps) else 0

        if not c_per_task_id:
            return MetricReport(name=self.name, value={}, details={"num_trials": num_trials, "task_count": 0, "eps": self.eps})

        top_k = self.max_k if self.max_k is not None else num_trials
        top_k = max(1, min(int(top_k), num_trials))

        pass_hat_ks: Dict[int, float] = {}
        for k in range(1, top_k + 1):
            denom = comb(num_trials, k)
            if denom == 0:
                continue
            task_sum = 0.0
            for c in c_per_task_id.values():
                task_sum += (comb(c, k) / float(denom)) if c >= k else 0.0
            pass_hat_ks[k] = task_sum / float(len(c_per_task_id))

        return MetricReport(
            name=self.name,
            value=pass_hat_ks,
            details={"num_trials": num_trials, "task_count": len(c_per_task_id), "eps": self.eps},
        )

from __future__ import annotations

from qitos import Task
from qitos.evaluate import EvaluationContext, EvaluationSuite
from qitos.kit.evaluate import DSLEvaluator, RuleBasedEvaluator
from qitos.kit.metric import (
    AverageRewardMetric,
    PassAtKMetric,
    RewardPassHatMetric,
    RewardSuccessRateMetric,
    StopReasonDistributionMetric,
    SuccessRateMetric,
)
from qitos.metric import MetricInput, MetricRegistry


def test_evaluation_suite_rule_and_dsl():
    task = Task(id="t1", objective="solve")
    context = EvaluationContext(
        task=task,
        manifest={"summary": {"stop_reason": "final_result", "final_result": "done"}},
        extras={"reward": 1.0},
    )
    suite = EvaluationSuite(
        evaluators=[
            RuleBasedEvaluator(name="reward_rule", min_reward=1.0),
            DSLEvaluator(name="dsl_ok", expression="extras['reward'] >= 1.0"),
        ],
        mode="all",
    )
    out = suite.evaluate(context)
    assert out.success is True
    assert len(out.results) == 2


def test_metric_registry_basic_and_pass_at_k():
    rows = [
        MetricInput(task_id="a", trial=0, success=True, reward=1.0),
        MetricInput(task_id="a", trial=1, success=False, reward=0.0),
        MetricInput(task_id="b", trial=0, success=True, reward=1.0),
        MetricInput(task_id="b", trial=1, success=True, reward=1.0),
    ]
    registry = MetricRegistry([SuccessRateMetric(), AverageRewardMetric(), PassAtKMetric(k=1)])
    reports = {r.name: r for r in registry.compute_all(rows)}

    assert "success_rate" in reports
    assert abs(float(reports["success_rate"].value) - 0.75) < 1e-9

    assert "avg_reward" in reports
    assert abs(float(reports["avg_reward"].value) - 0.75) < 1e-9

    assert "pass_at_k_1" in reports
    assert float(reports["pass_at_k_1"].value) >= 0.0


def test_stop_reason_distribution_metric():
    rows = [
        MetricInput(task_id="a", stop_reason="final"),
        MetricInput(task_id="b", stop_reason="budget_steps"),
        MetricInput(task_id="c", stop_reason="final"),
    ]
    rep = StopReasonDistributionMetric().compute(rows)
    assert rep.name == "stop_reason_distribution"
    assert rep.value["final"] == 2
    assert rep.value["budget_steps"] == 1


def test_reward_success_and_pass_hat_metric():
    rows = [
        MetricInput(task_id="a", trial=0, reward=1.0),
        MetricInput(task_id="a", trial=1, reward=0.0),
        MetricInput(task_id="b", trial=0, reward=1.0),
        MetricInput(task_id="b", trial=1, reward=1.0),
    ]
    sr = RewardSuccessRateMetric().compute(rows)
    assert abs(float(sr.value) - 0.75) < 1e-9

    ph = RewardPassHatMetric().compute(rows)
    assert 1 in ph.value and 2 in ph.value
    assert ph.value[1] >= ph.value[2]

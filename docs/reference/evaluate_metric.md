# Evaluate & Metric

## Separation of concerns

QitOS uses two layers:

1. `qitos.evaluate`: task-level judgement for one trajectory.
2. `qitos.metric`: benchmark-level aggregation over many runs.

This keeps custom success logic independent from reporting logic.

## Core interfaces

### Evaluate

- `TrajectoryEvaluator`
- `EvaluationContext`
- `EvaluationResult`
- `EvaluationSuite`

### Metric

- `Metric`
- `MetricInput`
- `MetricReport`
- `MetricRegistry`

## Kit implementations

### Evaluators (`qitos.kit.evaluate`)

- `RuleBasedEvaluator`
- `DSLEvaluator`
- `ModelBasedEvaluator`

### Metrics (`qitos.kit.metric`)

- `SuccessRateMetric`
- `AverageRewardMetric`
- `RewardSuccessRateMetric` (success from reward≈1)
- `RewardPassHatMetric` (tau-style pass^k series)
- `PassAtKMetric`
- `MeanStepsMetric`
- `StopReasonDistributionMetric`
- `CustomFieldMetric`

## Minimal usage

```python
from qitos.evaluate import EvaluationContext, EvaluationSuite
from qitos.kit.evaluate import RuleBasedEvaluator

suite = EvaluationSuite([RuleBasedEvaluator(min_reward=1.0)], mode="all")
out = suite.evaluate(EvaluationContext(task=task, manifest=manifest, extras={"reward": 1.0}))
print(out.success, out.score)
```

```python
from qitos.metric import MetricInput, MetricRegistry
from qitos.kit.metric import SuccessRateMetric, PassAtKMetric

rows = [MetricInput(task_id="a", trial=0, success=True), MetricInput(task_id="a", trial=1, success=False)]
reports = MetricRegistry([SuccessRateMetric(), PassAtKMetric(k=1)]).compute_all(rows)
```

## Source Index

- [qitos/evaluate/base.py](https://github.com/Qitor/qitos/blob/main/qitos/evaluate/base.py)
- [qitos/metric/base.py](https://github.com/Qitor/qitos/blob/main/qitos/metric/base.py)
- [qitos/kit/evaluate/rule_based.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/evaluate/rule_based.py)
- [qitos/kit/metric/basic.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/metric/basic.py)

# Evaluate 与 Metric

## 职责拆分

QitOS 将评测拆为两层：

1. `qitos.evaluate`：单条 trajectory 的任务完成判定。
2. `qitos.metric`：跨任务/跨运行的聚合指标。

这样可以把“成功定义”与“指标报表”解耦。

## 核心接口

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

## Kit 预实现

### Evaluator（`qitos.kit.evaluate`）

- `RuleBasedEvaluator`
- `DSLEvaluator`
- `ModelBasedEvaluator`

### Metric（`qitos.kit.metric`）

- `SuccessRateMetric`
- `AverageRewardMetric`
- `RewardSuccessRateMetric`（基于 reward≈1 判定成功）
- `RewardPassHatMetric`（tau 风格 pass^k 序列）
- `PassAtKMetric`
- `MeanStepsMetric`
- `StopReasonDistributionMetric`
- `CustomFieldMetric`

## 最小示例

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

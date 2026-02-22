# 生产落地指南

## 目标

把“能跑”升级为“可观测、可回归、可维护”。

## P0 稳定性清单

1. 配置预算（steps/runtime/tokens）。
2. 监控 stop reason 分布。
3. 持久化关键运行 trace。
4. 保留 failure report 用于定位。

## 建议上线流程

1. 固定模型与 parser 版本。
2. 准备回归任务集。
3. 每次变更跑回归并设阈值。
4. 以 trace 汇总结果驱动发布决策。

## 事故排查路径

1. 定位 `run_id`
2. 看 `manifest.summary.stop_reason`
3. 在 `events.jsonl` 找首个 `ok=false` 事件
4. 在 `steps.jsonl` 查看对应 step
5. 分类根因：parser / tool / env / model 漂移

## Source Index

- [qitos/engine/stop_criteria.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/stop_criteria.py)
- [qitos/engine/recovery.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/recovery.py)
- [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)
- [qitos/trace/schema.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/schema.py)
- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)

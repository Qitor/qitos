# Trace 与评测

## 目标

把运行日志提升为可对比、可复现实验资产。

## 每次运行至少要记录

1. Task 元数据
2. 模型/Parser/Tool 元数据
3. 阶段事件（`run_id`, `step_id`, `phase`, `ts`, `ok`）
4. `stop_reason` 与最终结果
5. 失败报告（若有）

## 教程：快速做一轮回归评测

1. 用 `Task` 构建小任务集（5-20 条）。
2. 跑基线，收集统计。
3. 跑候选方案（同预算、同环境）。
4. 对比：
- 成功率
- 平均步数
- 不可恢复错误占比
- 预算触发占比

## 指标模板

| 指标 | Baseline | Candidate | Delta |
|---|---:|---:|---:|
| 成功率 |  |  |  |
| 平均步数 |  |  |  |
| 不可恢复错误比例 |  |  |  |
| Budget Stop 比例 |  |  |  |

## Source Index

- [qitos/trace/events.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/events.py)
- [qitos/trace/schema.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/schema.py)
- [qitos/trace/writer.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/writer.py)
- [qitos/render/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/render/hooks.py)
- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)

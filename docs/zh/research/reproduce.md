# 论文范式复现

## 目标

用最少框架改动，快速复现典型 Agent 范式，并能横向比较。

## 仓库内可直接运行的范式

- ReAct：`examples/patterns/react.py`
- PlanAct：`examples/patterns/planact.py`
- Reflexion 风格：`examples/patterns/reflexion.py`
- ToT 风格：`examples/patterns/tot.py`

## 教程：ReAct -> PlanAct

### 第 1 步：运行 ReAct 基线

```bash
python examples/patterns/react.py
```

### 第 2 步：运行 PlanAct

```bash
python examples/patterns/planact.py
```

### 第 3 步：对比 trace

重点看：

1. `summary.stop_reason`
2. `summary.steps`
3. `DECIDE` 阶段 payload 结构
4. `failure_report` 变化

## 复现实验质量要求

1. 固定任务集。
2. 固定预算参数。
3. 记录模型与 parser。
4. 每个配置至少重复 3 次。
5. 同时报告成功率、步数与失败类型。

## Source Index

- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [examples/patterns/tot.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/tot.py)
- [qitos/kit/parser/react_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/react_parser.py)
- [qitos/kit/critic/self_reflection.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/critic/self_reflection.py)

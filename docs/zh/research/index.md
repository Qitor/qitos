# 研究者文档总览

## 目标

帮助你用同一套内核完成三件事：

1. 快速复现已有 Agent 方法。
2. 严格控制实验变量并开展消融。
3. 产出可复现、可比较、可解释的实验结果。

## 建议阅读顺序

1. [内核架构](kernel.md)
2. [内核深度拆解](kernel_deep_dive.md)
3. [论文范式复现](reproduce.md)
4. [新 Agent 设计方法](design.md)
5. [从 Core 实现新 Agent](agent_authoring.md)
6. [Trace 与评测](trace_eval.md)
7. [30 分钟实验课](labs/index.md)

## 30 分钟起步

```bash
pip install -e .
python examples/patterns/react.py
python examples/patterns/planact.py
```

随后对比两次运行的 trace，观察 `stop_reason`、`steps`、失败类型分布。

## Source Index

- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/trace/writer.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/writer.py)

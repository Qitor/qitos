# 为什么是 QitOS

## 目标

明确 QitOS 的优势边界与取舍，而不是泛泛宣传。

## QitOS 的核心取舍

QitOS 明确偏向：**研究级可控性 + 工程级可组合性**。

1. 顶层抽象更少，主线更清晰。
2. 运行阶段更显式，行为更可解释。
3. hooks + trace 更适合做方法比较和消融。

## 何时更适合用 QitOS

1. 你要复现/改进 Agent 方法，而不只是搭应用流程。
2. 你要稳定比较不同策略，不想被多套框架概念干扰。
3. 你需要把失败定位到具体阶段与具体结构化原因。

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)
- [qitos/trace/writer.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/writer.py)

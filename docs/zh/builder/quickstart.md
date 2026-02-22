# 快速开始

## 目标

在最短时间内完成一次“运行 -> 观察 -> 调试”的完整闭环。

## 前置条件

```bash
pip install -e .
```

请先完成模型配置：
- [配置与 API Key](configuration.md)

## 第 1 步：运行最小示例

```bash
python examples/quickstart/minimal_agent.py
```

## 第 2 步：运行模式示例

```bash
python examples/patterns/react.py
```

## 第 3 步：查看运行产物

关注：

- `runs/<run_id>/manifest.json`
- `runs/<run_id>/events.jsonl`
- `runs/<run_id>/steps.jsonl`

## 第 4 步：打开可视化面板

```bash
qita board --logdir runs
```

然后继续看：

- [qita 使用指南](qita.md)

## 常见问题

1. 没触发模型调用
- 如果 `decide` 每步都返回 `Decision`，Engine 不会走默认 LLM 路径。

2. Action 没执行
- 检查 parser 输出是否是 `Decision.act`，且工具名可匹配。

3. 环境能力不匹配
- 检查 Env 是否支持工具声明的 ops groups。

## Source Index

- [examples/quickstart/minimal_agent.py](https://github.com/Qitor/qitos/blob/main/examples/quickstart/minimal_agent.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
- [qitos/render/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/render/hooks.py)

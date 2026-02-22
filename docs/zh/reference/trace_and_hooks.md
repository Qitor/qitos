# Hooks 与 Trace

## 目标

把可观测性当作稳定契约，用于研究对比和线上调试。

## Hooks

Hook context 与事件 payload 都包含标准字段：

- `run_id`, `step_id`, `phase`, `ts`
- `state_digest`, `decision_digest`, `action_digest`

在代码里，你通过继承 `EngineHook` 来实现 hook，并在每个 phase 回调里拿到 `HookContext`。

### 最小 hook 示例

```python
from qitos.engine import EngineHook

class PrintDecisions(EngineHook):
    def on_after_decide(self, ctx, engine) -> None:
        print(f"[{ctx.run_id}] step={ctx.step_id} phase={ctx.phase} decision={ctx.decision}")
```

### 如何挂载 hooks

你既可以直接传给 `Engine(...)`，也可以通过 `agent.run(..., hooks=[...])` 传入：

```python
from qitos import Engine
from qitos.kit.env import HostEnv

engine = Engine(agent=my_agent, env=HostEnv(workspace_root="./playground"), hooks=[PrintDecisions()])
result = engine.run("do something")
```

## Trace 产物

一次 run 通常包含：

- `manifest.json`
- `events.jsonl`
- `steps.jsonl`

Trace 由 `TraceWriter` 写入，设计目标是：

- `*.jsonl` 追加写入，适合大 run
- schema version 化，便于长期兼容
- 可回放：qita 直接读取同一套 artifacts

## qita

用 `qita` 进行查看/回放/导出：

- [qita 使用指南](../builder/qita.md)

## Source Index

- [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)
- [qitos/trace/writer.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/writer.py)
- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)

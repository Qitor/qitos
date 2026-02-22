# First Run (Minimal + LLM)

## Goal

Get two runs working end-to-end:

1. a minimal run (no model call) to validate the kernel wiring
2. an LLM-backed ReAct run to validate model + parser + tools + trace

## 0) (One-time) configure model for LLM examples

QitOS examples read:

- `OPENAI_BASE_URL` (provider endpoint)
- `OPENAI_API_KEY` (or `QITOS_API_KEY`)

Fastest setup:

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"
```

If you prefer CLI-only config, see: [Configuration & API Keys](../builder/configuration.md).

## 1) Run the minimal agent (no LLM)

```bash
python examples/quickstart/minimal_agent.py
```

What to check:

1. The program completes with a final result.
2. The run has a clear stop reason.
3. If traces are enabled, you can find a run folder under `runs/`.

## 2) Run an LLM-backed agent (ReAct)

This run exercises the default model path:

- `AgentModule.decide(...) -> None`
- Engine builds messages (system + memory + prepared user text)
- Engine calls `llm(messages)`
- Parser turns text into `Decision(Action(...))`
- Engine executes the tool call and reduces into state

```bash
python examples/patterns/react.py --workspace ./playground
```

What to check:

1. You can see model output in the terminal render (unless `--disable-render`).
2. Tools are actually called (you should see action results in scratchpad/trace).
3. A run folder exists under `runs/` and contains `manifest.json`, `events.jsonl`, `steps.jsonl`.

## Next

- If model calls fail: [Configuration & API Keys](../builder/configuration.md)
- Inspect your run with qita: [qita Guide](../builder/qita.md)

## Source Index

- [examples/quickstart/minimal_agent.py](https://github.com/Qitor/qitos/blob/main/examples/quickstart/minimal_agent.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)

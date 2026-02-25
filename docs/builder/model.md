# Model Integration

## Goal

Connect your model in a way that is robust for multi-step agent runs.

## Default Engine-driven model path

When `AgentModule.decide(...)` returns `None`:

1. Engine calls `agent.prepare(state)`.
2. Engine adds system prompt from `build_system_prompt`.
3. Engine retrieves memory messages.
4. Engine calls `agent.llm(messages)`.
5. Parser maps model output to `Decision`.

## Minimal model wiring

```python
from qitos import AgentModule
from qitos.kit.parser import ReActTextParser

class MyAgent(AgentModule):
    def __init__(self, llm):
        super().__init__(tool_registry=..., llm=llm, model_parser=ReActTextParser())

    def build_system_prompt(self, state):
        return "You are a precise coding assistant."

    def prepare(self, state):
        return f"Task: {state.task}\nObservation: {observation}"

    def decide(self, state, observation):
        return None
```

## Config recommendation

Use env vars, not hardcoded keys:

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="..."
```

## Reliability checklist

1. Parser supports your output format (JSON/XML/ReAct/function-like).
2. Prompt instructs exact output protocol.
3. Parser has fallback behavior for malformed/truncated outputs.
4. Trace includes model name and parser name for audit.

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/models/openai.py](https://github.com/Qitor/qitos/blob/main/qitos/models/openai.py)
- [qitos/kit/parser/react_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/react_parser.py)
- [qitos/kit/parser/func_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/func_parser.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)

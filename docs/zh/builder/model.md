# 模型接入

## 目标

用最少样板代码把模型接入到多步 Agent 循环中，并保证可调试性。

## 默认调用路径

当 `AgentModule.decide(...)` 返回 `None` 时：

1. Engine 调 `agent.prepare(state, observation)`
2. Engine 拼接 system prompt
3. Engine 注入 memory messages
4. Engine 调 `agent.llm(messages)`
5. parser 把模型输出转成 `Decision`

## 最小接入示例

```python
from qitos import AgentModule
from qitos.kit.parser import ReActTextParser

class MyAgent(AgentModule):
    def __init__(self, llm):
        super().__init__(tool_registry=..., llm=llm, model_parser=ReActTextParser())

    def build_system_prompt(self, state):
        return "你是严谨的代码智能体。"

    def prepare(self, state, observation):
        return f"任务: {state.task}\n观察: {observation}"

    def decide(self, state, observation):
        return None
```

## 推荐配置方式

用环境变量，不要把 key 写死在代码里：

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_key>"
```

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/models/openai.py](https://github.com/Qitor/qitos/blob/main/qitos/models/openai.py)
- [qitos/kit/parser/react_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/react_parser.py)
- [qitos/kit/parser/func_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/func_parser.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)

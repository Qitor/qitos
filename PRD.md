# 🧘 qitos Framework v3.1 PRD

## —— 为开发者幸福感而生的状态驱动 Agent 框架

> **核心宣言**：
> 1. **显式优于隐式**：拒绝黑盒魔法，所有状态变更必须可追踪、可调试。
> 2. **状态即一切**：`AgentContext` 是唯一的真理来源。
> 3. **调试即开发**：提供像 IDE 一样的单步执行（Eager Execution）和时光倒流（Replay）能力。
> 不得使用toml，使用requirements.txt和 setup.py 进行依赖管理。
> 

---

## 一、系统架构概览

qitos v3.1 采用 **"Engine-Managed, State-Driven"** (引擎托管，状态驱动) 的架构。用户只负责定义“怎么看”（Perceive）和“怎么记”（Update），其余的循环、工具调用、错误重试均由引擎负责。

### 1.1 核心数据流

```mermaid
flowchart TD
    subgraph State [AgentContext (唯一状态)]
        Ctx[Context Dict]
        Log[Mutation Log]
    end

    subgraph UserCode [AgentModule (用户逻辑)]
        Perc([perceive])
        Upd([update_context])
    end

    subgraph Runtime [ExecutionEngine (框架托管)]
        LLM[LLM 调用]
        Parser[工具解析]
        Exec[工具执行]
    end

    Start((Task)) --> Ctx
    Ctx --> Perc
    Perc -- Messages --> LLM
    LLM -- Raw Text --> Parser
    Parser -- Tool Calls --> Exec
    Exec -- Observations --> Upd
    Upd -- Metadata Changes --> Ctx
    Ctx --> Log
    
    %% 循环控制
    Upd --> Check{Max Steps?}
    Check -- No --> Perc
    Check -- Yes/Final --> End((Result))

```

---

## 二、核心组件设计

### 2.1 `AgentContext`：全知全能的状态容器

`AgentContext` 不仅仅是一个字典，它是具备**自我审计能力**的状态机。

* **功能**：存储所有运行时数据（Task, History, Metadata）。
* **特性**：
* **Dot Access**：支持 `ctx.task` 访问，同时也支持 `ctx["task"]`。
* **Mutation Logging**：任何属性的修改（`__setitem__`, `__setattr__`）都会自动记录到 `_mutation_log`。
* **Memory Window**：自动维护最近 N 轮的 `observations` 快照，避免 Context 爆炸。



```python
# qitos/core/context.py

class AgentContext(OrderedDict):
    """
    Agent 的唯一状态容器。
    所有的状态变更都必须发生在这里，并且会被自动记录。
    """
    def __init__(self, task: str, max_steps: int = 10, **kwargs):
        super().__init__()
        # 标准字段
        self["task"] = task
        self["current_step"] = 0
        self["max_steps"] = max_steps
        self["observations"] = [] # 当前轮次的观察结果（只读）
        self["_final_result"] = None
        
        # 审计日志
        self["_mutation_log"] = [] 
        
        # 用户自定义字段
        self["metadata"] = kwargs

    def __setitem__(self, key: str, value: Any):
        # 记录变更日志：谁，在第几步，改了什么，旧值是什么，新值是什么
        if key != "_mutation_log":
            self["_mutation_log"].append({
                "step": self.get("current_step", 0),
                "key": key,
                "old_value": self.get(key), # 简化处理，实际需深拷贝或repr
                "new_value": value
            })
        super().__setitem__(key, value)
    
    # ... __getattr__, __setattr__, to_json, from_json 实现 ...

```

### 2.2 `AgentModule`：极简的用户接口

v3.1 进一步简化了用户接口。90% 的场景下，用户只需要关注 `perceive`。

* **Perceive (感知)**：Context -> LLM Messages。决定此刻 Agent 看到什么。
* **Update Context (记忆)**：Observations -> Context。决定 Agent 记住什么。（v3.1 改为可选）

```python
# qitos/core/agent.py
from abc import ABC, abstractmethod
from typing import List, Dict, Callable, Any, Optional

class AgentModule(ABC):
    def __init__(
        self, 
        toolkit: ToolRegistry, 
        llm: Callable,
        system_prompt: Optional[str] = None  # <--- 加回这里
    ):
        self.toolkit = toolkit
        self.llm = llm
        self.system_prompt = system_prompt

    @abstractmethod
    def perceive(self, context: AgentContext) -> List[Dict[str, str]]:
        """
        构建消息列表。
        注意：开发者需要显式地将 system_prompt 放入消息列表（如果需要的话）。
        """
        pass

    def update_context(self, context: AgentContext, observations: List[Any]) -> None:
        pass

```

### 2.3 `ToolRegistry` & Skills：声明式工具系统 (v3.1 新增)

不再需要繁琐的 JSON Schema 定义。利用 Python 的类型提示（Type Hints）和文档字符串（Docstrings），自动生成工具描述。

* **原则**：写工具就是写 Python 函数。
* **装饰器**：`@skill`
* **约束**：必须有类型注解；必须有 Docstring；返回值建议为 `Dict`。

```python
# qitos/core/skills.py

from typing import Dict, Any

def skill(domain: str = "default"):
    """装饰器：标记一个函数为 Agent 可用的 Skill"""
    def decorator(func):
        func._is_skill = True
        func._domain = domain
        return func
    return decorator

# 用户代码示例
@skill(domain="file_io")
def read_file(path: str, encoding: str = "utf-8") -> Dict[str, Any]:
    """
    读取指定路径的文件内容。
    
    Args:
        path: 文件绝对路径
        encoding: 文件编码，默认 utf-8
    Returns:
        包含 content 或 error 的字典
    """
    try:
        with open(path, 'r', encoding=encoding) as f:
            return {"status": "success", "content": f.read()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

```

---

## 三、执行引擎 (`ExecutionEngine`)

引擎是幕后的调度者，负责处理脏活累活。

### 3.1 标准执行循环 (`step`)

1. **Hook**: `on_step_start`
2. **Perceive**: 调用 `agent.perceive(context)` 获取 messages。
3. **LLM**: 调用 `agent.llm(messages)` 获取 raw response。
4. **Parse**: 解析 raw response，提取 `tool_calls` 或 `final_answer`。
5. **Branch**:
* 若是 `final_answer`: 设置 `context._final_result`，结束。
* 若是 `tool_calls`:
1. **Execute**: 并行/串行执行工具（支持 Sync/Async）。
2. **Capture**: 捕获结果（及异常），标准化为 `observations` List。
3. **Update**: 调用 `agent.update_context(context, observations)`。
4. **Inject**: Engine 刷新 `context.observations` 为本轮结果。




6. **Hook**: `on_step_end`
7. **Increment**: `context.current_step += 1`

### 3.2 错误处理策略

Engine 内置 `ToolErrorHandler`，支持配置策略：

* `raise`: 直接抛出异常（调试用）。
* `inject_error`: 将异常信息格式化为 Observation 返回给 Agent（生产用，让 Agent 自我修正）。

---

## 四、CLI 工具链：开发者幸福感的来源

qitos v3.1 的 CLI 不仅仅是启动器，它是完整的开发环境。

### 4.1 `qitos init <name>`

生成标准目录结构，包含 `agent.py`, `skills.py`, `prompts.py`。

### 4.2 `qitos play` (交互式沙盒)

这是 v3.1 的杀手级功能。它启动一个 REPL 环境，允许开发者介入 Agent 的每一步。

* **命令支持**：
* `(text)`: 作为 User 输入发送给 Agent。
* `:step`: 仅执行一步（感知 -> 推理 -> 工具 -> 暂停）。
* `:ctx`: 打印当前 Context JSON。
* `:log`: 查看最近的 Mutation Log。
* `:undo`: 回滚到上一步（利用 Mutation Log 反向操作）。
* `:save <file>`: 保存当前现场快照。



### 4.3 `qitos replay <trace_id/file>`

从 Crash 现场恢复。加载 `trace.json`，重建 `AgentContext`，重现 Bug。

### 4.4 `qitos list-tools`

扫描项目中的 `@skill`，生成可读的工具列表文档，检查 Schema 合法性。

---

## 五、Inspector：可视化与可观测性

Inspector 是一个基于 Web 或 TUI 的工具，用于可视化 `_mutation_log`。

* **Timeline View**: 左侧显示 Step 0 -> Step N 的时间轴。
* **Diff View**: 点击某一步，右侧显示 Context 在这一步发生了什么变化（Diff）。
* *e.g.* `metadata.search_results`: `None` -> `[Result A, Result B]`


* **Performance**: 显示 LLM 耗时、工具执行耗时。

---

## 六、API 参考 (Cheatsheet)

### 6.1 快速创建一个 Simple Agent

```python
from qitos import create_simple_agent, ToolRegistry
from my_skills import web_search

# 零样板代码，由工厂函数组装
agent = create_simple_agent(
    system_prompt="你是一个研究助手，请使用工具获取信息。",
    toolkit=ToolRegistry([web_search]),
    llm=openai_client.chat.completions.create,
    model="gpt-4"
)

# 直接运行
result = agent("分析一下 qitos Framework v3.1 的优势")

```

### 6.2 目录结构规范

```text
my_agent/
├── app.py             # 入口 (create_simple_agent 或 自定义类)
├── skills/            # 工具包
│   ├── __init__.py    # 暴露 ToolRegistry
│   ├── browser.py     # @skill 定义
│   └── calculator.py
├── prompts.py         # 提示词模板
├── config.yaml        # 配置 (LLM keys, max_steps)
└── requirements.txt

```

---

## 七、开发与发布计划

### Phase 1: Core (v3.1.0-alpha)

* [ ] `AgentContext` 实现 (Mutation Log, Serialization)。
* [ ] `ExecutionEngine` 基础循环。
* [ ] `ToolRegistry` 与 `@skill` 解析器。
* [ ] 单元测试覆盖率 > 80%。

### Phase 2: DX (v3.1.0-beta)

* [ ] CLI 实现 (`play`, `init`, `replay`)。
* [ ] `Inspector` 基础文本版实现。
* [ ] 完善的错误处理与重试机制。

### Phase 3: Ecosystem (v3.1.0-stable)

* [ ] `qitos serve` (FastAPI wrapper)。
* [ ] 预置通用 Skill Sets (File, Shell, Web)。
* [ ] 官方文档与最佳实践示例。

---

## 八、FAQ

**Q: 为什么不使用 JSON Schema 定义工具？**
A: 手写 JSON Schema 容易出错且冗余。Python 的 Type Hint 已经足够表达类型，Docstring 足够表达语义。我们遵循 DRY (Don't Repeat Yourself) 原则。

**Q: `update_context` 既然可选，什么时候需要用它？**
A: 当你需要跨轮次的“长期记忆”时。例如，Agent 在第1步搜索到了 10 篇文章，你可能希望在 `update_context` 中对它们进行摘要，并存入 `context.metadata['summary']`，而不是让原始的 10 篇文章一直停留在 `observations` 窗口中占用 Token。

**Q: 如何集成 LangChain 或 LlamaIndex 的工具？**
A: `ToolRegistry` 将提供适配器（Adapter），可以将 LangChain 的 `BaseTool` 包装成 qitos 的 Skill。
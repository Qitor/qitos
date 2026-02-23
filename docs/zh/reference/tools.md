# Tool 与 ToolRegistry

## 目标

理解工具注册与执行路径（ACT 阶段）。

## 工具注册

通过 `ToolRegistry` 注册工具，可以注册：

1. 函数工具
2. 类工具
3. ToolSet（工具集合）

## 函数工具（推荐）

用 `@tool` 给函数挂上 name/description/required_ops 等元信息，但不改变函数本身的调用语义。

```python
from qitos import ToolRegistry, tool

@tool(name="add", description="Add two integers.")
def add(a: int, b: int) -> int:
    return a + b

registry = ToolRegistry().register(add)
```

## 类工具（需要配置时用）

如果你的工具需要配置（workspace_root、缓存、凭证、client 等），用类把多个工具方法包起来，再用 `ToolRegistry.include(...)` 扫描并注册。

```python
from qitos import ToolRegistry, tool

class MathTools:
    def __init__(self, bias: int = 0):
        self.bias = bias

    @tool(name="add_bias", description="Add two ints plus a configured bias.")
    def add_bias(self, a: int, b: int) -> int:
        return a + b + self.bias

registry = ToolRegistry().include(MathTools(bias=3))
```

## ToolSet（bundle + 生命周期）

当一组工具需要 setup/teardown，或者希望统一 namespace 前缀时，用 ToolSet + `register_toolset(...)`。

```python
from typing import Any
from qitos import ToolRegistry, tool

class MyToolSet:
    name = "myset"
    version = "1"

    def setup(self, context: dict[str, Any]) -> None:
        pass

    def teardown(self, context: dict[str, Any]) -> None:
        pass

    def tools(self):
        @tool(name="ping")
        def ping() -> str:
            return "pong"
        return [ping]

registry = ToolRegistry().register_toolset(MyToolSet(), namespace="util")
# 工具名会变成：util.ping
```

## Env/ops 注入（高级但非常关键）

工具可以声明需要的 ops groups（例如 `file`、`process`、`web`）。执行时 Engine 会从你选定的 `Env` 解析这些 ops，
并通过 `runtime_context` 以及可选的“形参注入”方式传入：

- `runtime_context`：只要你的工具形参里有 `runtime_context` 就能拿到
- `env`：工具形参里有 `env` 时会自动注入
- `ops`：工具形参里有 `ops` 时会自动注入
- `file_ops` / `process_ops`：工具形参里有它们时会自动注入

这就是为什么“同一个工具语义”可以跑在 host/docker/remote 等不同后端，只要对应 Env 支持这些 ops groups。

## 工具执行路径

```mermaid
flowchart TB
  A[Decision.act] --> B[Engine ACT]
  B --> C[ActionExecutor]
  C --> D[ToolRegistry.call]
  C --> E[Env ops resolve]
  D --> F[Tool.run]
```

## 预定义工具包（`qitos.kit.tool`）

这些组件可以直接组合使用，类似 `torch.nn` 的现成模块。

- 编辑器工具包：
  - `EditorToolSet`（`view`、`create`、`str_replace`、`insert`、`search`、`list_tree`、`replace_lines`）
- EPUB 工具包：
  - `EpubToolSet`（`list_chapters`、`read_chapter`、`search`）
- 文件工具：
  - `WriteFile`、`ReadFile`、`ListFiles`
- 进程工具：
  - `RunCommand`
- HTTP/Web 工具：
  - `HTTPRequest`、`HTTPGet`、`HTTPPost`、`HTMLExtractText`
- 文本浏览器工具：
  - `WebSearch`、`VisitURL`、`PageDown`、`PageUp`、`FindInPage`、`FindNext`、`ArchiveSearch`
- 思维工具集：
  - `ThinkingToolSet`、`ThoughtData`
- 工具库：
  - `InMemoryToolLibrary`、`ToolArtifact`、`BaseToolLibrary`
- 注册表快捷构造：
  - `math_tools()`、`editor_tools(workspace_root)`

导入示例：

```python
from qitos.kit.tool import EditorToolSet, RunCommand, HTTPGet, ThinkingToolSet
```

## 预定义规划模块（`qitos.kit.planning`）

- LLM 编排模块：
  - `ToolAwareMessageBuilder`、`LLMDecisionBlock`
- 计划工具：
  - `PlanCursor`、`parse_numbered_plan`
- 搜索策略：
  - `GreedySearch`、`DynamicTreeSearch`
- 状态辅助函数：
  - `append_log`、`format_action`、`set_final`、`set_if_empty`

导入示例：

```python
from qitos.kit.planning import DynamicTreeSearch, PlanCursor, LLMDecisionBlock
```

## Source Index

- [qitos/core/tool.py](https://github.com/Qitor/qitos/blob/main/qitos/core/tool.py)
- [qitos/core/tool_registry.py](https://github.com/Qitor/qitos/blob/main/qitos/core/tool_registry.py)
- [qitos/engine/action_executor.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/action_executor.py)
- [qitos/kit/tool/toolset.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/tool/toolset.py)
- [qitos/kit/tool/__init__.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/tool/__init__.py)
- [qitos/kit/planning/__init__.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/planning/__init__.py)

# 03 Tools and ToolSets

## Why Two Forms Exist

- Function tool: fastest path for a single capability.
- ToolSet class: best for grouped capabilities with shared setup/config.

## A Function Tool

```python
from qitos import ToolRegistry, tool

registry = ToolRegistry()

@tool(name="add", description="Add two integers")
def add(a: int, b: int) -> int:
    return a + b

registry.register(add)
```

## A ToolSet With Lifecycle

```python
from typing import Any
from qitos import ToolRegistry, tool

class MathSet:
    name = "math"
    version = "1.0"

    def setup(self, context: dict[str, Any]) -> None:
        # e.g., warm cache / load config
        pass

    def teardown(self, context: dict[str, Any]) -> None:
        pass

    @tool(name="add")
    def add(self, a: int, b: int) -> int:
        return a + b

    @tool(name="multiply")
    def multiply(self, a: int, b: int) -> int:
        return a * b

    def tools(self):
        return [self.add, self.multiply]

registry = ToolRegistry()
registry.register_toolset(MathSet())
```

## Choosing Between Them

- Use function tools for papers/ablation prototypes.
- Use ToolSet for domain packs (editor/web/vision/ppt) and env-aware config.

## Research Tip

When publishing a template, prefer ToolSet so others can swap configs (workspace root, API endpoint, model adapters) without touching agent logic.

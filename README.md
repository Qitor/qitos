# QitOS Framework v3.1

<p align="center">
  <img src="docs/logo.png" alt="QitOS Logo" width="200"/>
</p>

<p align="center">
  <strong>🧘 QitOS Framework v3.1</strong>
</p>

<p align="center">
  <em>为开发者幸福感而生的状态驱动 Agent 框架</em>
</p>

<p align="center">
  <a href="#-features">特性</a> •
  <a href="#quick-start">快速开始</a> •
  <a href="#documentation">文档</a> •
  <a href="#examples">示例</a>
</p>

---

## 核心宣言

1. **显式优于隐式**：拒绝黑盒魔法，所有状态变更必须可追踪、可调试。
2. **状态即一切**：`AgentContext` 是唯一的真理来源。
3. **调试即开发**：提供像 IDE 一样的单步执行（Eager Execution）和时光倒流（Replay）能力。

## 特性

### 🎯 极简接口
- 只需实现 `perceive` 方法（`update_context` 可选）
- 依赖注入：toolkit、llm、system_prompt 均可运行时替换

### 📊 完整可观测性
- **Mutation Log**：自动记录所有状态变更
- **Timeline View**：可视化执行时间轴
- **Diff View**：对比每步状态变化
- **Performance Stats**：LLM 和工具执行耗时统计

### 🔧 强大工具系统
- **@skill 装饰器**：用 Python 函数定义工具
- **自动 Schema 生成**：从类型注解和文档字符串生成
- **ToolRegistry**：工具注册与管理

### 🚀 Eager Execution
- **单步执行**：像调试一样开发 Agent
- **状态快照**：随时保存和恢复执行现场
- **时光倒流**：利用 Mutation Log 回滚状态

### 💡 开发者体验
- **CLI 工具链**：`init`、`play`、`replay`、`serve`
- **交互式沙盒**：实时调试 Agent
- **快速原型**：零样板代码创建 Simple Agent

## 快速开始

### 安装

```bash
pip install qitos
```

### 创建项目

```bash
# 初始化新项目
qitos init my-agent
cd my-agent

# 启动交互式沙盒
qitos play
```

### 第一个 Agent

```python
from qitos import AgentModule, ToolRegistry, skill


@skill(domain="calculator")
def calculate(expression: str) -> dict:
    """计算数学表达式"""
    return {"result": eval(expression)}


class MyAgent(AgentModule):
    def perceive(self, context):
        return [
            {"role": "system", "content": "你是一个计算助手。"},
            {"role": "user", "content": context.task}
        ]


# 运行 Agent
agent = MyAgent(
    toolkit=ToolRegistry([calculate]),
    llm=lambda msgs: "Final Answer: 42"
)

result = agent("计算 40 + 2")
print(result)  # "42"
```

## 文档

### 核心概念

- [AgentContext](docs/context.md) - 状态容器
- [AgentModule](docs/agent.md) - Agent 基类
- [ToolRegistry](docs/tools.md) - 工具注册
- [ExecutionEngine](docs/engine.md) - 执行引擎
- [Hooks](docs/hooks.md) - 生命周期钩子

### CLI 命令

- [qitos init](docs/cli/init.md) - 初始化项目
- [qitos play](docs/cli/play.md) - 交互式沙盒
- [qitos replay](docs/cli/replay.md) - 重放轨迹
- [qitos serve](docs/cli/serve.md) - API 服务

## 示例

查看 [examples](examples/) 目录获取完整示例：

- [Simple Agent](examples/simple_agent.py) - 最简单的 Agent
- [Calculator Agent](examples/calculator.py) - 计算器 Agent
- [Research Agent](examples/research.py) - 研究助手 Agent
- [ReAct Agent](examples/react.py) - ReAct 风格 Agent

## 贡献

欢迎贡献代码！请查看 [贡献指南](CONTRIBUTING.md)。

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。

---

<p align="center">
  用 🧘 之力构建
</p>

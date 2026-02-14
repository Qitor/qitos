# QitOS Developer Documentation

> Build your own LLM Agent with minimal code.

## Quick Start

### 1. Installation

```bash
pip install qitos
# Or for development
pip install -e .
```

### 2. Your First Agent

```python
from qitos import AgentModule, AgentContext, ToolRegistry
from qitos.models import OpenAICompatibleModel
from qitos.render import RichConsoleHook

# Step 1: Define tools
def add(a: int, b: int) -> int:
    """
    Add two numbers.
    
    :param a: First number
    :param b: Second number
    
    Returns the sum of two numbers
    """
    return a + b

def multiply(a: int, b: int) -> int:
    """
    Multiply two numbers.
    
    :param a: First number
    :param b: Second number
    
    Returns the product of two numbers
    """
    return a * b

# Step 2: Create Agent by inheriting AgentModule
class CalculatorExpert(AgentModule):
    # Use {{tool_schema}} placeholder - Engine auto-injects tool descriptions
    system_prompt = """You are a math expert. Use ReAct (Reasoning + Acting) pattern.

Available tools:
{{tool_schema}}

Format:
Task: [Goal]
Observation: [Tool results auto-filled here]

When calling tools, output:
Thought: Analyze the problem
Action: tool_name(param=value)

When done, output:
Thought: ...
Final Answer: The final answer

Rules:
- Execute one Action at a time
- Don't make up tools or parameters
- Output Final Answer when you have enough information
"""

    def gather(self, context: AgentContext) -> str:
        """
        Return current turn's prompt.
        History is managed by Memory module, no need to manually concatenate.
        """
        return f"""Current task: {context.task}

Observation: {context.last_obs}"""

# Step 3: Run
if __name__ == "__main__":
    # Register tools (ToolRegistry auto-parses docstrings)
    registry = ToolRegistry()
    registry.register(add)
    registry.register(multiply)

    # Setup LLM
    llm = OpenAICompatibleModel(
        model="Qwen/Qwen3-8B",
        base_url="https://api.siliconflow.cn/v1",
        api_key="your-api-key"
    )

    # Initialize Agent
    agent = CalculatorExpert(toolkit=registry, llm=llm)
    hook = RichConsoleHook()
    
    # Execute
    result = agent.run("Calculate 112390 * 23", max_steps=8, hooks=[hook])
    print(f"Result: {result}")
```

## Core Concepts

### AgentModule

The base class for defining Agent behavior. You must inherit from it and implement `gather()`.

```python
from qitos import AgentModule, AgentContext

class MyAgent(AgentModule):
    # Optional: Define system prompt at class level
    system_prompt = "You are a helpful assistant."
    
    def gather(self, context: AgentContext) -> str:
        """
        Required: Define what to say this turn.
        
        Args:
            context: Contains task, current_step, last_obs, trajectory, etc.
        
        Returns:
            Prompt string for this turn
        """
        return f"Task: {context.task}\nObservation: {context.last_obs}"
    
    def absorb(self, context: AgentContext, observations: List[Any], action_text: Optional[str] = None) -> None:
        """
        Optional: Process observations from tool execution.
        Default implementation stores observations in context.
        """
        super().absorb(context, observations, action_text)
        # Add custom logic here
    
    def get_system_prompt(self, context: Optional[AgentContext] = None) -> Optional[str]:
        """
        Optional: Return dynamic system prompt.
        Can access context for state-based prompts.
        """
        return self.system_prompt
```

### AgentContext

The single state container for all Agent data.

```python
from qitos import AgentContext

# Create context
ctx = AgentContext(
    task="Book a flight to Paris",
    max_steps=10,
    memory_window=5,
    # Custom metadata
    user_location="Beijing",
    preferences={"airline": "Air France"}
)

# Access properties
print(ctx.task)           # "Book a flight to Paris"
print(ctx.current_step)   # 0
print(ctx.trajectory)     # []
print(ctx.metadata)       # {"user_location": "Beijing", ...}

# Dot access for metadata
print(ctx.user_location)  # "Beijing"

# Add trajectory entry
ctx.add_entry("user", "Find flights")
ctx.add_entry("assistant", "Thought: I need to search...")
ctx.add_entry("action", {"name": "search", "args": {"query": "flights to Paris"}})

# Get history for LLM
messages = ctx.get_trajectory_for_llm(window=5)
# Returns: [{"role": "user", "content": "..."}, ...]

# Serialize
json_str = ctx.to_json()
ctx2 = AgentContext.from_json(json_str)
```

### ToolRegistry

Register and manage tools.

```python
from qitos import ToolRegistry

registry = ToolRegistry()

# Register function (auto-parses docstring and type hints)
def search(query: str, limit: int = 10) -> List[dict]:
    """Search for items.
    
    :param query: Search query string
    :param limit: Max results to return
    
    Returns list of matching items
    """
    return []

registry.register(search)

# Register with custom name
registry.register(search, name="web_search")

# Register with domain (for categorization)
registry.register(search, domain="web")

# List tools
print(registry.list_tools())           # ["search"]
print(registry.list_tools(domain="web"))  # ["search"]

# Get tool schema
schema = registry.get_schema("search")

# Call tool
result = registry.call("search", query="python", limit=5)

# Check if tool exists
if "search" in registry:
    print("Search tool available")
```

### Skill (Class-based Tools)

For complex stateful tools, use Skill class.

```python
from qitos.core.skill import Skill

class DatabaseQuery(Skill):
    """Query database with connection pooling."""
    
    def __init__(self, connection_string: str):
        super().__init__(name="db_query")
        self.connection_string = connection_string
        self._pool = None
    
    def run(self, sql: str, params: Optional[dict] = None) -> dict:
        """
        Execute SQL query.
        
        :param sql: SQL query string
        :param params: Query parameters
        
        Returns query results
        """
        # Implementation
        return {"status": "success", "rows": []}

# Register
from qitos import ToolRegistry
registry = ToolRegistry()
registry.register(DatabaseQuery("postgresql://..."))
```

### Model Adapters

```python
from qitos.models import OpenAIModel, OpenAICompatibleModel

# OpenAI
llm = OpenAIModel(
    model="gpt-4",
    api_key="sk-...",
    temperature=0.7,
    max_tokens=2048
)

# OpenAI-compatible (SiliconFlow, etc.)
llm = OpenAICompatibleModel(
    model="Qwen/Qwen3-8B",
    base_url="https://api.siliconflow.cn/v1",
    api_key="sk-..."
)

# Use
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
]
response = llm(messages)
```

### Hooks

Hooks provide observability into Agent execution.

```python
from qitos.core.hooks import Hook
from qitos.render.hooks import RichConsoleHook

# Built-in hooks
hook = RichConsoleHook()  # Visual output with Rich
agent.run(task, hooks=[hook])

# Custom hook
class MyHook(Hook):
    def on_step_start(self, context, agent):
        print(f"Step {context.current_step} started")
    
    def on_llm_response(self, context, agent, messages, raw_output, parsed_actions):
        print(f"LLM: {raw_output[:100]}...")
    
    def on_tool_end(self, context, agent, tool_calls, observations):
        for call in tool_calls:
            print(f"Tool: {call['tool']}")
    
    def on_step_end(self, context, agent):
        print(f"Step {context.current_step} ended")
    
    def on_execution_end(self, context, agent):
        print(f"Final: {context.final_result}")
    
    def on_perceive_start(self, context, agent):
        pass

agent.run(task, hooks=[MyHook()])
```

### Memory

Control how history is retrieved for LLM context.

```python
from qitos.memory import WindowMemory, UnlimitedMemory
from qitos.engine import ExecutionEngine

# Window memory (default): Keep last N steps
memory = WindowMemory(window_size=5)

# Unlimited memory: Keep all history
memory = UnlimitedMemory()

# Use with agent
engine = ExecutionEngine(agent=agent, memory=memory)
```

## Execution Patterns

### Pattern 1: Simple Run

```python
from qitos import run_agent

result = run_agent(
    agent=agent,
    task="Calculate 2+2",
    max_steps=5,
    hooks=[RichConsoleHook()]
)
```

### Pattern 2: Step-by-Step (Eager Execution)

```python
from qitos.core.context import AgentContext
from qitos.engine import ExecutionEngine

# Create context
context = AgentContext(task="Calculate 2+2", max_steps=5)

# Create engine
engine = ExecutionEngine(agent=agent)

# Execute step by step
for step in range(5):
    observations = engine.execute_step(context)
    print(f"Step {step}: {observations}")
    
    if context.final_result:
        break

print(f"Result: {context.final_result}")
```

### Pattern 3: Interactive Mode

```python
# Start interactive CLI
agent.run_interactive(
    max_steps=10,
    welcome_message="Welcome to My Agent!",
    prompt_text="Enter your task"
)
```

## Advanced Usage

### Custom Action Parser

```python
from qitos.engine.execution_engine import ActionParser

class MyParser(ActionParser):
    def _parse_text(self, text: str) -> List[Dict[str, Any]]:
        # Custom parsing logic
        actions = []
        # ... parse text ...
        return actions

# Use
from qitos.engine import run_agent
result = run_agent(agent, task, parser=MyParser())
```

### Custom Stopping Criteria

```python
def stop_on_success(context, response):
    """Stop when 'success' appears in response."""
    return "success" in str(response).lower()

result = run_agent(agent, task, stopping_criteria=stop_on_success)
```

### Sub-Agents

```python
# Create specialized sub-agents
researcher = ResearchAgent(toolkit=tools, llm=llm)
writer = WriterAgent(toolkit=tools, llm=llm)

# Register as tools to main agent
main_agent = AgentModule(
    toolkit=registry,
    llm=llm,
    sub_agents={
        "researcher": researcher,
        "writer": writer
    }
)

# LLM can now call: Action: researcher(task="find info about X")
```

### Error Handling

```python
from qitos.engine.execution_engine import ToolErrorHandler

# Configure error handling
error_handler = ToolErrorHandler(strategy="inject_error")
# Strategies: "raise", "inject_error", "skip"

engine = ExecutionEngine(
    agent=agent,
    error_handler=error_handler
)
```

## Built-in Skills

### File Operations

```python
from qitos.skills.file import ReadFile, WriteFile, ListFiles

registry = ToolRegistry()
registry.register(ReadFile(root_dir="/tmp"))
registry.register(WriteFile(root_dir="/tmp"))
registry.register(ListFiles(root_dir="/tmp"))
```

### Shell Commands

```python
from qitos.skills.shell import RunCommand

registry.register(RunCommand(
    timeout=30,
    cwd="/workspace",
    env={"PATH": "/usr/bin"}
))
```

### HTTP Requests

```python
from qitos.skills.web import HTTPGet, HTTPPost

registry.register(HTTPGet(
    headers={"Authorization": "Bearer token"},
    timeout=30
))

# Async usage
result = await registry.call("http_get", url="https://api.example.com/data")
```

## Best Practices

### 1. Docstring Format

Use Google/Sphinx style for automatic schema generation:

```python
def my_tool(param1: str, param2: int = 10) -> dict:
    """
    Short description here.
    
    Longer description if needed.
    
    :param param1: Description of param1
    :param param2: Description of param2 (default: 10)
    
    Returns description of return value
    """
    return {}
```

### 2. System Prompt Template

Use `{{tool_schema}}` placeholder for automatic tool injection:

```python
system_prompt = """You are an assistant.

Available tools:
{{tool_schema}}

When calling tools, use:
Action: tool_name(param=value)

When done, use:
Final Answer: Your answer
"""
```

### 3. Observation Handling

Return structured results from tools:

```python
def search(query: str) -> dict:
    try:
        results = do_search(query)
        return {
            "status": "success",
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
```

### 4. Debugging

Use hooks for debugging:

```python
class DebugHook(Hook):
    def on_llm_response(self, context, agent, messages, raw_output, parsed_actions):
        print(f"Messages sent to LLM:")
        for msg in messages:
            print(f"  {msg['role']}: {msg['content'][:100]}...")
        print(f"LLM output: {raw_output}")
        print(f"Parsed actions: {parsed_actions}")
```

### 5. State Management

Use metadata for custom state:

```python
def gather(self, context: AgentContext) -> str:
    # Initialize on first call
    if "search_count" not in context.metadata:
        context.metadata["search_count"] = 0
    
    # Update state
    context.metadata["search_count"] += 1
    
    return f"Task: {context.task}"
```

## Complete Example

```python
from typing import List, Any, Optional
from qitos import AgentModule, AgentContext, ToolRegistry
from qitos.models import OpenAICompatibleModel
from qitos.render import RichConsoleHook
from qitos.core.hooks import Hook

# ============ Tools ============
def search_web(query: str, limit: int = 5) -> List[dict]:
    """Search the web for information.
    
    :param query: Search query
    :param limit: Max results (default: 5)
    
    Returns list of search results
    """
    # Mock implementation
    return [
        {"title": f"Result {i}", "url": f"http://example.com/{i}"}
        for i in range(limit)
    ]

def fetch_page(url: str) -> str:
    """Fetch webpage content.
    
    :param url: Page URL to fetch
    
    Returns page content as text
    """
    return f"Content of {url}"

# ============ Custom Hook ============
class ProgressHook(Hook):
    def on_step_start(self, context, agent):
        print(f"\n[Step {context.current_step + 1}] Starting...")
    
    def on_llm_response(self, context, agent, messages, raw_output, parsed_actions):
        action_names = [a.get("name") for a in parsed_actions if a.get("name")]
        if action_names:
            print(f"  Actions: {', '.join(action_names)}")
    
    def on_tool_end(self, context, agent, tool_calls, observations):
        for obs in observations:
            if isinstance(obs, dict) and obs.get("status") == "success":
                print(f"  ✓ Success")
    
    def on_execution_end(self, context, agent):
        print(f"\n✓ Done: {context.final_result[:100]}...")
    
    def on_step_end(self, context, agent):
        pass
    
    def on_perceive_start(self, context, agent):
        pass

# ============ Agent ============
class ResearchAgent(AgentModule):
    system_prompt = """You are a research assistant. Gather information and summarize.

Available tools:
{{tool_schema}}

Format:
Thought: Your reasoning
Action: tool_name(param=value)

When you have enough information:
Thought: I have gathered enough information
Final Answer: Your comprehensive summary
"""

    def gather(self, context: AgentContext) -> str:
        return f"""Research task: {context.task}

Previous observations: {context.last_obs}

What would you like to do next?"""

# ============ Main ============
if __name__ == "__main__":
    # Setup tools
    registry = ToolRegistry()
    registry.register(search_web)
    registry.register(fetch_page)
    
    # Setup LLM
    llm = OpenAICompatibleModel(
        model="Qwen/Qwen3-8B",
        base_url="https://api.siliconflow.cn/v1",
        api_key="your-api-key"
    )
    
    # Create agent
    agent = ResearchAgent(toolkit=registry, llm=llm)
    
    # Run with hooks
    result = agent.run(
        task="Research Python async programming best practices",
        max_steps=8,
        hooks=[ProgressHook(), RichConsoleHook()]
    )
    
    print(f"\nFinal Result:\n{result}")
```

## API Reference

See [arch.md](./arch.md) for complete module interfaces.

## Troubleshooting

### "No LLM configured"

```python
# Make sure to set agent.llm
agent = MyAgent(toolkit=registry, llm=my_llm)
# or
agent.llm = my_llm
```

### "Tool not found"

```python
# Check tool registration
print(registry.list_tools())  # Verify tool is registered

# Check tool name in Action
# Correct: Action: search_web(query="python")
# Wrong:  Action: search-web(query="python")
```

### Parser not recognizing actions

```python
# Ensure correct format in system prompt
# Correct formats:
# Action: tool_name(arg=value)
# Action: {"name": "tool_name", "args": {"arg": "value"}}
# Action 1: tool_name
```

### Memory issues

```python
# Increase window size
context = AgentContext(task, memory_window=10)

# Or use unlimited memory
from qitos.memory import UnlimitedMemory
engine = ExecutionEngine(agent=agent, memory=UnlimitedMemory())
```

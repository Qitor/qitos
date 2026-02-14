# QitOS Framework Architecture

> A state-driven Agent framework designed for developer happiness.

## Core Philosophy

- **Explicit over Implicit**: All state changes must be traceable and debuggable
- **State is Everything**: AgentContext is the single source of truth
- **Debugging is Development**: Step-by-step execution with time-travel capability
- **Interactive CLI**: Rich rendering and Typer command-line support

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Developer Interface                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  AgentModule │  │   skill()   │  │  run_agent() │  │   RichConsoleHook   │ │
│  │  (inherit)   │  │ (decorator) │  │  (function)  │  │    (render hook)    │ │
│  └──────┬──────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────┼───────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Execution Layer                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      ExecutionEngine                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │   │
│  │  │   execute() │  │execute_step()│  │_build_messages│ │is_finished()│ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │                     ActionParser                               │ │   │
│  │  │  - parse()          - _extract_json_actions()                  │ │   │
│  │  │  - _extract_simple_actions()  - _extract_numbered_actions()    │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Core Components                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │   AgentContext  │  │   ToolRegistry  │  │         Hook System         │ │
│  │   (state container)│  │  (tool management)│  │  - on_step_start()        │ │
│  │  - task         │  │  - register()   │  │  - on_llm_response()        │ │
│  │  - trajectory   │  │  - call()       │  │  - on_tool_end()            │ │
│  │  - metadata     │  │  - get_spec()   │  │  - on_step_end()            │ │
│  │  - mutation_log │  │  - list_tools() │  │  - on_execution_end()       │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Extension Layer                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │  Memory System  │  │  Model Adapters │  │      Built-in Skills        │ │
│  │  - BaseMemory   │  │  - Model        │  │  - ReadFile / WriteFile     │ │
│  │  - WindowMemory │  │  - OpenAIModel  │  │  - ListFiles                │ │
│  │  - UnlimitedMemory│  │  - OpenAICompatibleModel│  - RunCommand        │ │
│  │                 │  │  - AzureOpenAIModel│  │  - HTTPGet / HTTPPost      │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Interfaces

### 1. AgentModule (`qitos.core.agent`)

Abstract base class for defining Agent behavior.

```python
class AgentModule(ABC):
    # Class-level system prompt (can use {{tool_schema}} placeholder)
    system_prompt: Optional[str] = None
    
    def __init__(
        self,
        toolkit: Optional[ToolRegistry] = None,
        llm: Optional[Callable] = None,
        system_prompt: Optional[str] = None,
        sub_agents: Optional[Dict[str, 'AgentModule']] = None,
        memory: Optional['BaseMemory'] = None
    )
    
    # [Required] Define what to say this turn
    @abstractmethod
    def gather(self, context: AgentContext) -> str
    
    # [Optional] Get dynamic system prompt
    def get_system_prompt(self, context: Optional[AgentContext] = None) -> Optional[str]
    
    # [Optional] Absorb observations from tool execution
    def absorb(self, context: AgentContext, observations: List[Any], action_text: Optional[str] = None) -> None
    
    # Run the agent
    def run(self, task: str, max_steps: int = 10, hooks: Optional[List['Hook']] = None, **kwargs) -> str
    
    # Interactive CLI mode
    def run_interactive(self, max_steps: int = 10, welcome_message: Optional[str] = None, prompt_text: str = "Enter your task") -> None
    
    # Add tool dynamically
    def add_tool(self, func: Callable, name: Optional[str] = None)
    
    # List all available tools
    def list_tools(self) -> List[str]
```

### 2. AgentContext (`qitos.core.context`)

The single source of truth for all Agent state.

```python
class AgentContext(OrderedDict):
    def __init__(
        self,
        task: str,
        max_steps: int = 10,
        memory_window: int = 5,
        **kwargs
    )
    
    # Core properties
    @property
    def task(self) -> str                    # Original task
    @property
    def current_step(self) -> int            # Current step (0-indexed)
    @property
    def trajectory(self) -> List[TrajectoryEntry]  # Structured interaction history
    @property
    def metadata(self) -> Dict[str, Any]     # User-defined metadata
    @property
    def mutation_log(self) -> List[MutationLog]    # Auto-recorded state changes
    @property
    def memory_window(self) -> int           # Memory window size
    @property
    def final_result(self) -> Optional[str]  # Final answer
    @property
    def last_obs(self) -> List[Dict]         # Last observation results
    
    # Core methods
    def add_entry(self, role: str, content: Any, metadata: Optional[Dict[str, Any]] = None) -> TrajectoryEntry
    def get_history(self, roles: Optional[List[str]] = None, window: Optional[int] = None) -> List[TrajectoryEntry]
    def get_trajectory_for_llm(self, window: Optional[int] = None) -> List[Dict[str, Any]]
    def to_json(self, indent: int = 2) -> str
    @classmethod
    def from_json(cls, json_str: str) -> 'AgentContext'
    def create_snapshot(self) -> Dict[str, Any]
```

### 3. ToolRegistry (`qitos.core.skill`)

Central registry for managing tools/skills.

```python
class ToolRegistry:
    def __init__(self, skills: Optional[List[Callable]] = None)
    
    # Register a tool
    def register(self, func: Callable, name: Optional[str] = None, domain: Optional[str] = None) -> 'ToolRegistry'
    
    # Unregister a tool
    def unregister(self, name: str) -> bool
    
    # Get tool
    def get(self, name: str) -> Optional[Skill]
    
    # List tools
    def list_tools(self, domain: Optional[str] = None) -> List[str]
    def list_all(self) -> List[Skill]
    
    # Get schemas
    def get_schema(self, name: str) -> Optional[Dict[str, Any]]
    def get_all_schemas(self) -> List[Dict[str, Any]]
    def get_schemas(self, domain: Optional[str] = None) -> Dict[str, Any]
    def get_tool_descriptions(self) -> str
    
    # Call tool
    def call(self, name: str, **kwargs) -> Any
```

### 4. Skill (`qitos.core.skill`)

Abstract base class for defining tools.

```python
class Skill(ABC):
    def __init__(self, name: str = None, **kwargs)
    
    @property
    def name(self) -> str
    
    @property
    def domain(self) -> str
    
    # [Required] Execute skill logic
    @abstractmethod
    def run(self, **kwargs) -> Any
    
    # Get OpenAI-compatible tool specification
    def get_spec(self) -> Dict[str, Any]
    
    # Get compatible ToolSchema
    @property
    def schema(self) -> 'ToolSchema'
```

### 5. ExecutionEngine (`qitos.engine.execution_engine`)

Core execution engine for running Agents.

```python
class ExecutionEngine:
    def __init__(
        self,
        agent: 'AgentModule',
        hooks: Optional[List[Hook]] = None,
        error_handler: Optional[ToolErrorHandler] = None,
        observation_window: int = 5,
        parser: Optional[ActionParser] = None,
        memory: Optional[BaseMemory] = None,
        stopping_criteria: Optional[Callable[[AgentContext, Any], bool]] = None
    )
    
    # Check if execution should finish
    def is_finished(self, context: AgentContext, response: Any) -> bool
    
    # Execute single step (Eager Execution)
    def execute_step(self, context: AgentContext) -> List[Any]
    
    # Execute full workflow
    def execute(self, context: AgentContext) -> str
    
    # Get performance statistics
    def get_performance_stats(self) -> Dict[str, Any]

# Convenience function
def run_agent(
    agent: 'AgentModule',
    task: str,
    max_steps: int = 10,
    hooks: Optional[List[Hook]] = None,
    error_strategy: str = "inject_error",
    parser: Optional[ActionParser] = None,
    memory: Optional[BaseMemory] = None,
    stopping_criteria: Optional[Callable[[AgentContext, Any], bool]] = None,
    **kwargs
) -> str
```

### 6. Hook System (`qitos.core.hooks`)

Lifecycle hooks for observability and extension.

```python
class Hook(ABC):
    @abstractmethod
    def on_step_start(self, context: 'AgentContext', agent: 'AgentModule') -> None
    
    @abstractmethod
    def on_perceive_start(self, context: 'AgentContext', agent: 'AgentModule') -> None
    
    @abstractmethod
    def on_llm_response(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        messages: List[Dict[str, str]],
        raw_output: str,
        parsed_actions: List[Dict[str, Any]]
    ) -> None
    
    @abstractmethod
    def on_tool_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        tool_calls: List[Dict[str, Any]],
        observations: List[Any]
    ) -> None
    
    @abstractmethod
    def on_step_end(self, context: 'AgentContext', agent: 'AgentModule') -> None
    
    @abstractmethod
    def on_execution_end(self, context: 'AgentContext', agent: 'AgentModule') -> None
```

Built-in hooks:
- `LoggingHook`: Record execution trajectory
- `PerformanceHook`: Measure execution time
- `InspectorHook`: Integration with Inspector visualization
- `ConditionalHook`: Conditional breakpoints
- `RichConsoleHook`: Rich console rendering

### 7. Memory System (`qitos.memory`)

Memory management for conversation history.

```python
class BaseMemory(ABC):
    @abstractmethod
    def retrieve(self, context: 'AgentContext', **kwargs) -> List[Dict[str, Any]]

class WindowMemory(BaseMemory):
    def __init__(self, window_size: int = 5)
    def retrieve(self, context: 'AgentContext', **kwargs) -> List[Dict[str, Any]]

class UnlimitedMemory(WindowMemory):
    """Keep all history."""
    def __init__(self)
```

### 8. Model Adapters (`qitos.models`)

Unified LLM calling interface.

```python
class Model(ABC):
    def __init__(
        self,
        model: str = "default",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    )
    
    @abstractmethod
    def _call_api(self, messages: List[Dict[str, str]]) -> str
    
    def __call__(self, messages: List[Dict[str, str]]) -> str

# Implementations
class OpenAIModel(Model)
class OpenAICompatibleModel(Model)  # For SiliconFlow, etc.
class AzureOpenAIModel(OpenAICompatibleModel)
```

### 9. ActionParser (`qitos.engine.execution_engine`)

Parse LLM responses into structured actions.

```python
class ActionParser:
    def parse(self, response: Any, available_tools: Optional[List[str]] = None) -> List[Dict[str, Any]]
    # Returns: [{"name": str, "args": dict, "error": Optional[str]}]

class DefaultActionParser(ActionParser)
class ReActActionParser(DefaultActionParser)
```

## Execution Flow

```
┌─────────────┐
│   Start     │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│  AgentContext(task) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐     ┌─────────────────────┐
│   execute_step()    │◄────│   Step < max_steps  │
└──────────┬──────────┘     └─────────────────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
┌─────────┐  ┌─────────────┐
│on_step_start│ │ agent.gather()│
└─────────┘  └──────┬──────┘
                    │
                    ▼
           ┌────────────────┐
           │ context.add_entry│
           │   ("user", ...)  │
           └────────┬───────┘
                    │
                    ▼
           ┌────────────────┐
           │ _build_messages()│
           └────────┬───────┘
                    │
                    ▼
           ┌────────────────┐
           │   agent.llm()   │
           └────────┬───────┘
                    │
                    ▼
           ┌────────────────┐
           │  is_finished()? │──Yes──► Final Answer
           └────────┬───────┘
                    │ No
                    ▼
           ┌────────────────┐
           │  parser.parse() │
           └────────┬───────┘
                    │
                    ▼
           ┌────────────────┐
           │context.add_entry│
           │("assistant", ...)│
           └────────┬───────┘
                    │
                    ▼
           ┌────────────────┐
           │   Execute Tools │
           │  toolkit.call() │
           └────────┬───────┘
                    │
                    ▼
           ┌────────────────┐
           │   on_tool_end() │
           └────────┬───────┘
                    │
                    ▼
           ┌────────────────┐
           │  agent.absorb() │
           │(observations)   │
           └────────┬───────┘
                    │
                    ▼
           ┌────────────────┐
           │   on_step_end() │
           └────────┬───────┘
                    │
                    ▼
           ┌────────────────┐
           │  current_step++ │
           └────────────────┘
```

## Directory Structure

```
qitos/
├── __init__.py           # Main exports
├── core/                 # Core components
│   ├── __init__.py
│   ├── agent.py          # AgentModule base class
│   ├── context.py        # AgentContext state container
│   ├── skill.py          # Skill & ToolRegistry
│   └── hooks.py          # Hook system
├── engine/               # Execution engine
│   ├── __init__.py
│   └── execution_engine.py  # ExecutionEngine & parsers
├── memory/               # Memory management
│   ├── __init__.py
│   ├── base.py           # BaseMemory
│   └── window.py         # WindowMemory & UnlimitedMemory
├── models/               # LLM adapters
│   ├── __init__.py
│   ├── base.py           # Model base class
│   ├── openai.py         # OpenAI & compatible models
│   └── local.py          # Local model support
├── render/               # CLI rendering
│   ├── __init__.py
│   ├── cli_render.py     # RichRender utilities
│   └── hooks.py          # RichConsoleHook
├── skills/               # Built-in skills
│   ├── __init__.py
│   ├── file.py           # File operations
│   ├── shell.py          # Shell commands
│   └── web.py            # HTTP requests
└── cli/                  # CLI commands
    ├── __init__.py
    ├── main.py
    ├── init.py
    ├── play.py
    └── replay.py
```

## Key Design Decisions

1. **AgentContext as OrderedDict**: Enables both dot access (`ctx.task`) and dict access (`ctx["task"]`)

2. **Trajectory-based Memory**: All interactions are recorded as structured trajectory entries with roles (user/assistant/action/observation)

3. **Eager Execution**: `execute_step()` allows step-by-step execution for debugging

4. **Pluggable Parser**: ActionParser can be customized for different LLM output formats

5. **Hook System**: Six lifecycle hooks provide full observability without modifying core logic

6. **Skill Inheritance**: Tools can be defined as classes inheriting from Skill for complex stateful operations

7. **{{tool_schema}} Placeholder**: System prompts can include `{{tool_schema}}` which is automatically replaced with tool definitions

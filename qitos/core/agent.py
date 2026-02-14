"""
AgentModule: Minimal user interface

v6.0 Precise refactoring version.

Core methods:
- gather(context): Context -> str (what to say this turn)
- absorb(context, observations): Absorb observation results -> default store to context
- get_system_prompt(context): Dynamically get system prompt

Responsibility separation:
- Agent: Define "what to say" (gather), "what to process" (absorb), "system prompt" (get_system_prompt)
- ExecutionEngine: Handle execution control flow and message orchestration (auto-inject {{tool_schema}} placeholder)
- Memory: Handle history message management
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from .context import AgentContext
from .skill import ToolRegistry

if TYPE_CHECKING:
    from ..memory.base import BaseMemory

DEFAULT_REACT_PROMPT = """You are an intelligent assistant using ReAct (Reasoning + Acting) mode.

Available tools:
{{tool_schema}}

Information format:
Task: [Goal]
Observation: [Tool results will be auto-filled here]

When calling tools, output:

Thought: Analyze the current problem and clarify next steps.
Action: tool_name(param_name=param_value)

If no tool needed, output directly:
Thought: ...
Final Answer: Give a clear, accurate, complete final answer based on reasoning.

Notes:
- Execute one Action at a time.
- Don't make up tools or parameters that don't exist.
- If you have enough information, output Final Answer directly without more tool calls.
"""


class AgentModule(ABC):
    """
    Agent module abstract base class
    
    Users need to inherit from this class and implement the `gather` method.
    
    Core features:
    - Class attribute support: Can define system_prompt at class level
    - Dynamic prompt: get_system_prompt(context) supports state-based dynamic prompts
    - Auto tool injection: ExecutionEngine auto-replaces {{tool_schema}} placeholder
    
    Responsibilities:
    - gather: Define what to say this turn (return Prompt string)
    - absorb: Optional, define how to process tool observation results
    - get_system_prompt: Optional, dynamically get system prompt
    """
    
    system_prompt: Optional[str] = None
    
    def __init__(
        self,
        toolkit: Optional[ToolRegistry] = None,
        llm: Optional[Callable] = None,
        system_prompt: Optional[str] = None,
        sub_agents: Optional[Dict[str, 'AgentModule']] = None,
        memory: Optional['BaseMemory'] = None,
        skills: Optional[List[Any]] = None
    ):
        """
        Initialize AgentModule
        
        Simplified initialization with skills support:
        
        Args:
            toolkit: Tool registry (optional if skills provided)
            llm: LLM callable function
            system_prompt: System prompt (higher priority than class attribute)
            sub_agents: Sub-agent dictionary
            memory: Memory module
            skills: Skill instances list (e.g., [EditorSkill(), FileSkill()])
                   All @skill decorated methods will be auto-registered
        
        Example:
            agent = MyAgent(
                llm=my_llm,
                skills=[EditorSkill(workspace_root="."), FileSkill()]
            )
            # All editor and file tools are now available!
        """
        self.toolkit = toolkit or ToolRegistry()
        self.llm = llm
        
        if system_prompt is not None:
            self.system_prompt = system_prompt
        elif self.__class__.system_prompt is not None:
            self.system_prompt = self.__class__.system_prompt
        else:
            self.system_prompt = None
        
        self.memory = memory
        
        if sub_agents:
            for name, agent in sub_agents.items():
                self._register_sub_agent(name, agent)
        
        if skills:
            for skill in skills:
                self.toolkit.include(skill)
    
    def _register_sub_agent(self, name: str, agent: 'AgentModule'):
        """Register sub-agent as a tool"""
        def wrapper(**kwargs) -> str:
            task = kwargs.get("task") or kwargs.get("instruction")
            if not task:
                return "Error: sub_agent requires 'task' or 'instruction'"
            max_steps = kwargs.get("max_steps", 3)
            return agent(task, max_steps=max_steps)
        
        wrapper.__name__ = name
        wrapper.__doc__ = f"SubAgent: {agent.__class__.__name__}"
        self.toolkit.register(wrapper, name=name)
    
    def get_system_prompt(self) -> str:
        prompt = self.system_prompt or ""
        
        # Auto-detect and inject {{tool_schema}}
        if "{{tool_schema}}" in prompt and self.toolkit:
            schemas_str = self.toolkit.get_schemas_as_str() 
            prompt = prompt.replace("{{tool_schema}}", schemas_str)
            
        return prompt

    @abstractmethod
    def gather(self, context: AgentContext) -> str:
        """
        [User must implement] Collect what to say this turn
        
        Return the Prompt string to send to LLM this step.
        History messages are injected by Memory module.
        system_prompt is handled separately by Engine, should not be included in return value.
        
        Args:
            context: AgentContext instance
            
        Returns:
            Prompt string
        
        Example:
            def gather(self, context):
                return f"User request: {context.task}"
        """
        pass
    
    def get_system_prompt(self, context: Optional[AgentContext] = None) -> Optional[str]:
        """
        [Optional override] Get system prompt
        
        Supports state-based dynamic prompts.
        If returns None, Engine uses default ReAct template.
        
        Args:
            context: AgentContext instance (may be None)
            
        Returns:
            System prompt string, or None if no prompt
        """
        return self.system_prompt
    
    def absorb(
        self,
        context: AgentContext,
        observations: List[Any],
        action_text: Optional[str] = None
    ) -> None:
        """
        [Optional default implementation] Absorb observation results
        
        Default behavior:
        1. Record tool execution results (Observation role)
        2. Update context.last_obs to this observation result
        
        Args:
            context: AgentContext instance
            observations: Tool call result list
            action_text: LLM raw response
        """
        if observations:
            # Update last_obs attribute
            context.last_obs = observations
            
            # Record to trajectory
            for obs in observations:
                context.add_entry("observation", obs)
    
    def __call__(self, task: str, max_steps: int = 10, **kwargs) -> str:
        """
        Make AgentModule callable
        
        Args:
            task: Initial task description
            max_steps: Max step limit
            **kwargs: Extra params passed to run_agent
            
        Returns:
            Final answer
        """
        from ..engine import run_agent
        return run_agent(agent=self, task=task, max_steps=max_steps, **kwargs)
    
    def run(
        self,
        task: str,
        max_steps: int = 10,
        hooks: Optional[List['Hook']] = None,
        **kwargs
    ) -> str:
        """
        Run Agent to execute task
        
        Args:
            task: Task description
            max_steps: Max step limit
            hooks: Hook list (e.g. RichConsoleHook)
            **kwargs: Other params
            
        Returns:
            Final answer
        """
        from ..engine import ExecutionEngine
        from ..core.context import AgentContext
        from ..core.hooks import CompositeHook
        
        context = AgentContext(task=task, max_steps=max_steps)
        
        if hooks:
            composite = CompositeHook(hooks) if len(hooks) > 1 else (hooks[0] if hooks else None)
        else:
            composite = None
        
        engine = ExecutionEngine(
            agent=self,
            hooks=[composite] if composite else None,
            **kwargs
        )
        
        return engine.execute(context)
    
    def run_interactive(
        self,
        max_steps: int = 10,
        welcome_message: Optional[str] = None,
        prompt_text: str = "Enter your task"
    ):
        """
        Start interactive command line interface
        
        Uses typer for interactive input, Rich for rendering output.
        
        Args:
            max_steps: Max step limit
            welcome_message: Custom welcome message
            prompt_text: Input prompt text
            
        Example:
            agent = MyAgent()
            agent.run_interactive()
        """
        try:
            import typer
            from ..render.hooks import RichConsoleHook
            from ..render.cli_render import RichRender, console
            
            app = typer.Typer(
                help="QitOS Agent Interactive CLI",
                add_completion=False
            )
            
            @app.command()
            def chat(
                task: str = typer.Option(
                    ...,
                    "-t", "--task",
                    prompt=prompt_text,
                    help="Task description to execute"
                ),
                steps: int = typer.Option(
                    max_steps,
                    "-s", "--steps",
                    help="Max execution steps"
                ),
                verbose: bool = typer.Option(
                    False,
                    "-v", "--verbose",
                    help="Show detailed execution process"
                ),
                quiet: bool = typer.Option(
                    False,
                    "-q", "--quiet",
                    help="Quiet mode, only show final answer"
                )
            ):
                """
                Execute Agent task
                """
                from ..render.hooks import VerboseRichConsoleHook, SimpleRichConsoleHook
                from ..render.cli_render import RichRender
                
                if quiet:
                    hooks = None
                elif verbose:
                    hooks = [VerboseRichConsoleHook()]
                else:
                    hooks = [RichConsoleHook()]
                
                try:
                    result = self.run(task=task, max_steps=steps, hooks=hooks)
                except KeyboardInterrupt:
                    RichRender.print_info("User interrupted execution")
                    raise typer.Exit(code=130)
                except Exception as e:
                    RichRender.print_error(f"Execution error: {str(e)}")
                    raise typer.Exit(code=1)
            
            @app.command()
            def tools():
                """
                List all available tools
                """
                from ..render.cli_render import RichRender, console
                
                tools = self.list_tools()
                if tools:
                    RichRender.print_info(f"Available tools ({len(tools)}):")
                    for tool in tools:
                        console.print(f"  • {tool}")
                else:
                    RichRender.print_info("No available tools")
                
                console.print()
                console.print(f"[bold]Tool count:[/bold] {len(tools)}")
            
            @app.command()
            def info():
                """
                Show Agent info
                """
                from ..render.cli_render import RichRender, console, Panel
                from rich.text import Text
                
                info_text = Text()
                info_text.append("Agent type: ", style="dim")
                info_text.append(self.__class__.__name__, style="bold cyan")
                info_text.append("\n")
                info_text.append("Tool count: ", style="dim")
                info_text.append(str(len(self.toolkit)), style="bold cyan")
                info_text.append("\n")
                
                system_prompt = self.get_system_prompt()
                if system_prompt:
                    info_text.append("System prompt: ", style="dim")
                    info_text.append(f"{system_prompt[:50]}...", style="cyan")
                
                panel = Panel(
                    info_text,
                    title="[bold]Agent Info[/bold]",
                    subtitle="[dim]QitOS Framework[/dim]",
                    box=ROUNDED
                )
                console.print(panel)
            
            @app.command()
            def exit():
                """
                Exit interactive mode
                """
                RichRender.print_info("Goodbye!")
                raise typer.Exit()
            
            def main():
                """Main entry, show welcome message"""
                from rich.text import Text
                from rich.panel import Panel
                from rich.box import DOUBLE
                
                if welcome_message:
                    console.print(welcome_message)
                else:
                    title = Text("🧘 QitOS Agent", style="bold magenta")
                    subtitle = Text("Interactive CLI", style="dim")
                    
                    panel = Panel(
                        title,
                        title="[bold]QitOS Framework v3.1[/bold]",
                        subtitle=subtitle,
                        box=DOUBLE,
                        style="magenta",
                        expand=True
                    )
                    console.print(panel)
                    
                    console.print("\n[bold]Available commands:[/bold]")
                    console.print("  • [cyan]chat[/cyan] - Execute task")
                    console.print("  • [cyan]tools[/cyan] - List available tools")
                    console.print("  • [cyan]info[/cyan] - Show Agent info")
                    console.print("  • [cyan]exit[/cyan] - Exit")
                    
                    console.print("\n[bold]Usage:[/bold]")
                    console.print("  • Run [cyan]qitos chat --task \"your task\"[/cyan] to execute")
                    console.print("  • Add [cyan]-v[/cyan] for verbose execution")
                    console.print("  • Add [cyan]-q[/cyan] for quiet mode")
                
                console.print()
            
            main()
            app()
            
        except ImportError as e:
            raise ImportError(
                "typer and rich libraries required for interactive mode.\n"
                "Please run: pip install typer rich"
            )
    
    def add_tool(self, func: Callable, name: Optional[str] = None):
        """Dynamically add tool"""
        self.toolkit.register(func, name=name)
    
    def list_tools(self) -> List[str]:
        """List all available tools"""
        return self.toolkit.list_tools()
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(tools={len(self.toolkit)})"


def create_react_agent(
    toolkit: Optional[ToolRegistry] = None,
    llm: Optional[Callable] = None,
    system_prompt: Optional[str] = None,
    memory: Optional['BaseMemory'] = None
) -> AgentModule:
    """
    Factory function: Create ReAct style Agent
    
    ReAct = Reasoning + Acting
    
    If system_prompt not provided, uses default template with {{tool_schema}}.
    
    Args:
        toolkit: Tool registry
        llm: LLM callable function
        system_prompt: System prompt (optional, uses default template if None)
        memory: Memory module
        
    Returns:
        Configured AgentModule instance
    """
    prompt = system_prompt if system_prompt is not None else DEFAULT_REACT_PROMPT
    
    class ReActAgent(AgentModule):
        """ReAct style Agent"""
        
        system_prompt: Optional[str] = prompt
        
        def gather(self, context: AgentContext) -> str:
            """
            gather only needs to return current incremental task.
            History (Memory) is auto-orchestrated by Engine, no manual concatenation needed.
            """
            return f"""Current task: {context.task}

Observation: {context.last_obs}"""

    
    return ReActAgent(
        toolkit=toolkit,
        llm=llm,
        system_prompt=prompt,
        memory=memory
    )
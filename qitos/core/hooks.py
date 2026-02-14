"""
Hooks System: Observability and Extension

Defines AgentHook base class, inserts key hooks into ExecutionEngine execution loop.

Six key hooks:
- on_step_start: When step starts
- on_llm_response: After LLM response parsed, before absorb (can extract Thought/Action)
- on_tool_end: After tool execution completed
- on_step_end: After update_context completed
- on_execution_end: When entire execution ends
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from ..core.context import AgentContext
    from ..core.agent import AgentModule


class Hook(ABC):
    """
    Agent lifecycle hook base class
    
    Users can inherit from this class to implement custom hooks for:
    - Debugging and logging: Record complete execution trajectory
    - Monitoring and alerting: Detect abnormal patterns
    - Performance analysis: Measure latency
    - Breakpoint debugging: Conditional pause
    - UI rendering: Rich console output
    
    All hook methods are optional - you only need to implement the ones you need.
    
    Example:
        class DebugHook(Hook):
            def on_step_start(self, context, agent):
                print(f"[Step {context.current_step}] Starting execution")
            
            def on_step_end(self, context, agent):
                print(f"[Step {context.current_step}] Completed, mutations: {len(context.mutation_log)}")
    """
    
    def on_step_start(
        self,
        context: 'AgentContext',
        agent: 'AgentModule'
    ) -> None:
        """Triggered when step starts"""
        pass
    
    def on_llm_response(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        messages: List[Dict[str, str]],
        raw_output: str,
        parsed_actions: List[Dict[str, Any]]
    ) -> None:
        """
        Triggered after LLM response parsed, before absorb
        
        Can be used to extract and render LLM's Thought/Action.
        
        Args:
            context: AgentContext instance
            agent: AgentModule instance
            messages: Message list sent to LLM
            raw_output: LLM raw output
            parsed_actions: Parsed action list
        """
        pass
    
    def on_tool_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        tool_calls: List[Dict[str, Any]],
        observations: List[Any]
    ) -> None:
        """Triggered after tool execution completed and observations obtained"""
        pass
    
    def on_step_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule'
    ) -> None:
        """Triggered after update_context completed"""
        pass
    
    def on_execution_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule'
    ) -> None:
        """Triggered when entire execution ends"""
        pass


class CompositeHook(Hook):
    """
    Combine multiple hooks container
    
    Supports batch execution of multiple hooks.
    
    Example:
        hooks = CompositeHook([
            LoggingHook(),
            PerformanceHook(),
            MyCustomHook()
        ])
    """
    
    def __init__(self, hooks: List[Hook]):
        """
        Initialize composite hook
        
        Args:
            hooks: Hook instance list
        """
        self.hooks = hooks
    
    def on_step_start(self, context: 'AgentContext', agent: 'AgentModule'):
        for hook in self.hooks:
            hook.on_step_start(context, agent)
    
    def on_llm_response(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        messages: List[Dict[str, str]],
        raw_output: str,
        parsed_actions: List[Dict[str, Any]]
    ):
        for hook in self.hooks:
            hook.on_llm_response(context, agent, messages, raw_output, parsed_actions)
    
    def on_tool_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        tool_calls: List[Dict[str, Any]],
        observations: List[Any]
    ):
        for hook in self.hooks:
            hook.on_tool_end(context, agent, tool_calls, observations)
    
    def on_step_end(self, context: 'AgentContext', agent: 'AgentModule'):
        for hook in self.hooks:
            hook.on_step_end(context, agent)
    
    def on_execution_end(self, context: 'AgentContext', agent: 'AgentModule'):
        for hook in self.hooks:
            hook.on_execution_end(context, agent)
    
    def add_hook(self, hook: Hook):
        """Dynamically add hook"""
        self.hooks.append(hook)
    
    def remove_hook(self, hook_type: type) -> bool:
        """Remove hook of specified type"""
        for i, hook in enumerate(self.hooks):
            if isinstance(hook, hook_type):
                self.hooks.pop(i)
                return True
        return False
    
    def __len__(self) -> int:
        return len(self.hooks)


class LoggingHook(Hook):
    """
    Built-in logging hook
    
    Records complete execution trajectory, suitable for debugging and auditing.
    
    Example:
        hook = LoggingHook(logger=print)  # Use print
        hook = LoggingHook(logger=my_logger.info)  # Use custom logger
    """
    
    def __init__(
        self,
        logger: Optional[Callable] = None,
        verbose: bool = False
    ):
        """
        Initialize logging hook
        
        Args:
            logger: Logger function, defaults to print
            verbose: Verbose mode, output more debug info
        """
        self.logger = logger or print
        self.verbose = verbose
    
    def on_step_start(self, context: 'AgentContext', agent: 'AgentModule'):
        task_preview = context.task[:50] + "..." if len(context.task) > 50 else context.task
        self.logger(f"[Step {context.current_step}] 🚀 Starting execution")
        self.logger(f"[Step {context.current_step}] Task: {task_preview}")
    
    def on_llm_response(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        messages: List[Dict[str, str]],
        raw_output: str,
        parsed_actions: List[Dict[str, Any]]
    ):
        preview = raw_output[:100] + "..." if len(raw_output) > 100 else raw_output
        self.logger(f"[Step {context.current_step}] 🤖 LLM output: {preview}")
        
        if parsed_actions:
            action_names = [a.get("name", "unknown") for a in parsed_actions]
            self.logger(f"[Step {context.current_step}] 📌 Parsed actions: {', '.join(action_names)}")
    
    def on_tool_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        tool_calls: List[Dict[str, Any]],
        observations: List[Any]
    ):
        if tool_calls:
            tool_names = [call.get("tool", "unknown") for call in tool_calls]
            self.logger(f"[Step {context.current_step}] 🔧 Tool calls: {', '.join(tool_names)}")
            self.logger(f"[Step {context.current_step}] 📊 Result count: {len(observations)}")
            
            if self.verbose:
                for i, obs in enumerate(observations):
                    obs_preview = str(obs)[:200] + "..." if len(str(obs)) > 200 else str(obs)
                    self.logger(f"  [Obs {i+1}] {obs_preview}")
    
    def on_step_end(self, context: 'AgentContext', agent: 'AgentModule'):
        mutation_count = len(context.mutation_log)
        self.logger(f"[Step {context.current_step}] ✅ Step completed")
        self.logger(f"[Step {context.current_step}] 📝 State mutations: {mutation_count}")
        
        if context.get("_final_result"):
            result_preview = context["_final_result"][:100] + "..." if len(str(context["_final_result"])) > 100 else context["_final_result"]
            self.logger(f"[Step {context.current_step}] 🎉 Final answer: {result_preview}")
    
    def on_execution_end(self, context: 'AgentContext', agent: 'AgentModule'):
        if context.get("_final_result"):
            self.logger("=" * 50)
            self.logger("🎯 Execution completed - Final answer:")
            self.logger(context["_final_result"])
            self.logger("=" * 50)


class PerformanceHook(Hook):
    """
    Performance analysis hook
    
    Measures time spent in each phase, supports performance optimization.
    
    Example:
        hook = PerformanceHook()
        result = run_agent(agent, task, hooks=[hook])
        stats = hook.get_stats()
    """
    
    def __init__(self):
        self.step_times: List[Dict[str, Any]] = []
        self.current_step_data: Optional[Dict[str, Any]] = None
    
    def on_step_start(self, context: 'AgentContext', agent: 'AgentModule'):
        self.current_step_data = {
            "step": context.current_step,
            "start_time": datetime.now().isoformat(),
            "phases": {}
        }
    
    def on_llm_response(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        messages: List[Dict[str, str]],
        raw_output: str,
        parsed_actions: List[Dict[str, Any]]
    ):
        if self.current_step_data:
            self.current_step_data["phases"]["llm"] = datetime.now().isoformat()
            self.current_step_data["llm_output_length"] = len(raw_output)
            self.current_step_data["parsed_actions_count"] = len(parsed_actions)
    
    def on_tool_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        tool_calls: List[Dict[str, Any]],
        observations: List[Any]
    ):
        if self.current_step_data:
            self.current_step_data["phases"]["tool"] = datetime.now().isoformat()
            self.current_step_data["tool_calls"] = len(tool_calls)
            self.current_step_data["observations"] = len(observations)
    
    def on_step_end(self, context: 'AgentContext', agent: 'AgentModule'):
        if self.current_step_data:
            self.current_step_data["phases"]["end"] = datetime.now().isoformat()
            self.current_step_data["end_time"] = datetime.now().isoformat()
            self.current_step_data["final_result"] = context.get("_final_result") is not None
            self.step_times.append(self.current_step_data)
            self.current_step_data = None
    
    def on_execution_end(self, context: 'AgentContext', agent: 'AgentModule'):
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics
        
        Returns:
            Dict containing performance data
        """
        return {
            "total_steps": len(self.step_times),
            "steps": self.step_times
        }
    
    def reset(self):
        """Reset statistics data"""
        self.step_times = []
        self.current_step_data = None


class InspectorHook(Hook):
    """
    Inspector hook
    
    Integrates with Inspector visualization tool, supports:
    - State change tracking
    - Timeline View data generation
    - Diff View data generation
    """
    
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
    
    def on_step_start(self, context: 'AgentContext', agent: 'AgentModule'):
        self.events.append({
            "type": "step_start",
            "step": context.current_step,
            "timestamp": datetime.now().isoformat(),
            "task": context.task
        })
    
    def on_llm_response(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        messages: List[Dict[str, str]],
        raw_output: str,
        parsed_actions: List[Dict[str, Any]]
    ):
        self.events.append({
            "type": "llm_response",
            "step": context.current_step,
            "timestamp": datetime.now().isoformat(),
            "output_length": len(raw_output),
            "parsed_actions": [a.get("name") for a in parsed_actions if a.get("name")]
        })
    
    def on_tool_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        tool_calls: List[Dict[str, Any]],
        observations: List[Any]
    ):
        self.events.append({
            "type": "tool_end",
            "step": context.current_step,
            "timestamp": datetime.now().isoformat(),
            "tool_calls": [call.get("tool") for call in tool_calls],
            "observation_count": len(observations)
        })
    
    def on_step_end(self, context: 'AgentContext', agent: 'AgentModule'):
        self.events.append({
            "type": "step_end",
            "step": context.current_step,
            "timestamp": datetime.now().isoformat(),
            "mutation_count": len(context.mutation_log)
        })
    
    def on_execution_end(self, context: 'AgentContext', agent: 'AgentModule'):
        self.events.append({
            "type": "execution_end",
            "step": context.current_step,
            "timestamp": datetime.now().isoformat(),
            "has_final_result": context.get("_final_result") is not None
        })
    
    def get_timeline_data(self) -> List[Dict[str, Any]]:
        """
        Get Timeline View data
        
        Returns:
            Timeline event list
        """
        return self.events
    
    def get_diff_data(self, step: int) -> Dict[str, Any]:
        """
        Get Diff View data for specified step
        
        Args:
            step: Step number
            
        Returns:
            State diff data
        """
        from ..core.context import AgentContext
        if hasattr(context, 'get_mutations_since'):
            mutations = context.get_mutations_since(step - 1)
        else:
            mutations = []
        return {
            "step": step,
            "mutations": [m.to_dict() if hasattr(m, 'to_dict') else m for m in mutations]
        }


class ConditionalHook(Hook):
    """
    Conditional breakpoint hook
    
    Supports pause or trigger callback under specific conditions.
    
    Example:
        hook = ConditionalHook(
            condition=lambda ctx, agent: len(ctx.observations) > 5,
            callback=lambda ctx, agent: print("Too many observations!")
        )
    """
    
    def __init__(
        self,
        condition: Callable[['AgentContext', 'AgentModule'], bool],
        on_trigger: Callable[['AgentContext', 'AgentModule'], None],
        trigger_on: str = "step_start"
    ):
        """
        Initialize conditional breakpoint
        
        Args:
            condition: Condition function, returns True to trigger
            on_trigger: Callback function when triggered
            trigger_on: Trigger timing (step_start / tool_end / step_end)
        """
        self.condition = condition
        self.on_trigger = on_trigger
        self.trigger_on = trigger_on
        self.trigger_count = 0
    
    def _check_and_trigger(self, context: 'AgentContext', agent: 'AgentModule'):
        """Check condition and trigger"""
        if self.condition(context, agent):
            self.trigger_count += 1
            self.on_trigger(context, agent)
    
    def on_step_start(self, context: 'AgentContext', agent: 'AgentModule'):
        if self.trigger_on == "step_start":
            self._check_and_trigger(context, agent)
    
    def on_tool_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        tool_calls: List[Dict[str, Any]],
        observations: List[Any]
    ):
        if self.trigger_on == "tool_end":
            self._check_and_trigger(context, agent)
    
    def on_step_end(self, context: 'AgentContext', agent: 'AgentModule'):
        if self.trigger_on == "step_end":
            self._check_and_trigger(context, agent)


def create_default_hooks(
    log_level: str = "info",
    enable_performance: bool = False
) -> List[Hook]:
    """
    Factory function: Create default hooks combination
    
    Args:
        log_level: Log level (debug/info/warning/error)
        enable_performance: Whether to enable performance analysis
        
    Returns:
        Hook list
    """
    hooks = []
    
    if log_level in ["debug", "info"]:
        verbose = (log_level == "debug")
        hooks.append(LoggingHook(verbose=verbose))
    
    if enable_performance:
        hooks.append(PerformanceHook())
    
    return hooks

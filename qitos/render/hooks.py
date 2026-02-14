"""
Rich Console Hook for QitOS

Inject Rich rendering logic into Engine lifecycle to provide production-grade console visual experience.

Usage:
    from qitos import AgentModule, ToolRegistry, skill
    from qitos.render.hooks import RichConsoleHook

    class MyAgent(AgentModule):
        system_prompt = "You are an assistant"
        def gather(self, context):
            return f"Task: {context.task}"

    agent = MyAgent(toolkit=ToolRegistry(), llm=my_llm)
    agent.run(task="Help me do something", hooks=[RichConsoleHook()])
"""

import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..core.hooks import Hook
from .cli_render import RichRender

if TYPE_CHECKING:
    from ..core.context import AgentContext
    from ..core.agent import AgentModule


class RichConsoleHook(Hook):
    """
    Rich console rendering hook
    
    Inject Rich rendering into Agent execution lifecycle:
    - on_step_start: Render step header
    - on_llm_response: Render LLM thinking process and tool calls
    - on_tool_end: Render tool execution results
    - on_execution_end: Render final answer
    
    Example:
        agent.run(task="xxx", hooks=[RichConsoleHook()])
    """
    
    def __init__(
        self,
        show_step_header: bool = True,
        show_llm_input: bool = True,
        show_thought: bool = True,
        show_action: bool = True,
        show_observation: bool = True,
        show_final_answer: bool = True,
        max_thought_length: int = 2000,
        max_observation_length: int = 2000
    ):
        """
        Initialize Rich console hook
        
        Args:
            show_step_header: Whether to show step header
            show_llm_input: Whether to show complete input sent to LLM
            show_thought: Whether to show thinking process
            show_action: Whether to show tool calls
            show_observation: Whether to show observation results
            show_final_answer: Whether to show final answer
            max_thought_length: Maximum length of thought content
            max_observation_length: Maximum length of observation content
        """
        self.show_step_header = show_step_header
        self.show_llm_input = show_llm_input
        self.show_thought = show_thought
        self.show_action = show_action
        self.show_observation = show_observation
        self.show_final_answer = show_final_answer
        self.max_thought_length = max_thought_length
        self.max_observation_length = max_observation_length
        self._tools_used: List[str] = []
    
    def on_step_start(
        self,
        context: 'AgentContext',
        agent: 'AgentModule'
    ) -> None:
        """Render step header at step start"""
        if self.show_step_header:
            RichRender.print_step_header(context.current_step)
    
    def on_perceive_start(
        self,
        context: 'AgentContext',
        agent: 'AgentModule'
    ) -> None:
        """At perception start (optional rendering)"""
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
        Render thinking and actions after LLM response is parsed
        
        Extract from LLM output:
        - Thought (reasoning process)
        - Action (tool calls)
        """
        # First print input sent to LLM
        if self.show_llm_input and messages:
            RichRender.print_llm_input(messages, context.current_step)
        
        if not raw_output:
            return
        
        output = raw_output.strip()
        
        if self.show_thought:
            thought = self._extract_thought(output)
            if thought:
                thought = thought[:self.max_thought_length]
                RichRender.print_thought(thought, context.current_step)
        
        if self.show_action and parsed_actions:
            for action in parsed_actions:
                tool_name = action.get("name")
                args = action.get("args", {})
                error = action.get("error")
                
                if tool_name and tool_name != "FINAL_ANSWER":
                    self._tools_used.append(tool_name)
                    RichRender.print_action(tool_name, args, context.current_step)
                
                if error:
                    RichRender.print_error(f"Action parsing error: {error}")
    
    def on_tool_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule',
        tool_calls: List[Dict[str, Any]],
        observations: List[Any]
    ) -> None:
        """Render observation results after tool execution"""
        if not self.show_observation:
            return
        
        for obs in observations:
            if isinstance(obs, dict):
                status = obs.get("status", "unknown")
                tool_name = obs.get("tool", "unknown")
                
                if status == "error":
                    message = obs.get("message", "Unknown error")
                    RichRender.print_error(message)
                else:
                    result = obs.get("result", obs)
                    RichRender.print_observation(result, context.current_step)
            else:
                RichRender.print_observation(obs, context.current_step)
    
    def on_step_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule'
    ) -> None:
        """At step end (optional separator)"""
        pass
    
    def on_execution_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule'
    ) -> None:
        """Render final answer at end of entire execution"""
        if not self.show_final_answer:
            return
        
        final_result = context.get("_final_result")
        if final_result:
            RichRender.print_final_answer(final_result, context.task)
            
            if self._tools_used:
                tools_unique = list(dict.fromkeys(self._tools_used))
                print()
                print(f"[bold]Tools used:[/bold] {', '.join(tools_unique)}")
    
    def _extract_thought(self, output: str) -> Optional[str]:
        """
        Extract Thought content from LLM output
        
        Supports multiple formats:
        - Thought: xxx
        - 思考: xxx
        - Or text located before Action:
        
        Args:
            output: Raw LLM output
            
        Returns:
            Extracted thought text, or None if not found
        """
        if not output:
            return None
        
        patterns = [
            r'Thought:\s*(.+?)(?:\nAction:|\nFinal Answer:|$)',
            r'思考:\s*(.+?)(?:\nAction:|\nFinal Answer:|$)',
            r'推理:\s*(.+?)(?:\nAction:|\nFinal Answer:|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE | re.DOTALL)
            if match:
                thought = match.group(1).strip()
                if thought:
                    return thought
        
        action_match = re.search(r'Action:\s*\w+', output, re.IGNORECASE)
        if action_match:
            before_action = output[:action_match.start()].strip()
            if before_action and len(before_action) > 10:
                lines = before_action.split('\n')
                last_meaningful_lines = []
                for line in reversed(lines):
                    line = line.strip()
                    if line and not line.startswith('Observation'):
                        last_meaningful_lines.append(line)
                    if len(last_meaningful_lines) >= 2:
                        break
                if last_meaningful_lines:
                    return '\n'.join(reversed(last_meaningful_lines))
        
        final_match = re.search(r'Final Answer:\s*(.+?)$', output, re.DOTALL)
        if final_match:
            before_final = output[:final_match.start()].strip()
            if before_final and len(before_final) > 10:
                return before_final
        
        return None
    
    def reset(self):
        """Reset hook state"""
        self._tools_used = []


class SimpleRichConsoleHook(RichConsoleHook):
    """
    Simplified Rich console hook
    
    Only displays final answer and key information, suitable for quick output.
    """
    
    def __init__(self):
        super().__init__(
            show_step_header=False,
            show_llm_input=False,
            show_thought=False,
            show_action=False,
            show_observation=False,
            show_final_answer=True
        )


class VerboseRichConsoleHook(RichConsoleHook):
    """
    Verbose Rich console hook
    
    Displays all execution details, suitable for debugging and learning.
    """
    
    def __init__(self):
        super().__init__(
            show_step_header=True,
            show_llm_input=True,
            show_thought=True,
            show_action=True,
            show_observation=True,
            show_final_answer=True,
            max_thought_length=5000,
            max_observation_length=5000
        )
    
    def on_step_end(
        self,
        context: 'AgentContext',
        agent: 'AgentModule'
    ) -> None:
        """Add separator at step end in verbose mode"""
        RichRender.print_separator("dim")

"""
ExecutionEngine: Execution Engine

The engine is the behind-the-scenes scheduler, handling the dirty work.

Core features:
- Standard execution loop (step)
- Tool execution and error handling
- Hook system integration
- Eager Execution support
- Configurable Action parser
- Customizable termination conditions
- Multi-tool parallel execution support
- Parse error feedback mechanism
- Memory module integration
"""

import re
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple
from ..core.context import AgentContext
from ..core.skill import ToolRegistry
from ..core.hooks import Hook, CompositeHook
from ..memory.base import BaseMemory
from ..memory.window import WindowMemory

if TYPE_CHECKING:
    from ..core.agent import AgentModule


class ToolErrorHandler:
    """
    Tool error handler
    
    Supports configurable strategies:
    - raise: Directly raise exception (for debugging)
    - inject_error: Format exception info as Observation and return to Agent (for production)
    - skip: Skip error calls
    """
    
    def __init__(self, strategy: str = "inject_error"):
        """
        Initialize error handler
        
        Args:
            strategy: Error handling strategy
        """
        self.strategy = strategy
    
    def handle(
        self,
        exception: Exception,
        tool_name: str,
        tool_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle tool execution error
        
        Args:
            exception: Caught exception
            tool_name: Tool name
            tool_args: Tool arguments
            
        Returns:
            Formatted error info (as Observation)
        """
        if self.strategy == "raise":
            raise exception
        
        elif self.strategy == "inject_error":
            return {
                "status": "error",
                "tool": tool_name,
                "message": str(exception),
                "args": tool_args,
                "error_type": type(exception).__name__
            }
        
        elif self.strategy == "skip":
            return None
        
        else:
            return {
                "status": "error",
                "tool": tool_name,
                "message": str(exception),
                "error_type": type(exception).__name__
            }
    
    def __repr__(self) -> str:
        return f"ToolErrorHandler(strategy='{self.strategy}')"


class ActionParser:
    """
    Action parser
    
    Parse tool name and arguments from LLM response.
    Supports multiple parsing formats and can be extended via inheritance.
    
    Return format:
    - List[Dict]: Dict for each Action
      - {"name": str, "args": dict, "error": Optional[str]}
      - If parsing fails, name is None, contains error description
    
    Supported formats:
    - Action: tool_name(args)
    - Action: {"name": "...", "args": {...}}
    - Action N: tool_name
    """
    
    def __init__(self):
        """Initialize parser"""
        pass
    
    def parse(
        self,
        response: Any,
        available_tools: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Parse Actions from LLM response
        
        Args:
            response: LLM raw response
            available_tools: Available tool list (for validation)
            
        Returns:
            Action dict list, format is [{"name": str, "args": dict, "error": Optional[str]}]
        """
        if response is None:
            return self._make_error_action("Empty response received")
        
        text = str(response)
        
        if not text.strip():
            return self._make_error_action("Empty response received")
        
        actions = self._parse_text(text)
        
        validated_actions = []
        for action in actions:
            name = action.get("name")
            error = action.get("error")
            
            if error:
                validated_actions.append(action)
            elif name and available_tools and name not in available_tools:
                validated_actions.append({
                    "name": None,
                    "args": action.get("args", {}),
                    "error": f"Unknown tool: '{name}'. Available tools: {', '.join(available_tools)}"
                })
            else:
                validated_actions.append(action)
        
        if not validated_actions:
            return [] #self._make_error_action("No valid actions found in response")
        
        return validated_actions
    
    def _make_error_action(
        self,
        error_msg: str,
        name: Optional[str] = None,
        args: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Create an error Action
        
        Args:
            error_msg: Error message
            
        Returns:
            Action list containing error
        """
        return [{
            "name": name,
            "args": args or {},
            "error": error_msg
        }]
    
    def _parse_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse text content
        
        Subclasses can override this method to implement custom parsing logic.
        
        Args:
            text: LLM response text
            
        Returns:
            Action dict list
        """
        return []
    
    def _extract_json_actions(self, text: str) -> List[Dict[str, Any]]:
        """
        Try to match JSON format Action (supports nested quotes)
        
        Format: Action: {"name": "tool_name", "args": {...}}
        """
        import json as json_module
        
        actions = []
        
        start_pattern = r'Action\s*:\s*\{'
        matches = list(re.finditer(start_pattern, text, re.IGNORECASE))
        
        for match in matches:
            start_pos = match.end() - 1
            
            brace_count = 1
            pos = start_pos + 1
            end_pos = None
            
            while pos < len(text) and brace_count > 0:
                if text[pos] == '{':
                    brace_count += 1
                elif text[pos] == '}':
                    brace_count -= 1
                pos += 1
            
            if brace_count == 0:
                end_pos = pos - 1
                json_str = text[match.start():end_pos + 1]
                
                json_str = json_str.replace('Action:', '').strip()
                
                try:
                    data = json_module.loads(json_str)
                    if isinstance(data, dict):
                        name = data.get("name") or data.get("tool") or data.get("function")
                        args = data.get("args") or data.get("arguments") or data.get("parameters") or {}
                        actions.append({
                            "name": name,
                            "args": args,
                            "error": None
                        })
                except (json_module.JSONDecodeError, AttributeError) as e:
                    actions.append({
                        "name": None,
                        "args": {},
                        "error": f"JSON parsing failed: {str(e)}"
                    })
        
        return actions
    
    def _extract_simple_actions(self, text: str) -> List[Dict[str, Any]]:
        """
        Try to match simple format Action (global match)
        
        Format: Action: tool_name(args)
        """
        actions = []
        
        pattern = r'Action\s*:\s*(\w+)\s*\(\s*(.*?)\s*\)'
        matches = list(re.finditer(pattern, text))
        
        for match in matches:
            tool_name = match.group(1)
            args_str = match.group(2)
            args = self._parse_args_str(args_str)
            actions.append({
                "name": tool_name,
                "args": args,
                "error": None
            })
        
        return actions
    
    def _extract_numbered_actions(self, text: str) -> List[Dict[str, Any]]:
        """
        Try to match numbered format Action
        
        Format:
        Action 1: tool_name
        {"param": "value"}
        """
        actions = []
        lines = text.strip().split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            pattern = r'Action\s*\d*\s*:\s*(\w+)$'
            match = re.search(pattern, line, re.IGNORECASE)
            
            if match:
                tool_name = match.group(1)
                args = {}
                
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line:
                        args = self._parse_args_str(next_line)
                
                actions.append({
                    "name": tool_name,
                    "args": args,
                    "error": None
                })
            
            i += 1
        
        return actions
    
    def _parse_args_str(self, args_str: str) -> Dict[str, Any]:
        """
        Parse argument string
        
        Args:
            args_str: Argument string
            
        Returns:
            Argument dict
        """
        args_str = args_str.strip()
        
        if not args_str:
            return {}
        
        import json as json_module
        
        if args_str.startswith('{') and args_str.endswith('}'):
            try:
                return json_module.loads(args_str)
            except json_module.JSONDecodeError:
                pass
        
        result = {}
        
        pairs = args_str.split(',')
        for pair in pairs:
            pair = pair.strip()
            if '=' in pair:
                key, value = pair.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"\'')
                
                if value.isdigit():
                    value = int(value)
                elif value.replace('.', '').isdigit():
                    value = float(value)
                elif value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                
                result[key] = value
        
        if result:
            return result
        
        return {"input": args_str}
    
    def _check_final_answer(self, text: str) -> bool:
        """
        Check if it's final answer
        
        Args:
            text: LLM response text
            
        Returns:
            Whether it's final answer
        """
        final_patterns = [
            r'Final Answer:',
            r'最终答案:',
            r'结论:',
            r'完成',
            r'Done\.?',
            r'Finished\.?',
        ]
        
        for pattern in final_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _extract_final_answer(self, text: str) -> Optional[str]:
        """
        Extract final answer content
        
        Args:
            text: LLM response text
            
        Returns:
            Final answer content, or None if not found
        """
        patterns = [
            (r'Final Answer:\s*(.+?)(?:\n\n|$)', 'Final Answer:'),
            (r'最终答案:\s*(.+?)(?:\n\n|$)', '最终答案:'),
            (r'结论:\s*(.+?)(?:\n\n|$)', '结论:'),
        ]
        
        for pattern, prefix in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def __repr__(self) -> str:
        return f"ActionParser()"


class DefaultActionParser(ActionParser):
    """
    Default Action parser
    
    Combines multiple parsing strategies:
    1. Final answer detection
    2. JSON format
    3. Simple parameter format
    4. Numbered format
    """
    
    def _parse_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Combine multiple parsing strategies
        
        Priority:
        1. JSON Action format (complete response with Thought/Action/Observation)
        2. Simple Action format
        3. Numbered Action format
        4. Final Answer (if no Action)
        
        Returns:
            Action dict list
        """
        # First try to parse Action (priority over Final Answer)
        actions = self._extract_json_actions(text)
        if actions:
            # Check if also contains Final Answer
            final_answer = self._extract_final_answer(text)
            if final_answer:
                actions.append({
                    "name": "FINAL_ANSWER",
                    "args": {"content": final_answer},
                    "error": None
                })
            return actions
        
        actions = self._extract_simple_actions(text)
        if actions:
            return actions
        
        actions = self._extract_numbered_actions(text)
        if actions:
            return actions
        
        # Only return Final Answer if no Action found
        final_answer = self._extract_final_answer(text)
        if final_answer:
            return [{
                "name": "FINAL_ANSWER",
                "args": {"content": final_answer},
                "error": None
            }]
        
        return []


class ReActActionParser(DefaultActionParser):
    """
    ReAct style Action parser
    
    Specifically optimized for ReAct (Reasoning + Acting) mode output.
    """
    
    def _parse_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Check final answer first, then parse Action
        """
        if self._check_final_answer(text):
            final_answer = self._extract_final_answer(text) or text
            return [{
                "name": "FINAL_ANSWER",
                "args": {"content": final_answer},
                "error": None
            }]
        
        return super()._parse_text(text)


def parse_tool_calls(text: str, available_tools: List[str]) -> Dict[str, Any]:
    """
    Parse tool calls from LLM output (backward compatible interface)
    
    Args:
        text: LLM raw output
        available_tools: Available tool list
        
    Returns:
        Parse result:
        - {"is_final": True, "content": "..."}  or
        - {"is_final": False, "tool_calls": [{"tool": "...", "args": "..."}, ...]}
    """
    parser = DefaultActionParser()
    actions = parser.parse(text, available_tools)
    
    if not actions:
        return {
            "is_final": True,
            "content": text
        }
    
    first_action = actions[0]
    name = first_action.get("name")
    error = first_action.get("error")
    
    if name == "FINAL_ANSWER":
        content = first_action.get("args", {}).get("content", text)
        return {
            "is_final": True,
            "content": content
        }
    
    if name is None and error:
        return {
            "is_final": True,
            "content": text
        }
    
    tool_calls = []
    for action in actions:
        tool_name = action.get("name")
        tool_args = action.get("args", {})
        action_error = action.get("error")
        
        if tool_name and not action_error:
            tool_calls.append({
                "tool": tool_name,
                "args": tool_args
            })
    
    if tool_calls:
        return {
            "is_final": False,
            "tool_calls": tool_calls
        }
    
    return {
        "is_final": True,
        "content": text
    }


class ExecutionEngine:
    """
    Execution engine
    
    Responsible for task scheduling, tool execution, error handling.
    
    Core flow:
    1. on_step_start
    2. gather + memory.retrieve -> messages
    3. LLM -> Parse
    4. Execute tools (with error handling)
    5. absorb
    6. on_step_end
    7. Increment step
    
    Supports customization:
    - parser: Action parser (default DefaultActionParser)
    - memory: Memory module (default WindowMemory)
    """
    
    def __init__(
        self,
        agent: 'AgentModule',
        hooks: Optional[List[Hook]] = None,
        error_handler: Optional[ToolErrorHandler] = None,
        observation_window: int = 5,
        parser: Optional[ActionParser] = None,
        memory: Optional[BaseMemory] = None,
        stopping_criteria: Optional[Callable[[AgentContext, Any], bool]] = None
    ):
        """
        Initialize execution engine
        
        Args:
            agent: AgentModule instance
            hooks: Hook list
            error_handler: Error handler
            observation_window: Observation window size (deprecated, managed by memory module)
            parser: Action parser (default DefaultActionParser)
            memory: Memory module (default WindowMemory(window_size=5))
            stopping_criteria: Custom termination condition function (context, response) -> bool
        """
        self.agent = agent
        self.hooks = CompositeHook(hooks) if hooks else None
        self.error_handler = error_handler or ToolErrorHandler()
        self.parser = parser or DefaultActionParser()
        self.stopping_criteria = stopping_criteria
        
        if memory is None:
            memory = WindowMemory(window_size=5)
        self.memory: BaseMemory = memory
        
        self._step_times: List[float] = []
        self._tool_times: Dict[str, List[float]] = {}
    
    def is_finished(
        self,
        context: AgentContext,
        response: Any
    ) -> bool:
        """
        Determine if execution should finish
        
        Check order:
        1. Step limit (max_steps)
        2. User-defined termination condition
        3. Default content markers (Final Answer, etc.)
        
        Args:
            context: AgentContext
            response: LLM response
            
        Returns:
            Whether should terminate
        """
        current_step = context.get("current_step", 0)
        max_steps = context.get("max_steps", 10)
        
        if current_step >= max_steps:
            context.metadata["stop_reason"] = "max_steps_reached"
            return True
        
        if self.stopping_criteria:
            try:
                if self.stopping_criteria(context, response):
                    context.metadata["stop_reason"] = "custom_criteria"
                    return True
            except Exception:
                pass
        
        text = str(response)
        
        final_patterns = [
            r'Final Answer:',
            r'最终答案:',
            r'结论:',
        ]
        
        for pattern in final_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                context.metadata["stop_reason"] = "final_answer"
                return True
        
        return False
    
    def _build_messages(
        self,
        context: AgentContext,
        current_prompt: str
    ) -> List[Dict[str, str]]:
        """
        Build complete message list
        
        Message orchestration strategy: [System?, ...History, Current_User_Msg]
        - System: agent.get_system_prompt(context) dynamically gets and replaces {{tool_schema}}
        - History: memory.retrieve(context) extracts from trajectory
        
        Args:
            context: AgentContext instance
            current_prompt: Current round prompt (from gather)
            
        Returns:
            Complete message list
        """
        messages = []
        
        system_prompt = self._get_system_prompt(context)
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        history_messages = self.memory.retrieve(context)
        
        has_system_in_history = (
            history_messages and
            history_messages[0].get("role") == "system"
        )
        
        if has_system_in_history and system_prompt:
            history_messages = history_messages[1:]
        
        messages.extend(history_messages)
        
        return messages
    
    def _get_system_prompt(self, context: AgentContext) -> Optional[str]:
        """
        Get and process system prompt
        
        Processing flow:
        1. Call agent.get_system_prompt(context) to get prompt
        2. If returns None, use default ReAct template
        3. Replace {{tool_schema}} placeholder with tool definitions
        
        Args:
            context: AgentContext instance
            
        Returns:
            Processed system prompt, or None if no prompt
        """
        prompt = self.agent.get_system_prompt(context)
        
        if prompt is None:
            from ..core.agent import DEFAULT_REACT_PROMPT
            prompt = DEFAULT_REACT_PROMPT
        
        if prompt and "{{tool_schema}}" in prompt:
            schema_str = self.agent.toolkit.get_tool_descriptions()
            prompt = prompt.replace("{{tool_schema}}", schema_str)
        return prompt
    
    def execute_step(self, context: AgentContext) -> List[Any]:
        """
        Execute single step reasoning
        
        This is the core method of Eager Execution.
        
        Args:
            context: AgentContext instance (needs task pre-set)
            
        Returns:
            This round's observations
            
        Timing description:
        1. on_step_start: Step starts
        2. gather: Get current prompt
        3. Record user message to trajectory
        4. _build_messages: Build complete messages
        5. LLM call
        6. Record assistant response to trajectory
        7. Parse output
        8. Execute tools (with error handling)
        9. Record actions to trajectory
        10. on_tool_end: After tool execution (via Hook)
        11. absorb: User absorbs observations
        12. on_step_end: Step ends
        """
        step = context.get("current_step", 0)
        start_time = time.time()
        
        if self.hooks:
            self.hooks.on_step_start(context, self.agent)
        
        current_prompt = ""
        try:
            current_prompt = self.agent.gather(context)
        except Exception as e:
            current_prompt = f"Gather error: {str(e)}"
        
        context.add_entry("user", current_prompt)
        
        try:
            messages = self._build_messages(context, current_prompt)
        except Exception as e:
            error_msg = f"Message building error: {str(e)}"
            context["_message_error"] = str(e)
            raise BaseException(error_msg)
        
        response = ""
        try:
            if self.agent.llm:
                response = self.agent.llm(messages)
            else:
                response = "Error: No LLM configured. Please set agent.llm."
        except Exception as e:
            response = f"LLM Error: {str(e)}"
        
        if self.is_finished(context, response):
            final_result = response
            
            text = str(response)
            if "Final Answer:" in text:
                final_result = text.split("Final Answer:", 1)[-1].strip()
            elif "最终答案:" in text:
                final_result = text.split("最终答案:", 1)[-1].strip()
            elif "结论:" in text:
                final_result = text.split("结论:", 1)[-1].strip()
            
            context["_final_result"] = final_result
            
            if self.hooks:
                self.hooks.on_llm_response(context, self.agent, messages, response, [])
                self.hooks.on_step_end(context, self.agent)
            
            return []
        
        actions = self.parser.parse(
            response,
            self.agent.toolkit.list_tools()
        )
        context.add_entry("assistant", response)

        if self.hooks:
            self.hooks.on_llm_response(context, self.agent, messages, response, actions)
        
        observations = []
        tool_calls = []
        print(actions)
        
        for action in actions:
            name = action.get("name")
            args = action.get("args", {})
            error = action.get("error")
            
            if error:
                observations.append({
                    "status": "error",
                    "tool": name or "UNKNOWN",
                    "message": f"Action parsing error: {error}",
                    "raw_action": action
                })
                tool_calls.append({
                    "tool": name,
                    "args": args,
                    "error": error
                })
                context.add_entry("action", {"name": name, "args": args, "error": error})
                continue
            
            if name == "FINAL_ANSWER":
                final_content = args.get("content", response)
                context["_final_result"] = final_content
                break
            
            if name and name in self.agent.toolkit:
                context.add_entry("action", {"name": name, "args": args})
                tool_start = time.time()
                
                try:
                    obs = self.agent.toolkit.call(name, **args)
                    
                    tool_time = time.time() - tool_start
                    if name not in self._tool_times:
                        self._tool_times[name] = []
                    self._tool_times[name].append(tool_time)
                    
                except Exception as e:
                    obs = self.error_handler.handle(e, name, args)
                
                if obs is not None:
                    observations.append(obs)
                
                tool_calls.append({
                    "tool": name,
                    "args": args,
                    "error": None
                })
            elif name:
                observations.append({
                    "status": "error",
                    "tool": name,
                    "message": f"Tool '{name}' not found",
                    "available_tools": self.agent.toolkit.list_tools()
                })
                tool_calls.append({
                    "tool": name,
                    "args": args,
                    "error": f"Unknown tool: {name}"
                })
        
        print('observations: ', observations)        
        if observations and self.hooks:
            self.hooks.on_tool_end(context, self.agent, tool_calls, observations)
        
        self.agent.absorb(context, observations, action_text=response)
        
        if self.hooks:
            self.hooks.on_step_end(context, self.agent)
        
        step_time = time.time() - start_time
        self._step_times.append(step_time)
        
        context["current_step"] = step + 1
        
        if context.get("_plan"):
            has_error = any(
                (isinstance(obs, dict) and obs.get("status") == "error")
                for obs in observations
            )
            if not has_error:
                context.complete_current_step()
        
        return observations
    
    def execute(self, context: AgentContext) -> str:
        """
        Execute complete workflow (until final answer or max steps reached)
        
        Args:
            context: AgentContext instance
            
        Returns:
            Final answer
        """
        max_steps = context.get("max_steps", 10)
        
        for step in range(max_steps):
            context["current_step"] = step
            observations = self.execute_step(context)
            
            if context.get("_final_result"):
                if self.hooks:
                    self.hooks.on_execution_end(context, self.agent)
                return context["_final_result"]
        
        context["_final_result"] = "Agent failed to produce final answer within step limit."
        if self.hooks:
            self.hooks.on_execution_end(context, self.agent)
        return context["_final_result"]
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics
        
        Returns:
            Dict containing execution time statistics
        """
        return {
            "total_steps": len(self._step_times),
            "total_time": sum(self._step_times),
            "avg_step_time": sum(self._step_times) / len(self._step_times) if self._step_times else 0,
            "tool_times": {
                tool: {
                    "calls": len(times),
                    "avg_time": sum(times) / len(times),
                    "total_time": sum(times)
                }
                for tool, times in self._tool_times.items()
            }
        }
    
    def __repr__(self) -> str:
        return f"ExecutionEngine(steps=∞, tools={len(self.agent.toolkit)}, memory={self.memory})"


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
) -> str:
    """
    Simplified interface for running Agent
    
    Args:
        agent: AgentModule instance
        task: Initial task description
        max_steps: Max step limit
        hooks: Hook list
        error_strategy: Error handling strategy
        parser: Action parser (default DefaultActionParser)
        memory: Memory module (default WindowMemory)
        stopping_criteria: Custom termination condition function (context, response) -> bool
        
    Returns:
        Final answer
        
    Example:
        # Basic usage
        agent = MyAgent(toolkit=my_tools, llm=my_llm)
        result = run_agent(agent, "Order takeout", max_steps=5)
        
        # Custom parser
        parser = ReActActionParser()
        result = run_agent(agent, "Search", parser=parser)
        
        # Custom memory
        from qitos.memory import WindowMemory
        memory = WindowMemory(window_size=10)
        result = run_agent(agent, "Complex task", memory=memory)
        
        # Custom termination condition
        def stop_on_success(context, response):
            return "success" in str(response).lower()
        
        result = run_agent(agent, "Complete task", stopping_criteria=stop_on_success)
    """
    from ..core.context import AgentContext
    
    context = AgentContext(task=task, max_steps=max_steps)
    
    engine = ExecutionEngine(
        agent=agent,
        hooks=hooks,
        error_handler=ToolErrorHandler(strategy=error_strategy),
        parser=parser,
        memory=memory,
        stopping_criteria=stopping_criteria
    )
    
    return engine.execute(context)

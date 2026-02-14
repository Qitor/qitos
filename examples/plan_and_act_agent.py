"""
Plan-and-Act Agent for Complex File Editing Tasks

This example demonstrates how to build an agent that:
1. Plans complex editing tasks into steps
2. Executes each step using the EditorSkill
3. Uses the EditorSkill package for file operations
"""

from typing import List, Any, Optional
from qitos import AgentModule, AgentContext
from qitos.models import OpenAICompatibleModel
from qitos.render import RichConsoleHook
from qitos.skills.editor import EditorSkill
from qitos.core.skill import ToolRegistry
from qitos.core.hooks import Hook


class EditorPlanAndActAgent(AgentModule):
    """
    An Agent that breaks down file editing tasks into a plan before execution.
    
    Uses the EditorSkill package to perform complex file operations:
    - view: View file or directory content
    - create: Create new files
    - str_replace: Replace exact strings in files
    - insert: Insert content at specific line numbers
    - replace_lines: Replace a range of lines
    - search: Search for keywords in files
    - list_tree: List directory structure
    """
    
    PLANNER_PROMPT = """You are a strategic planner for file editing tasks.
Given the Task, break it down into a numbered list of concrete steps.
Each step should be atomic and actionable.

Available Tools
{{tool_schema}}

Output format:
Return a numbered list, one step per line. Be specific about file paths and changes."""

    EXECUTOR_PROMPT = """You are an expert file editor.
Global Plan:
{{plan_status}}

Currently working on Step {{current_idx}}: {{current_step}}

Available Tools
{{tool_schema}}

When finished with this sub-task, provide the result so we can move to the next step.
If the step is complete, say "Step completed: [summary of what was done]"
If there was an error, explain what went wrong and how to fix it.

When you want to invoke a tool, you should output as:

Thought: Analyze the current problem and make sure the tool is appropriate for the task.
Action: tool_name(param_1=..., param_2=...)
"""

    def get_system_prompt(self, context: AgentContext) -> str:
        if not context.is_planned():
            return self.PLANNER_PROMPT
        
        plan = context.get("plan", [])
        cursor = context.plan_cursor
        
        plan_status = ""
        for i, step in enumerate(plan):
            if i < cursor:
                status = "[DONE]"
            elif i == cursor:
                status = "[DOING]"
            else:
                status = "[WAIT]"
            plan_status += f"{i}. {status} {step}\n"
        
        if cursor >= len(plan):
            return "All steps completed! Provide a final summary of what was accomplished."
        
        return self.EXECUTOR_PROMPT.replace('{{plan_status}}', plan_status).replace(f'{{current_idx}}', str(cursor)).replace('{{current_step}}', context.current_plan_step())

    def gather(self, context: AgentContext) -> str:
        if not context.is_planned():
            return f"Initial Task: {context.task}\n\nPlease generate a plan with numbered steps."
        
        current_step = context.current_plan_step()
        if current_step is None:
            return "All steps completed. Provide your final summary."
        
        prev_obs = context.get("last_obs", "")
        
        if prev_obs:
            return f"Previous step result: {prev_obs}\n\nNow execute: {current_step}"
        
        return f"Execute: {current_step}"

    def absorb(self, context: AgentContext, observations: List[Any], action_text: Optional[str] = None):
        if not context.is_planned() and action_text:
            plan = self._extract_list_from_text(action_text)
            if plan:
                context.set_plan(plan)
                return
        
        super().absorb(context, observations, action_text)
        
        if observations:
            obs_str = str(observations[0]) if observations else ""
            context.last_obs = obs_str
            
            if "Error" not in obs_str and "completed" in obs_str.lower():
                if context.plan_cursor < len(context.get("plan", [])):
                    context.advance_plan()
    
    def _extract_list_from_text(self, text: str) -> List[str]:
        """
        Extract numbered list from text.
        
        Supports formats like:
        1. First item
        2. Second item
        3. Third item
        
        Args:
            text: Text containing numbered list
            
        Returns:
            List of items, or empty list if no valid list found
        """
        if not text:
            return []
        
        import re
        
        lines = text.strip().split('\n')
        items = []
        
        for line in lines:
            line = line.strip()
            
            match = re.match(r'^(\d+)[\.\)]\s*(.+)$', line)
            if match:
                item = match.group(2).strip()
                if item:
                    items.append(item)
            
            elif line.startswith('- ') or line.startswith('* '):
                item = line[2:].strip()
                if item:
                    items.append(item)
        
        return items


class ProgressHook(Hook):
    """Hook to display planning and execution progress."""
    
    def on_step_start(self, context, agent):
        if context.is_planned():
            cursor = context.plan_cursor
            total = len(context.get("plan", []))
            print(f"\n📋 Plan Progress: Step {cursor + 1}/{total}")
            current_step = context.current_plan_step()
            if current_step:
                print(f"   Current: {current_step}")
        else:
            print(f"\n📋 Planning: {context.task}")
    
    def on_llm_response(self, context, agent, messages, raw_output, parsed_actions):
        if parsed_actions:
            for action in parsed_actions:
                name = action.get('name', 'unknown')
                args = action.get('args', {})
                if name != 'FINAL_ANSWER':
                    print(f"   🔧 Tool: {name}({args})")
    
    def on_tool_end(self, context, agent, tool_calls, observations):
        for obs in observations:
            if isinstance(obs, dict):
                if obs.get('status') == 'success':
                    stdout = obs.get('stdout', '')[:200]
                    if stdout:
                        print(f"   ✅ {stdout[:100]}...")
    
    def on_execution_end(self, context, agent):
        if context.is_planned():
            cursor = context.plan_cursor
            total = len(context.get("plan", []))
            print(f"\n🎯 Plan Execution: {cursor}/{total} steps completed")


def create_editor_tools(workspace_root: str = "."):
    """
    Create editor tools using the new skill system.
    
    EditorSkill itself is a Skill with a run() method that dispatches to commands.
    """
    registry = ToolRegistry()
    editor = EditorSkill(workspace_root=workspace_root)
    registry.register(editor, name="editor", domain="editor")
    return registry


def main():
    import os
    
    workspace_root = os.path.dirname(os.path.abspath(__file__))
    
    registry = create_editor_tools(workspace_root=workspace_root)
    
    llm = OpenAICompatibleModel(
        model="Qwen/Qwen3-8B",
        base_url="https://api.siliconflow.cn/v1",
        api_key="sk-nbxooqwpyyvzfexesvwqgogfogvicxmpyscqgihtsuvyyimr"
    )
    
    editor = EditorSkill(workspace_root=workspace_root)
    agent = EditorPlanAndActAgent(llm=llm, skills=[editor])
    
    print("=" * 60)
    print("Plan-and-Act Editor Agent")
    print("=" * 60)
    
    tasks = [
        "Create a new Python module with a hello world function",
        "Search for 'def' in all Python files and list the results",
        "Create a README.md with project documentation",
    ]
    
    for i, task in enumerate(tasks):
        print(f"\n{'='*60}")
        print(f"Task {i+1}: {task}")
        print("=" * 60)
        
        result = agent.run(
            task=task,
            max_steps=15,
            hooks=[ProgressHook(), RichConsoleHook()]
        )
        
        print(f"\n📊 Final Result: {result}")


if __name__ == "__main__":
    main()

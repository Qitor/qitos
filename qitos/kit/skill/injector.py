"""Prompt injection system for integrating selected skills into prompts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from .manifest import SkillManifest

if TYPE_CHECKING:
    from .registry import SkillRegistry


@dataclass
class PromptContext:
    """Context for building prompts with skills."""

    task: str
    active_skills: List[SkillManifest] = field(default_factory=list)
    memory_snippets: List[str] = field(default_factory=list)
    available_tools: List[str] = field(default_factory=list)


class SkillInjector:
    """Injects skill instructions into agent prompts.

    This is the bridge between declarative skills and the agent's
    decision-making process. Skills provide context that helps the
    agent know when and how to use tools.
    """

    def __init__(self, include_examples: bool = True, include_guidelines: bool = True):
        self.include_examples = include_examples
        self.include_guidelines = include_guidelines

    def build_system_prompt(
        self,
        base_prompt: str,
        skills: List[SkillManifest],
        context: Optional[PromptContext] = None,
    ) -> str:
        """Build system prompt with skill context injected.

        Args:
            base_prompt: Original system prompt
            skills: Skills to activate
            context: Additional runtime context

        Returns:
            Enhanced prompt with skill instructions
        """
        deduped: List[SkillManifest] = []
        for skill in skills:
            if skill not in deduped:
                deduped.append(skill)

        if not deduped:
            return base_prompt

        parts = [base_prompt]
        parts.append("\n\n# ACTIVE SKILLS\n")
        parts.append(
            "You have access to the following specialized skills. "
            "Use them only when they materially help the current task.\n"
        )

        for skill in deduped:
            parts.append(self._format_skill(skill))

        # Add tool guidance if tools are available
        if context and context.available_tools:
            parts.append(self._format_tool_guidance(context))

        return "".join(parts)

    def _format_skill(self, skill: SkillManifest) -> str:
        """Format a single skill for injection."""
        lines = [f"\n## {skill.name}", f"*When to use: {skill.description}*", ""]

        instructions = skill.instructions.strip()

        if not self.include_examples:
            instructions = self._remove_section(instructions, "## Examples")
        if not self.include_guidelines:
            instructions = self._remove_section(instructions, "## Guidelines")

        lines.append(instructions)
        lines.append("")

        return "\n".join(lines)

    def build_catalog(self, skills: List[SkillManifest]) -> str:
        """Advertise descriptions only; select skills before injecting full bodies.

        This is not a context budget policy. The normal request compiler still
        decides whether the selected, complete instructions fit its budget.
        """
        return "\n".join(f"- {skill.name}: {skill.description}" for skill in skills)

    def _remove_section(self, content: str, section_header: str) -> str:
        """Remove a section from markdown content."""
        import re

        pattern = rf"{re.escape(section_header)}.*?\n(?=## |\Z)"
        return re.sub(pattern, "", content, flags=re.DOTALL).strip()

    def _format_tool_guidance(self, context: PromptContext) -> str:
        """Format tool availability guidance."""
        lines = [
            "\n## AVAILABLE TOOLS\n",
            "You can use these tools to accomplish the task:\n",
        ]
        for tool in context.available_tools:
            lines.append(f"- {tool}")
        lines.append("")
        return "\n".join(lines)

    def get_skill_for_file(
        self, filepath: str, skills: List[SkillManifest]
    ) -> Optional[SkillManifest]:
        """Get the most relevant skill for a file path."""
        filepath_lower = filepath.lower()

        # Extension matching
        ext = filepath_lower.split(".")[-1] if "." in filepath else ""

        for skill in skills:
            # Direct extension match in skill name
            if ext and skill.name == ext:
                return skill

            # Check if skill handles this extension
            if ext and f".{ext}" in skill.description.lower():
                return skill

            # Check tags
            if ext in skill.tags:
                return skill

        return None


class AutoSkillSelector:
    """Automatically selects relevant skills based on task context."""

    def __init__(self, registry: "SkillRegistry"):
        self.registry = registry

    def select(self, task: str, filepath: Optional[str] = None) -> List[SkillManifest]:
        """Automatically select skills for a task.

        Args:
            task: The task description
            filepath: Optional file path to consider

        Returns:
            List of relevant skills
        """
        selected = []
        task_lower = task.lower()
        for skill in self.registry.find_for_task(
            task_lower, filepath=filepath, active_only=False
        ):
            if skill not in selected:
                selected.append(skill)
        return selected[:5]


class SkillPromptBuilder:
    """Convenience builder for constructing prompts with skills."""

    def __init__(self, registry: "SkillRegistry"):
        self.registry = registry
        self.injector = SkillInjector()
        self.selector = AutoSkillSelector(registry)
        self._skills: List[SkillManifest] = []

    def with_skill(self, name: str) -> SkillPromptBuilder:
        """Add a skill by name."""
        skill = self.registry.get(name)
        if skill and skill not in self._skills:
            self._skills.append(skill)
        return self

    def with_skills_for_task(
        self, task: str, filepath: Optional[str] = None
    ) -> SkillPromptBuilder:
        """Auto-select skills for a task."""
        skills = self.selector.select(task, filepath)
        for skill in skills:
            if skill not in self._skills:
                self._skills.append(skill)
        return self

    def build(self, base_prompt: str, task: str = "") -> str:
        """Build the final prompt."""
        context = PromptContext(task=task)
        return self.injector.build_system_prompt(base_prompt, self._skills, context)

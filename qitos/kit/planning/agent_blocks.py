"""High-value building blocks for AgentModule implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from qitos.core.decision import Decision
from qitos.engine.parser import Parser
from qitos.kit.prompts import render_prompt


@dataclass
class ToolAwareMessageBuilder:
    """Build stable LLM messages with tool schema and scratchpad context."""

    system_template: str
    max_history_items: int = 8

    def build(
        self,
        task: str,
        tool_registry: Any,
        scratchpad: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        tool_schema = tool_registry.get_tool_descriptions() if tool_registry is not None else ""
        system_prompt = render_prompt(self.system_template, {"tool_schema": tool_schema})

        lines = [f"Task: {task}"]
        if scratchpad:
            lines.append("\nScratchpad:")
            lines.extend(scratchpad[-self.max_history_items :])
        if extra:
            lines.append("\nContext:")
            for k, v in extra.items():
                lines.append(f"- {k}: {v}")

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(lines)},
        ]

    def build_from_observation(
        self,
        observation: Dict[str, Any],
        tool_registry: Any,
        task_key: str = "task",
        scratchpad_key: str = "scratchpad",
        include_memory: bool = True,
    ) -> List[Dict[str, str]]:
        """Convert a structured observation dict to stable LLM messages."""
        task = str(observation.get(task_key, ""))
        raw_scratchpad = observation.get(scratchpad_key)
        scratchpad = raw_scratchpad if isinstance(raw_scratchpad, list) else None

        extra: Dict[str, Any] = {
            k: v for k, v in observation.items() if k not in {task_key, scratchpad_key}
        }
        if include_memory and isinstance(observation.get("memory"), dict):
            memory_block = observation["memory"]
            extra.setdefault("memory_summary", memory_block.get("summary", ""))
            extra.setdefault("memory_records", memory_block.get("records", []))

        return self.build(
            task=task,
            tool_registry=tool_registry,
            scratchpad=scratchpad,
            extra=extra,
        )


@dataclass
class LLMDecisionBlock:
    """Call LLM and parse into Decision with safe fallback behavior."""

    llm: Any
    parser: Parser[Any]
    fallback_to_final: bool = True

    def decide(self, messages: List[Dict[str, str]]) -> Decision[Any]:
        raw = self.llm(messages)
        try:
            return self.parser.parse(raw)
        except Exception:
            if self.fallback_to_final:
                return Decision.final(str(raw).strip())
            raise


__all__ = ["ToolAwareMessageBuilder", "LLMDecisionBlock"]

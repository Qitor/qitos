"""Handoff tool: auto-generated tool that triggers a Decision.handoff().

When an agent declares `handoff_targets`, the Engine registers one
HandoffTool per target. The LLM can then call `transfer_to_{target}`
to hand off control to another agent.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from ...core.tool import BaseTool, ToolSpec
from .agent.durable_adapter import _work_effect, submit_durable_work


class HandoffTool(BaseTool):
    """Tool that signals a handoff to another agent.

    When the LLM calls this tool, the Engine intercepts the action
    and converts it to a `Decision.handoff(target=...)` instead of
    executing it as a normal tool.
    """

    def __init__(
        self,
        target_name: str,
        target_description: str = "",
        input_filter: Callable[[List[Any]], List[Any]] | None = None,
    ) -> None:
        self.target_name = target_name
        self._input_filter = input_filter
        _description = f"Transfer control to the {target_name} agent. {target_description}".strip()
        spec = ToolSpec(
            name=f"transfer_to_{target_name}",
            description=_description,
            parameters={
                "rationale": {
                    "type": "string",
                    "description": "Brief explanation of why this handoff is needed.",
                },
            },
            required=[],
            read_only=False,
            effect=_work_effect("handoff"),
        )
        super().__init__(spec)
        # Override BaseTool's auto-description from execute() docstring
        self.spec.description = _description

    def execute(self, args: Any, runtime_context: Any = None) -> Dict[str, Any]:
        """Declare a durable handoff through the canonical work runtime."""
        rationale = args.get("rationale", "") if isinstance(args, dict) else ""
        durable = submit_durable_work(
            "handoff",
            {"target": self.target_name, "rationale": rationale},
            runtime_context,
        )
        return durable

    @property
    def input_filter(self) -> Callable[[List[Any]], List[Any]] | None:
        return self._input_filter

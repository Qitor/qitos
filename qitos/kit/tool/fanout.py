"""Model adapter for canonical durable fan-out."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ...core.agent_spec import AgentRegistry
from ...core.tool import BaseTool, ToolSpec
from .agent.durable_adapter import _work_effect, submit_durable_work


# Compatibility import only. Depth admission is owned by WorkRuntimePolicy.
MAX_DELEGATE_DEPTH = 3


class FanOutTool(BaseTool):
    """Declare parallel child work through the Session-owned DurableWorkRuntime."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        max_workers: int = 4,
        per_task_timeout: float = 120.0,
    ) -> None:
        self.agent_registry = agent_registry
        # Retained constructor fields ease migration; scheduling is runtime-owned.
        self._max_workers = max_workers
        self._per_task_timeout = per_task_timeout
        super().__init__(
            ToolSpec(
                name="fanout",
                description="Declare multiple supervised durable child tasks.",
                parameters={
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "agent": {"type": "string"},
                                "task": {"type": "string"},
                            },
                            "required": ["agent", "task"],
                        },
                    },
                },
                required=["tasks"],
                timeout_s=300.0,
                max_retries=0,
                supports_background=True,
                effect=_work_effect("fan_out"),
            )
        )

    def execute(
        self,
        args: Dict[str, Any],
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raw_tasks = args.get("tasks")
        if not isinstance(raw_tasks, list) or not raw_tasks:
            return {
                "status": "error",
                "error_code": "invalid_work_request",
                "message": "tasks is required and must be non-empty",
                "outcome_unknown": False,
            }
        tasks: list[dict[str, str]] = []
        for item in raw_tasks:
            if not isinstance(item, dict):
                return self._invalid_child()
            agent = str(item.get("agent", "")).strip()
            task = str(item.get("task", "")).strip()
            if not agent or not task:
                return self._invalid_child()
            tasks.append({"agent": agent, "task": task})
        return submit_durable_work("fan_out", {"tasks": tasks}, runtime_context)

    @staticmethod
    def _invalid_child() -> Dict[str, Any]:
        return {
            "status": "error",
            "error_code": "invalid_work_request",
            "message": "each child requires non-empty agent and task fields",
            "outcome_unknown": False,
        }

    def _run_sub_agent(self, *args: Any, **kwargs: Any) -> None:
        """Rejected compatibility seam; fan-out is runtime-owned."""
        _ = args, kwargs
        raise RuntimeError("legacy_nested_execution_removed: use Session.submit_work")

    def _build_sub_trace_writer(self, *args: Any, **kwargs: Any) -> None:
        """Rejected compatibility seam; child traces are runtime-owned."""
        _ = args, kwargs
        raise RuntimeError("legacy_nested_execution_removed: use Session.submit_work")


__all__ = ["FanOutTool", "MAX_DELEGATE_DEPTH"]

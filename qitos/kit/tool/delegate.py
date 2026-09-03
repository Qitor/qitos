"""Model adapter for canonical durable delegation."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ...core.agent_spec import AgentRegistry, AgentSpec
from ...core.tool import BaseTool, ToolSpec
from .agent.durable_adapter import _work_effect, submit_durable_work


# Compatibility import only. Depth admission is owned by WorkRuntimePolicy.
MAX_DELEGATE_DEPTH = 3


class DelegateTool(BaseTool):
    """Declare delegated work through the Session-owned DurableWorkRuntime."""

    def __init__(self, spec: AgentSpec, agent_registry: AgentRegistry):
        self.agent_spec = spec
        self.agent_registry = agent_registry
        self._execution_context = ""
        public_name = str(spec.tool_name or "").strip() or f"delegate_to_{spec.name}"
        super().__init__(
            ToolSpec(
                name=public_name,
                description=spec.description,
                parameters={
                    "task": {
                        "type": "string",
                        "description": "Subtask to declare for the target agent",
                    },
                },
                required=["task"],
                timeout_s=120.0,
                max_retries=0,
                effect=_work_effect("delegate"),
            )
        )
        self.spec.description = spec.description

    def execute(
        self,
        args: Dict[str, Any],
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        task = str(args.get("task", "")).strip()
        if not task:
            return {
                "status": "error",
                "error_code": "invalid_work_request",
                "message": "task is required",
                "outcome_unknown": False,
            }
        return submit_durable_work(
            "delegate",
            {"agent": self.agent_spec.name, "task": task},
            runtime_context,
        )

    def _build_sub_engine(self, *args: Any, **kwargs: Any) -> None:
        """Rejected compatibility seam; nested engines are no longer canonical."""
        _ = args, kwargs
        raise RuntimeError("legacy_nested_execution_removed: use Session.submit_work")

    def _build_sub_trace_writer(self, *args: Any, **kwargs: Any) -> None:
        """Rejected compatibility seam; child traces are runtime-owned."""
        _ = args, kwargs
        raise RuntimeError("legacy_nested_execution_removed: use Session.submit_work")


__all__ = ["DelegateTool", "MAX_DELEGATE_DEPTH"]

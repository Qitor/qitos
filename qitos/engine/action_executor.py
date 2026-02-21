"""Action executor for QitOS."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from ..core.action import Action, ActionExecutionPolicy, ActionResult, ActionStatus
from ..core.env import Env


class ActionExecutor:
    """Executes normalized actions against a tool registry."""

    def __init__(self, tool_registry: Any, policy: Optional[ActionExecutionPolicy] = None):
        self.tool_registry = tool_registry
        self.policy = policy or ActionExecutionPolicy()

    def execute(self, actions: Sequence[Action], env: Optional[Env] = None, state: Any = None) -> List[ActionResult]:
        if self.policy.mode == "parallel":
            # Kept serial for now; deterministic behavior is preferred for reproducibility.
            return [self._execute_one(action, env=env, state=state) for action in actions]
        return [self._execute_one(action, env=env, state=state) for action in actions]

    def _execute_one(self, action: Action, env: Optional[Env] = None, state: Any = None) -> ActionResult:
        start = time.monotonic()
        attempts = 0
        last_error = None
        tool_meta = self._tool_meta(action.name)

        while attempts <= action.max_retries:
            attempts += 1
            try:
                output = self._call_tool(action, env=env, state=state)
                latency = (time.monotonic() - start) * 1000
                return ActionResult(
                    name=action.name,
                    status=ActionStatus.SUCCESS,
                    output=output,
                    action_id=action.action_id,
                    attempts=attempts,
                    latency_ms=latency,
                    metadata={
                        **tool_meta,
                        "error_category": None,
                    },
                )
            except Exception as exc:  # pragma: no cover - defensive path
                last_error = str(exc)
                if attempts > action.max_retries:
                    break

        latency = (time.monotonic() - start) * 1000
        error_category = "runtime_error"
        if last_error and "not found" in last_error.lower():
            error_category = "tool_not_found"
        return ActionResult(
            name=action.name,
            status=ActionStatus.ERROR,
            error=last_error or "unknown action execution error",
            action_id=action.action_id,
            attempts=attempts,
            latency_ms=latency,
            metadata={
                **tool_meta,
                "error_category": error_category,
            },
        )

    def _call_tool(self, action: Action, env: Optional[Env] = None, state: Any = None) -> Any:
        required_ops = self._required_ops(action.name)
        runtime_context = {"env": env, "state": state, "ops": self._resolve_ops(required_ops, env)}
        if hasattr(self.tool_registry, "call"):
            return self.tool_registry.call(action.name, runtime_context=runtime_context, **action.args)

        # Fallback protocol for custom registries.
        if hasattr(self.tool_registry, "get"):
            tool = self.tool_registry.get(action.name)
            if tool is None:
                raise ValueError(f"Unknown tool: {action.name}")
            if hasattr(tool, "execute"):
                return tool.execute(action.args, runtime_context=runtime_context)
            if hasattr(tool, "run"):
                return tool.run(**action.args)
            return tool(**action.args)

        raise TypeError("Unsupported tool registry. Expected object with call() or get().")

    def _required_ops(self, name: str) -> List[str]:
        if hasattr(self.tool_registry, "get"):
            try:
                tool = self.tool_registry.get(name)
                if tool is not None and hasattr(tool, "spec"):
                    spec = getattr(tool, "spec")
                    if hasattr(spec, "required_ops"):
                        value = getattr(spec, "required_ops")
                        if isinstance(value, list):
                            return [str(x) for x in value]
            except Exception:
                return []
        return []

    def _resolve_ops(self, required_ops: List[str], env: Optional[Env]) -> Dict[str, Any]:
        if not required_ops:
            return {}
        if env is None:
            raise ValueError(f"Tool requires ops {required_ops} but no env was provided")
        out: Dict[str, Any] = {}
        for group in required_ops:
            ops = env.get_ops(group)
            if ops is None:
                raise ValueError(f"Env '{getattr(env, 'name', 'env')}' missing required ops group: {group}")
            out[group] = ops
        return out

    def _tool_meta(self, name: str) -> dict[str, Any]:
        if hasattr(self.tool_registry, "describe_tool"):
            try:
                desc = self.tool_registry.describe_tool(name)
                origin = desc.get("origin", {})
                return {
                    "tool_name": desc.get("name", name),
                    "toolset_name": origin.get("toolset_name"),
                    "toolset_version": origin.get("toolset_version"),
                    "source": origin.get("source", "function"),
                }
            except Exception:
                pass
        return {"tool_name": name, "toolset_name": None, "toolset_version": None, "source": "unknown"}

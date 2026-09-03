"""Thin model-tool adapter for the engine-owned durable work runtime."""

from __future__ import annotations

import json
from typing import Any, Mapping
from uuid import uuid4

from ....core.tool import BaseTool, ToolSpec
from ....core.tool_runtime import ToolEffectDeclaration


def _work_effect(operation: str):
    def declare(args: dict[str, Any], context: dict[str, Any]) -> ToolEffectDeclaration:
        return ToolEffectDeclaration(
            effect_ref=f"durable-work:{operation}",
            metadata={"operation": operation},
        )
    return declare


def submit_durable_work(
    operation: str,
    payload: Mapping[str, Any],
    runtime_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Submit only through Session's canonical DurableWorkRuntime seam."""
    context = runtime_context or {}
    runtime = context.get("work_runtime")
    session = context.get("session")
    if runtime is None or session is None:
        return {
            "status": "error",
            "error_code": "durable_work_runtime_unavailable",
            "message": "durable work runtime is unavailable",
            "outcome_unknown": False,
        }
    canonical = json.loads(json.dumps(dict(payload), sort_keys=True, allow_nan=False))
    supplied = context.get("idempotency_key") or context.get("slot_id")
    if supplied:
        operation_id = f"{operation}:{supplied}"
    else:
        operation_id = f"{operation}:{uuid4().hex}"
    del runtime
    receipt = session.submit_work(
        operation,
        canonical,
        operation_id=operation_id,
    )
    return {
        "status": receipt.state,
        "operation_id": receipt.operation_id,
        "operation": receipt.operation,
        "payload_digest": receipt.payload_digest,
        "generation": receipt.generation,
        "attempt": receipt.attempt,
        "worker_ref": receipt.worker_ref,
        "outcome_unknown": receipt.outcome_unknown,
        "terminal_receipt_ref": receipt.terminal_receipt_ref,
    }


class SpawnTool(BaseTool):
    """Model-callable detached child declaration over the durable runtime."""

    def __init__(self) -> None:
        super().__init__(
            ToolSpec(
                name="spawn",
                description="Declare a supervised detached durable child.",
                parameters={
                    "agent": {"type": "string"},
                    "task": {"type": "string"},
                },
                required=["agent", "task"],
                effect=_work_effect("spawn"),
            )
        )

    def execute(self, args: Any, runtime_context: Any = None) -> dict[str, Any]:
        payload = {
            "agent": str(args.get("agent", "")),
            "task": str(args.get("task", "")),
        }
        durable = submit_durable_work("spawn", payload, runtime_context)
        return durable


class JoinTool(BaseTool):
    """Model-callable durable join declaration."""

    def __init__(self) -> None:
        super().__init__(
            ToolSpec(
                name="join",
                description="Declare a deterministic join over durable child identities.",
                parameters={
                    "children": {"type": "array", "items": {"type": "string"}},
                    "policy": {
                        "type": "string",
                        "enum": ["all", "all_successful", "first_success", "quorum"],
                    },
                    "quorum": {"type": "integer", "nullable": True},
                    "reducer_ref": {"type": "string", "nullable": True},
                    "reducer_digest": {"type": "string", "nullable": True},
                },
                required=["children", "policy"],
                effect=_work_effect("join"),
            )
        )

    def execute(self, args: Any, runtime_context: Any = None) -> dict[str, Any]:
        payload = {
            "children": list(args.get("children", [])),
            "policy": str(args.get("policy", "all")),
            "quorum": args.get("quorum"),
            "reducer_ref": args.get("reducer_ref"),
            "reducer_digest": args.get("reducer_digest"),
        }
        durable = submit_durable_work("join", payload, runtime_context)
        return durable


__all__ = ["JoinTool", "SpawnTool", "submit_durable_work"]

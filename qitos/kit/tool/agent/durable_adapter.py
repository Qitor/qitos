"""Thin model-tool adapter for the engine-owned durable work runtime."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from ....core.tool import BaseTool, ToolSpec


def submit_durable_work(
    operation: str,
    payload: Mapping[str, Any],
    runtime_context: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Submit through the Session/runtime seam, or return None for legacy mode."""
    context = runtime_context or {}
    runtime = context.get("work_runtime")
    session = context.get("session")
    graph = context.get("work_graph")
    if runtime is None or session is None or graph is None:
        return None
    canonical = json.loads(json.dumps(dict(payload), sort_keys=True, allow_nan=False))
    supplied = context.get("idempotency_key") or context.get("slot_id")
    if supplied:
        operation_id = f"{operation}:{supplied}"
    else:
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        operation_id = f"{operation}:{digest}"
    del runtime, graph
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
            )
        )

    def execute(self, args: Any, runtime_context: Any = None) -> dict[str, Any]:
        payload = {
            "agent": str(args.get("agent", "")),
            "task": str(args.get("task", "")),
        }
        durable = submit_durable_work("spawn", payload, runtime_context)
        return durable or {
            "status": "error",
            "message": "durable work runtime is unavailable",
        }


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
        return durable or {
            "status": "error",
            "message": "durable work runtime is unavailable",
        }


__all__ = ["JoinTool", "SpawnTool", "submit_durable_work"]

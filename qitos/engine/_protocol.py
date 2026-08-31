"""Structural Engine contract used by private runtime helpers.

The runtime helpers are split out of :mod:`qitos.engine.engine` to keep the
kernel reviewable. This protocol records the Engine state they are allowed to
share without importing ``Engine`` back into those helpers and creating a
circular dependency.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class _EngineProtocol(Protocol):
    """Internal Engine surface consumed by runtime components."""

    agent: Any
    budget: Any
    context_config: Any
    executor: Any
    env: Optional[Any]
    records: List[Any]
    events: List[Any]
    auto_approve: bool
    critics: List[Any]
    stop_criteria: List[Any]
    recovery_handler: Any
    recovery_policy: Any
    hooks: List[Any]
    trace_writer: Any
    tool_registry: Any
    parser: Any
    protocol: Any
    search: Any
    branch_selector: Any
    history_policy: Any
    runtime: Any

    _active_run_id: str
    _active_task: str
    _active_task_obj: Any
    _active_state: Any
    _last_system_prompt: str
    _last_prompt_metadata: Dict[str, Any]
    _token_usage: int
    _last_context_telemetry: Dict[str, Any]
    _last_env_observation: Any
    _last_env_result: Any
    _critic_modified_prompt: Optional[str]
    _critic_instruction_patch: Optional[str]
    _tool_loop_detector: Any
    _handoff_history: List[str]
    _runtime_history: Any
    _resolved_protocol_source: str
    _context_runtime: Any
    _trace_runtime: Any
    _session_handle: Any
    _session_run_id: str
    _qitos_exchange_log: Any
    _qitos_steering_receipts: Any
    _qitos_tool_batch_snapshot: Any
    _qitos_restored_conversation_pending: bool

    def _dispatch_hook(self, method_name: str, ctx: Any) -> None:
        ...

    def _hook_context(self, **kwargs: Any) -> Any:
        ...

    def _emit(
        self,
        step_id: int,
        phase: Any,
        ok: bool = True,
        payload: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        ...

    def _memory_append(
        self,
        role: str,
        content: Any,
        step_id: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        ...

    def _memory(self) -> Any:
        ...

    def _history(self) -> Any:
        ...

    def _history_append(
        self,
        role: str,
        content: Any,
        step_id: int,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
        native_items: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        ...

    def _intercept_handoff_action(self, action: Any) -> Optional[Any]:
        ...

    def _run_env_step(
        self, decision: Any, action_results: List[Any]
    ) -> Optional[Any]:
        ...

    def _env_step_result_to_dict(
        self, result: Optional[Any]
    ) -> Optional[Dict[str, Any]]:
        ...

    def _env_identity(self) -> Dict[str, Any]:
        ...

    def _estimate_tokens(self, payload: Any) -> int:
        ...

    def _normalize_history_messages(self, payload: Any) -> List[Dict[str, Any]]:
        ...

    def _compute_state_diff(
        self, before: Dict[str, Any], after: Dict[str, Any]
    ) -> Dict[str, Any]:
        ...

    def resolve_protocol(self) -> Any:
        ...

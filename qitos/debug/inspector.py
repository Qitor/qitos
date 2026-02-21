"""Inspector payload helpers derived from canonical trace fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class InspectorPayload:
    step_id: int
    rationale: Optional[str]
    decision_mode: Optional[str]
    actions: list[Any]
    tool_invocations: list[Any]
    action_results: list[Any]
    critic_outputs: list[Any]
    state_diff: Dict[str, Any]
    stop_reason: Optional[str]
    remediation_hint: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "rationale": self.rationale,
            "decision_mode": self.decision_mode,
            "actions": self.actions,
            "tool_invocations": self.tool_invocations,
            "action_results": self.action_results,
            "critic_outputs": self.critic_outputs,
            "state_diff": self.state_diff,
            "stop_reason": self.stop_reason,
            "remediation_hint": self.remediation_hint,
        }


def build_inspector_payload(step: Dict[str, Any], manifest: Optional[Dict[str, Any]] = None) -> InspectorPayload:
    decision = step.get("decision") or {}
    stop_reason = None
    if isinstance(manifest, dict):
        summary = manifest.get("summary", {})
        if isinstance(summary, dict):
            stop_reason = summary.get("stop_reason")

    return InspectorPayload(
        step_id=int(step.get("step_id", -1)),
        rationale=decision.get("rationale") if isinstance(decision, dict) else None,
        decision_mode=decision.get("mode") if isinstance(decision, dict) else None,
        actions=list(step.get("actions", []) or []),
        tool_invocations=list(step.get("tool_invocations", []) or []),
        action_results=list(step.get("action_results", []) or []),
        critic_outputs=list(step.get("critic_outputs", []) or []),
        state_diff=dict(step.get("state_diff", {}) or {}),
        stop_reason=stop_reason,
        remediation_hint=_build_remediation_hint(step),
    )


def compare_steps(base_step: Dict[str, Any], other_step: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact comparison payload for two step snapshots."""
    fields = ["decision", "actions", "action_results", "critic_outputs", "state_diff"]
    diff: Dict[str, Any] = {"step_a": base_step.get("step_id"), "step_b": other_step.get("step_id"), "changes": {}}
    for field in fields:
        a = base_step.get(field)
        b = other_step.get(field)
        if a != b:
            diff["changes"][field] = {"a": a, "b": b}
    return diff


__all__ = ["InspectorPayload", "build_inspector_payload", "compare_steps"]


def _build_remediation_hint(step: Dict[str, Any]) -> Optional[str]:
    invocations = step.get("tool_invocations", []) or []
    for item in invocations:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "error":
            category = item.get("error_category")
            if category == "tool_not_found":
                return "Verify tool registration and action name."
            if category == "runtime_error":
                return "Inspect tool arguments and environment configuration."
    return None

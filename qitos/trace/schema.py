"""Trace schema validator for required fields."""

from __future__ import annotations

from typing import Any, Dict, Iterable


class TraceSchemaValidator:
    REQUIRED_MANIFEST_FIELDS = {
        "schema_version",
        "run_id",
        "status",
        "step_count",
        "event_count",
        "summary",
        "model_id",
        "prompt_hash",
        "tool_versions",
        "seed",
        "run_config_hash",
    }
    REQUIRED_EVENT_FIELDS = {"step_id", "phase", "ok", "ts"}
    REQUIRED_STEP_FIELDS = {
        "step_id",
        "observation",
        "decision",
        "actions",
        "action_results",
        "tool_invocations",
        "critic_outputs",
        "state_diff",
    }
    REQUIRED_SUMMARY_FIELDS = {"stop_reason", "final_result", "steps", "failure_report"}

    def validate_manifest(self, manifest: Dict[str, Any]) -> None:
        self._require(manifest, self.REQUIRED_MANIFEST_FIELDS, "manifest")
        summary = manifest.get("summary", {})
        if not isinstance(summary, dict):
            raise ValueError("manifest.summary must be a dict")
        self._require(summary, self.REQUIRED_SUMMARY_FIELDS, "manifest.summary")

    def validate_events(self, events: Iterable[Dict[str, Any]]) -> None:
        for idx, event in enumerate(events):
            self._require(event, self.REQUIRED_EVENT_FIELDS, f"event[{idx}]")

    def validate_steps(self, steps: Iterable[Dict[str, Any]]) -> None:
        for idx, step in enumerate(steps):
            self._require(step, self.REQUIRED_STEP_FIELDS, f"step[{idx}]")

    def _require(self, payload: Dict[str, Any], required: set[str], name: str) -> None:
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"{name} missing required fields: {missing}")

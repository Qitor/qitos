"""Compact, append-only canonical trajectory storage.

The canonical trace is deliberately independent from any chat template or
training framework.  It stores each provider-visible message and tool schema
once, then references them from request/response/tool-result records.  This
keeps live traces tail-able while avoiding repeated full conversation snapshots.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


TRAJECTORY_SCHEMA = "qitos.trajectory.v1"
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|credential|password|secret|access[_-]?token|"
    r"refresh[_-]?token|cookie|private[_-]?key|endpoint|base[_-]?url|server[_-]?url)",
    re.IGNORECASE,
)
_HOST_PATH = re.compile(r"/(?:home|data\d*|inspire)/[^\s'\"`<>()\[\]{}]+")
_BEARER = re.compile(r"(?i)\bBearer\s+\S+")
_URL_AUTH = re.compile(r"https?://[^\s/@]+:[^\s/@]+@", re.IGNORECASE)
_TOKEN = re.compile(r"\b(?:hf|sk|rk)_[A-Za-z0-9_-]{12,}\b")


@dataclass(frozen=True)
class TraceStorageConfig:
    """Persistence policy for :class:`TraceWriter`.

    ``capture_debug_artifacts`` is intentionally opt-in.  It retains the
    historical events/steps files for a short diagnostic run, while the
    canonical JSONL remains the source of truth in both modes.
    """

    capture_debug_artifacts: bool = False
    flush_every: int = 1


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def safe_projection(value: Any, key: str = "") -> Any:
    """Return a JSON-safe public projection with secrets and host paths removed."""
    if _SENSITIVE_KEY.search(str(key)):
        return "[REDACTED]"
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        return {str(k): safe_projection(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_projection(item) for item in value]
    if isinstance(value, str):
        value = _BEARER.sub("Bearer [REDACTED]", value)
        value = _URL_AUTH.sub("https://[REDACTED]@", value)
        value = _TOKEN.sub("[REDACTED]", value)
        return _HOST_PATH.sub("[HOST_PATH_OMITTED]", value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CanonicalTrajectoryWriter:
    """Append-only writer for one compact provider/tool trajectory."""

    def __init__(
        self,
        path: str | Path,
        *,
        run_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        flush_every: int = 1,
    ) -> None:
        self.path = Path(path)
        self.run_id = str(run_id)
        self.metadata = dict(metadata or {})
        self.flush_every = max(1, int(flush_every or 1))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")
        self._pending = 0
        self._sequence = 0
        self._message_ids: Dict[str, str] = {}
        self._schema_ids: Dict[str, str] = {}
        self._turns: Dict[int, str] = {}
        self._record_count = 0
        self._header_written = False
        self._footer_written = False
        self._digest = hashlib.sha256()

    @property
    def record_count(self) -> int:
        return self._record_count

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest()

    def start(self) -> None:
        if self._header_written:
            return
        self._header_written = True
        self._append(
            {
                "record_type": "header",
                "schema": TRAJECTORY_SCHEMA,
                "run_id": self.run_id,
                "created_at": _utc_now(),
                "provenance": self._safe_provenance(),
            }
        )

    def record_model_request(
        self,
        *,
        step_id: int,
        messages: Iterable[Dict[str, Any]],
        tools: Iterable[Dict[str, Any]] | None,
        protocol: str = "",
    ) -> str:
        self.start()
        message_ids = [self._intern_message(message) for message in messages]
        schema_id = self._intern_tool_schema(list(tools or []))
        turn_id = f"turn:{int(step_id)}"
        self._turns[int(step_id)] = turn_id
        self._append(
            {
                "record_type": "turn",
                "state": "requested",
                "turn_id": turn_id,
                "step_id": int(step_id),
                "timestamp": _utc_now(),
                "request_message_ids": message_ids,
                "tool_schema_id": schema_id,
                "protocol": str(protocol or ""),
            }
        )
        return turn_id

    def record_model_response(
        self,
        *,
        step_id: int,
        assistant_message: Dict[str, Any],
        finish_reason: str | None = None,
        usage: Optional[Dict[str, Any]] = None,
        model_name: str | None = None,
        provider: str | None = None,
        reasoning_content: str | None = None,
        reasoning_fields: Optional[Dict[str, str]] = None,
        reasoning_source: str | None = None,
    ) -> None:
        self.start()
        turn_id = self._turns.setdefault(int(step_id), f"turn:{int(step_id)}")
        message_id = self._intern_message(assistant_message)
        self._append(
            {
                "record_type": "model_response",
                "turn_id": turn_id,
                "step_id": int(step_id),
                "timestamp": _utc_now(),
                "assistant_message_id": message_id,
                "finish_reason": str(finish_reason or ""),
                "usage": safe_projection(dict(usage or {}), "usage"),
                "model": {"name": str(model_name or ""), "provider": str(provider or "")},
                "reasoning_content": safe_projection(str(reasoning_content or ""), "reasoning_content"),
                "reasoning_fields": {
                    str(key): safe_projection(str(value), str(key))
                    for key, value in dict(reasoning_fields or {}).items()
                    if isinstance(value, str) and value.strip()
                },
                "reasoning_source": str(reasoning_source or ""),
            }
        )

    def record_model_tool_calls(
        self,
        *,
        step_id: int,
        tool_calls: Iterable[Dict[str, Any]],
    ) -> None:
        """Amend a response with calls recovered by a text protocol parser.

        Native providers put their calls in ``model_response`` directly.  A
        few generic QitOS agents still derive actions from text; recording the
        normalized calls separately keeps the canonical transaction complete
        without pretending that they came from the provider.
        """
        calls = [safe_projection(dict(item), "tool_call") for item in tool_calls if isinstance(item, dict)]
        if not calls:
            return
        self.start()
        self._append(
            {
                "record_type": "parsed_tool_calls",
                "turn_id": self._turns.setdefault(int(step_id), f"turn:{int(step_id)}"),
                "step_id": int(step_id),
                "timestamp": _utc_now(),
                "tool_calls": calls,
            }
        )

    def record_tool_result(
        self,
        *,
        step_id: int,
        tool_call_id: str,
        tool_name: str,
        content: Any,
        status: str,
        latency_ms: Any = None,
        attempts: Any = None,
        error: str | None = None,
    ) -> None:
        self.start()
        turn_id = self._turns.setdefault(int(step_id), f"turn:{int(step_id)}")
        message = {
            "role": "tool",
            "tool_call_id": str(tool_call_id),
            "name": str(tool_name),
            "content": content,
        }
        message_id = self._intern_message(message)
        self._append(
            {
                "record_type": "tool_result",
                "turn_id": turn_id,
                "step_id": int(step_id),
                "timestamp": _utc_now(),
                "tool_call_id": str(tool_call_id),
                "tool_name": str(tool_name),
                "message_id": message_id,
                "execution": {
                    "status": str(status),
                    "latency_ms": latency_ms,
                    "attempts": attempts,
                    "error": safe_projection(str(error or ""), "error"),
                },
            }
        )

    def record_diagnostic(
        self, *, step_id: int, code: str, detail: Optional[Dict[str, Any]] = None
    ) -> None:
        self.start()
        self._append(
            {
                "record_type": "diagnostic",
                "step_id": int(step_id),
                "timestamp": _utc_now(),
                "code": str(code),
                "detail": safe_projection(dict(detail or {})),
            }
        )

    def finalize(self, summary: Optional[Dict[str, Any]] = None) -> None:
        self.start()
        if not self._footer_written:
            self._footer_written = True
            self._append(
                {
                    "record_type": "footer",
                    "run_id": self.run_id,
                    "completed_at": _utc_now(),
                    "summary": safe_projection(dict(summary or {})),
                }
            )
        self.flush()
        self._fh.close()

    def flush(self) -> None:
        if self._fh.closed:
            return
        self._fh.flush()
        self._pending = 0

    def _safe_provenance(self) -> Dict[str, Any]:
        allowed = {
            "model_id", "prompt_hash", "seed", "run_config_hash", "git_sha",
            "package_version", "benchmark_name", "benchmark_split", "model_family",
            "prompt_protocol", "parser_name", "agent_name", "official_run",
        }
        return {
            key: safe_projection(self.metadata.get(key), key)
            for key in sorted(allowed)
            if self.metadata.get(key) not in (None, "", [], {})
        }

    def _intern_message(self, message: Dict[str, Any]) -> str:
        value = safe_projection(dict(message or {}), "message")
        encoded = canonical_json(value)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        existing = self._message_ids.get(digest)
        if existing:
            return existing
        message_id = f"message:{digest[:20]}"
        self._message_ids[digest] = message_id
        self._append({"record_type": "message", "message_id": message_id, "message": value})
        return message_id

    def _intern_tool_schema(self, tools: List[Dict[str, Any]]) -> str:
        value = safe_projection(tools, "tools")
        encoded = canonical_json(value)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        existing = self._schema_ids.get(digest)
        if existing:
            return existing
        schema_id = f"tools:{digest[:20]}"
        self._schema_ids[digest] = schema_id
        self._append(
            {
                "record_type": "tool_schema",
                "tool_schema_id": schema_id,
                "sha256": digest,
                "tools": value,
            }
        )
        return schema_id

    def _append(self, record: Dict[str, Any]) -> None:
        self._sequence += 1
        payload = {"sequence": self._sequence, **safe_projection(record)}
        line = canonical_json(payload) + "\n"
        self._fh.write(line)
        self._digest.update(line.encode("utf-8"))
        self._record_count += 1
        self._pending += 1
        if self._pending >= self.flush_every:
            self.flush()


class CanonicalTraceReader:
    """Read and reconstruct canonical traces without a training-template dependency."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def turns(self) -> List[Dict[str, Any]]:
        return list(self.iter_turns())

    def iter_turns(self) -> Iterable[Dict[str, Any]]:
        """Yield reconstructed turns in append order without loading a run.

        Writer ordering guarantees that message/schema definitions precede the
        turn that references them and that a turn's response/results occur
        before the next request.  This makes training/export pipelines stream
        large trajectories with bounded memory.
        """
        messages: Dict[str, Any] = {}
        schemas: Dict[str, Any] = {}
        current: Dict[str, Any] | None = None

        def materialize(turn: Dict[str, Any]) -> Dict[str, Any]:
            response = dict(turn.get("response") or {})
            assistant_message = messages.get(str(response.get("assistant_message_id")))
            if isinstance(assistant_message, dict) and turn.get("parsed_calls"):
                assistant_message = dict(assistant_message)
                assistant_message["tool_calls"] = list(turn["parsed_calls"])
            return {
                "turn_id": turn.get("turn_id"),
                "step_id": turn.get("step_id"),
                "provider_messages": [messages[item] for item in turn.get("request_message_ids", []) if item in messages],
                "tool_schema": schemas.get(str(turn.get("tool_schema_id")), []),
                "model_response": response,
                "assistant_message": assistant_message,
                "tool_results": [
                    {**result, "message": messages.get(str(result.get("message_id")))}
                    for result in turn.get("tool_results", [])
                ],
            }

        for row in self._iter_records():
            kind = row.get("record_type")
            if kind == "message":
                messages[str(row.get("message_id"))] = row.get("message")
            elif kind == "tool_schema":
                schemas[str(row.get("tool_schema_id"))] = row.get("tools")
            elif kind == "turn":
                if current is not None:
                    yield materialize(current)
                current = dict(row)
                current["tool_results"] = []
            elif current is not None and str(row.get("turn_id")) == str(current.get("turn_id")):
                if kind == "model_response":
                    current["response"] = row
                elif kind == "parsed_tool_calls":
                    current["parsed_calls"] = list(row.get("tool_calls") or [])
                elif kind == "tool_result":
                    current["tool_results"].append(row)
        if current is not None:
            yield materialize(current)

    def footer(self) -> Dict[str, Any]:
        for row in reversed(self._read_records()):
            if row.get("record_type") == "footer":
                return dict(row)
        return {}

    def validate(self, *, require_footer: bool = False) -> None:
        """Validate references without requiring a cleanly completed run.

        A killed worker may legitimately end after a request or tool result;
        all earlier records must still be replayable.  ``require_footer`` is
        therefore reserved for a normal finalized writer.
        """
        records = self._read_records()
        messages = {str(row.get("message_id")) for row in records if row.get("record_type") == "message"}
        schemas = {str(row.get("tool_schema_id")) for row in records if row.get("record_type") == "tool_schema"}
        errors: List[str] = []
        if not any(row.get("record_type") == "header" and row.get("schema") == TRAJECTORY_SCHEMA for row in records):
            errors.append("missing canonical header")
        for row in records:
            kind = row.get("record_type")
            if kind == "turn":
                for message_id in row.get("request_message_ids") or []:
                    if str(message_id) not in messages:
                        errors.append(f"unknown request message {message_id}")
                if str(row.get("tool_schema_id")) not in schemas:
                    errors.append(f"unknown tool schema {row.get('tool_schema_id')}")
            elif kind == "model_response":
                if str(row.get("assistant_message_id")) not in messages:
                    errors.append(f"unknown assistant message {row.get('assistant_message_id')}")
            elif kind == "tool_result":
                if str(row.get("message_id")) not in messages:
                    errors.append(f"unknown tool-result message {row.get('message_id')}")
        if require_footer and not self.footer():
            errors.append("missing canonical footer")
        if errors:
            raise ValueError("invalid canonical trajectory: " + "; ".join(errors[:8]))

    def to_legacy_artifacts(self) -> Dict[str, Any]:
        """Provide a compact compatibility view for replay/evaluation consumers."""
        events: List[Dict[str, Any]] = []
        steps: List[Dict[str, Any]] = []
        for turn in self.turns():
            step_id = int(turn.get("step_id") or 0)
            response = dict(turn.get("model_response") or {})
            events.append({"step_id": step_id, "phase": "DECIDE", "ok": True, "ts": response.get("timestamp"), "payload": {"stage": "model_input", "messages": turn["provider_messages"], "tool_schema": turn["tool_schema"]}})
            if response:
                events.append({"step_id": step_id, "phase": "DECIDE", "ok": True, "ts": response.get("timestamp"), "payload": {"stage": "model_output", "model_response": response, "assistant_message": turn.get("assistant_message")}})
            if turn["tool_results"]:
                events.append({"step_id": step_id, "phase": "ACT", "ok": True, "ts": turn["tool_results"][-1].get("timestamp"), "payload": {"stage": "action_results", "action_results": turn["tool_results"]}})
            steps.append({"step_id": step_id, "observation": None, "decision": None, "actions": [], "action_results": turn["tool_results"], "tool_invocations": [], "critic_outputs": [], "state_diff": {}})
        return {"events": events, "steps": steps}

    def _read_records(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not self.path.is_file():
            return rows
        with self.path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
        return rows

    def _iter_records(self) -> Iterable[Dict[str, Any]]:
        if not self.path.is_file():
            return
        with self.path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    yield item


__all__ = [
    "TRAJECTORY_SCHEMA",
    "TraceStorageConfig",
    "CanonicalTrajectoryWriter",
    "CanonicalTraceReader",
    "safe_projection",
]

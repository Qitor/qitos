"""Thin qita adapter over the lower-level trajectory reader protocol."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote


def default_reader(root: str | Path) -> Any:
    """Return the qualified default: the frozen-trace compatibility reader."""
    from qitos.tracing.readers import TraceCompatibilityReader

    return TraceCompatibilityReader(root)


def candidate_file_reader(path: str | Path) -> Any:
    """Open candidate trajectory bytes without creating or mutating a store."""
    from qitos.tracing.readers import StoreTrajectoryReader
    from qitos.tracing.store import MemoryTrajectoryStore
    from qitos.tracing.trajectory import TrajectoryRecord

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError("candidate_store_unavailable")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("records"), list):
        raise ValueError("candidate_store_invalid")
    records = tuple(
        TrajectoryRecord.from_dict(item)
        for item in value["records"]
        if isinstance(item, dict)
    )
    if len(records) != len(value["records"]):
        raise ValueError("candidate_store_invalid")
    store = MemoryTrajectoryStore(store_id="qitos.qita.read_only_candidate")
    store.append_batch(records)
    return StoreTrajectoryReader(store)


def _portable_asset_refs(payload: Dict[str, Any], run_dir: Path) -> None:
    """Replace host paths with run-scoped portable URLs or an omission marker."""
    run_root = run_dir.resolve()
    run_id = run_dir.name
    for step in payload.get("steps") or []:
        if not isinstance(step, dict):
            continue
        assets = step.get("visual_assets")
        if not isinstance(assets, list):
            continue
        for asset in assets:
            if not isinstance(asset, dict) or not asset.get("path"):
                continue
            raw_path = Path(str(asset.get("path")))
            resolved = (
                raw_path.resolve()
                if raw_path.is_absolute()
                else (run_root / raw_path).resolve()
            )
            try:
                relative = resolved.relative_to(run_root).as_posix()
            except ValueError:
                asset["path"] = "__omitted__"
                asset["asset_status"] = "host_path_rejected"
                continue
            asset["path"] = relative
            asset["asset_url"] = (
                f"/asset?run={quote(run_id)}&path={quote(relative)}"
            )


def load_run_payload(
    reader: Any,
    run_id: str,
    *,
    run_dir: Optional[Path] = None,
    view: Optional[Any] = None,
) -> Dict[str, Any]:
    """Load one qita payload through a structural TrajectoryReader."""
    from qitos.tracing.privacy import project_data
    from qitos.tracing.readers import trajectory_to_qita_payload
    from qitos.tracing.trajectory import PrivacyView

    selected_view = view or PrivacyView.REDACTED_PUBLIC
    raw = reader.read_run(run_id, view=PrivacyView.RAW_PRIVATE)
    payload = trajectory_to_qita_payload(raw)
    if run_dir is not None:
        _portable_asset_refs(payload, run_dir)
    projection = project_data(payload, view=selected_view)
    safe = copy.deepcopy(dict(projection.data or {}))
    meta = safe.get("trajectory_meta")
    if not isinstance(meta, dict):
        meta = {}
        safe["trajectory_meta"] = meta
    meta["privacy_view"] = selected_view.value
    source_loss = raw.loss.merged(projection.loss)
    meta["loss"] = source_loss.to_dict()
    meta["reader_id"] = reader.capabilities.reader_id
    meta["reader_default_qualified"] = bool(
        reader.capabilities.default_qualified
    )
    return safe


def load_session_payload(
    reader: Any,
    session_id: str,
    *,
    view: Optional[Any] = None,
) -> Dict[str, Any]:
    """Inspect a session through readers that declare session-query support."""
    from qitos.tracing.privacy import project_data
    from qitos.tracing.readers import trajectory_to_qita_payload
    from qitos.tracing.trajectory import PrivacyView

    if not reader.capabilities.session_query:
        raise LookupError("session_query_unavailable")
    selected_view = view or PrivacyView.REDACTED_PUBLIC
    raw = reader.read_session(session_id, view=PrivacyView.RAW_PRIVATE)
    payload = trajectory_to_qita_payload(raw)
    projection = project_data(payload, view=selected_view)
    safe = copy.deepcopy(dict(projection.data or {}))
    meta = safe.get("trajectory_meta")
    if not isinstance(meta, dict):
        meta = {}
        safe["trajectory_meta"] = meta
    meta["privacy_view"] = selected_view.value
    meta["loss"] = raw.loss.merged(projection.loss).to_dict()
    meta["reader_id"] = reader.capabilities.reader_id
    meta["session_id"] = session_id
    meta["session_ids"] = list(raw.session_ids)
    meta["run_ids"] = list(raw.run_ids)
    return safe


def discover_run_payloads(
    reader: Any, *, view: Optional[Any] = None
) -> list[Dict[str, Any]]:
    """Discover safe run summaries without exposing reader storage paths."""
    from qitos.tracing.privacy import project_data
    from qitos.tracing.trajectory import PrivacyView

    selected_view = view or PrivacyView.REDACTED_PUBLIC
    output = []
    for summary in reader.discover_runs():
        projection = project_data(summary.to_dict(), view=selected_view)
        value = copy.deepcopy(dict(projection.data or {}))
        value["reader_id"] = reader.capabilities.reader_id
        output.append(value)
    return output


__all__ = [
    "candidate_file_reader",
    "default_reader",
    "discover_run_payloads",
    "load_run_payload",
    "load_session_payload",
]

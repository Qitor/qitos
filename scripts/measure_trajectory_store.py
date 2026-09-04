#!/usr/bin/env python3
"""Reproducible measurements for qualified S4 Lane D fixture workloads."""

from __future__ import annotations

import argparse
import gzip
import json
import platform
import resource
import statistics
import sys
import tempfile
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from qitos.tracing.journal_store import JournalTrajectoryStore
from qitos.tracing.store import MemoryTrajectoryStore
from qitos.tracing.exporter import CanonicalTrajectoryExporter
from qitos.tracing.trajectory import PrivacyView
from qitos.tracing.trajectory import (
    TrajectoryQuery,
    TrajectoryRecord,
    canonical_json_bytes,
)


FIXTURE_SCHEMA = "qitos.s4.lane_d.measurement_fixture/1"
RESULT_SCHEMA = "qitos.s4.lane_d.storage_measurements/1"
REQUIRED_SOURCES = {"coding-tool-agent", "research-tool-agent"}


def _load(path: Path) -> tuple[Dict[str, tuple[TrajectoryRecord, ...]], int]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("measurement_fixture_invalid_json") from exc
    if not isinstance(value, Mapping) or value.get("schema_version") != FIXTURE_SCHEMA:
        raise ValueError("measurement_fixture_schema_invalid")
    if value.get("measurement_only") is not True:
        raise ValueError("measurement_fixture_role_invalid")
    raw_sources = value.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("measurement_sources_invalid")
    sources: Dict[str, tuple[TrajectoryRecord, ...]] = {}
    for source in raw_sources:
        if not isinstance(source, Mapping):
            raise ValueError("measurement_source_invalid")
        name = str(source.get("name", ""))
        raw_records = source.get("records")
        if not isinstance(raw_records, list) or not raw_records:
            raise ValueError("measurement_records_unavailable")
        base_records = tuple(
            TrajectoryRecord.from_dict(item)
            for item in raw_records
            if isinstance(item, Mapping)
        )
        if len(base_records) != len(raw_records):
            raise ValueError("measurement_record_invalid")
        repeat_count = int(source.get("repeat", 1))
        if repeat_count <= 0 or repeat_count > 1_000:
            raise ValueError("measurement_repeat_invalid")
        expanded = []
        for repetition in range(repeat_count):
            for record in base_records:
                cloned = replace(
                    record,
                    record_id=f"{record.record_id}-m{repetition}",
                    sequence=len(expanded),
                    digest="",
                )
                expanded.append(replace(cloned, digest=cloned.compute_digest()))
        sources[name] = tuple(expanded)
    if set(sources) != REQUIRED_SOURCES:
        raise ValueError("measurement_source_set_incomplete")
    return sources, len(raw)


def _time_ns(operation: Any) -> tuple[int, Any]:
    started = time.perf_counter_ns()
    result = operation()
    return time.perf_counter_ns() - started, result


def _compression_sizes(data: bytes) -> Dict[str, Any]:
    result: Dict[str, Any] = {"gzip_bytes": len(gzip.compress(data, mtime=0))}
    try:
        import zstandard
    except ImportError:
        result["zstd"] = {"status": "unavailable", "bytes": None}
    else:
        compressed = zstandard.ZstdCompressor(level=3).compress(data)
        result["zstd"] = {
            "status": "measured",
            "bytes": len(compressed),
            "version": getattr(zstandard, "__version__", "unknown"),
        }
    return result


def _artifact_measurement(records: Iterable[TrajectoryRecord]) -> Dict[str, int]:
    all_refs = [ref for record in records for ref in record.artifact_refs]
    unique = {ref.sha256: ref for ref in all_refs}
    return {
        "reference_count": len(all_refs),
        "unique_count": len(unique),
        "referenced_bytes": sum(ref.byte_length for ref in all_refs),
        "unique_bytes": sum(ref.byte_length for ref in unique.values()),
    }


def _measure_source(
    name: str,
    records: tuple[TrajectoryRecord, ...],
    *,
    repetitions: int,
) -> Dict[str, Any]:
    canonical = canonical_json_bytes([record.to_dict() for record in records])
    runs = {record.run_id for record in records if record.run_id}
    sessions = {record.session_id for record in records if record.session_id}
    works = {record.work_item_id for record in records if record.work_item_id}
    raw_runs = []
    for repetition in range(repetitions):
        memory = MemoryTrajectoryStore(store_id=f"measurement.{name}.{repetition}")
        memory_append_ns, _ = _time_ns(lambda: memory.append_batch(records))
        with tempfile.TemporaryDirectory(prefix="qitos-trajectory-measure-") as temp:
            journal_path = Path(temp) / "trajectory.journal"
            journal = JournalTrajectoryStore(journal_path)
            append_ns, _ = _time_ns(lambda: journal.append_batch(records))
            journal.close()
            reopen_ns, reopened = _time_ns(
                lambda: JournalTrajectoryStore(journal_path)
            )
            query_ns, selected = _time_ns(
                lambda: reopened.query(TrajectoryQuery(limit=len(records)))
            )
            first_run = sorted(runs)[0] if runs else None
            replay_ns, replayed = _time_ns(
                lambda: reopened.replay(
                    TrajectoryQuery(run_id=first_run, limit=len(records))
                )
            )
            full_read_ns, trajectory = _time_ns(lambda: reopened.read_run(first_run))
            exporter = CanonicalTrajectoryExporter()
            export_ns, exported = _time_ns(
                lambda: exporter.export(trajectory, view=PrivacyView.RAW_PRIVATE)
            )
            reimport_ns, imported = _time_ns(lambda: exporter.reimport(exported))
            assert imported.to_dict() == trajectory.to_dict()
            index_ns, index_report = _time_ns(reopened.rebuild_index)
            index_path = journal_path.with_name(journal_path.name + ".index.json")
            raw_runs.append(
                {
                    "repetition": repetition,
                    "memory_append_ns": memory_append_ns,
                    "journal_append_ns": append_ns,
                    "reopen_ns": reopen_ns,
                    "query_ns": query_ns,
                    "replay_ns": replay_ns,
                    "index_rebuild_ns": index_ns,
                    "full_read_ns": full_read_ns,
                    "exact_export_ns": export_ns,
                    "exact_reimport_ns": reimport_ns,
                    "exact_export_bytes": len(exported.data),
                    "complete_run_records": len(trajectory.records),
                    "journal_bytes": journal_path.stat().st_size,
                    "index_bytes": index_path.stat().st_size,
                    "query_records": len(selected),
                    "replay_records": len(replayed),
                    "index_records": index_report.record_count,
                }
            )
            reopened.close()
    return {
        "source": name,
        "scan_behavior": "Each journal query/read reloads all frames; append reloads and rebuilds the index.",
        "memory_boundary": "Full journal and exact trajectory are materialized; query limit bounds returned records only.",
        "record_count": len(records),
        "run_count": len(runs),
        "session_count": len(sessions),
        "work_item_count": len(works),
        "canonical_bytes": len(canonical),
        **_compression_sizes(canonical),
        "artifact_deduplication": _artifact_measurement(records),
        "raw_measurements": raw_runs,
        "median_ns": {
            key: int(statistics.median(item[key] for item in raw_runs))
            for key in (
                "memory_append_ns",
                "journal_append_ns",
                "reopen_ns",
                "query_ns",
                "replay_ns",
                "index_rebuild_ns",
                "full_read_ns",
                "exact_export_ns",
                "exact_reimport_ns",
            )
        },
    }


def build_result(
    fixture: Path, *, repetitions: int, dry_run: bool
) -> Dict[str, Any]:
    try:
        sources, raw_fixture_bytes = _load(fixture)
    except OSError:
        return {
            "schema_version": RESULT_SCHEMA,
            "status": "not_ready",
            "reason_code": "measurement_fixture_unavailable",
            "measurements": [],
            "claims": [],
        }
    except ValueError as exc:
        return {
            "schema_version": RESULT_SCHEMA,
            "status": "not_ready",
            "reason_code": str(exc),
            "measurements": [],
            "claims": [],
        }
    if dry_run:
        return {
            "schema_version": RESULT_SCHEMA,
            "status": "dry_run_ready",
            "source_names": sorted(sources),
            "repetitions": repetitions,
            "measurements": [],
            "claims": [],
        }
    tracemalloc.start()
    measurements = [
        _measure_source(name, records, repetitions=repetitions)
        for name, records in sorted(sources.items())
    ]
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "measured_not_release_qualified",
        "fixture_raw_bytes": raw_fixture_bytes,
        "repetitions": repetitions,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "tracemalloc_peak_bytes": peak,
            "process_peak_rss_platform_units": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
        },
        "measurements": measurements,
        "claims": [],
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.repetitions < 2:
        parser.error("--repetitions must be at least 2")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = build_result(
        args.fixture, repetitions=args.repetitions, dry_run=args.dry_run
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"dry_run_ready", "measured_not_release_qualified"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

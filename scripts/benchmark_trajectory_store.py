#!/usr/bin/env python3
"""Schema-neutral entry point for the future trajectory-store benchmark.

D1 deliberately has no trajectory-v2 schema or payload fixtures.  This script
therefore validates source manifests and emits a typed readiness result.  It
must not be extended with an inferred v2 representation: the owning Lane B/C
contracts are hard prerequisites for measurements.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence


RESULT_VERSION = "trajectory-store-benchmark-readiness-v1"
MANIFEST_NAME = "fixture-manifest.json"
REQUIRED_SOURCE_CLASSES = {"campaign_long", "unrelated_agent"}
REQUIRED_CONTRACTS = [
    "lane_b.exchange_log_fixture_version",
    "lane_b.request_view_report",
    "lane_b.codec_report",
    "lane_b.provider_continuation_opaque_fields",
    "lane_b.artifact_ref",
    "lane_b.compaction_report",
    "lane_c.canonical_tool_result_fixture_version",
    "lane_c.timeout_cancellation_receipt",
    "lane_c.durability_receipt",
    "lane_c.hook_failure_fields",
    "lane_c.trace_safe_redaction_contract",
]
PLANNED_MEASUREMENTS = [
    "current_v1_bytes",
    "naive_repeated_json_bytes",
    "digest_references_uncompressed_bytes",
    "optional_gzip_bytes",
    "optional_zstd_bytes",
    "write_time",
    "read_time",
    "replay_time",
    "query_render_time",
    "artifact_dedup_ratio",
]
PLANNED_VIEWS = ["raw_private", "redacted_public"]


def _load_manifests(fixture_root: Path) -> tuple[List[Dict[str, Any]], List[str]]:
    manifests: List[Dict[str, Any]] = []
    errors: List[str] = []
    if not fixture_root.is_dir():
        return manifests, ["fixture_root_not_found"]

    for path in sorted(fixture_root.rglob(MANIFEST_NAME)):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"invalid_manifest:{path.relative_to(fixture_root)}")
            continue
        if not isinstance(value, dict):
            errors.append(f"manifest_not_object:{path.relative_to(fixture_root)}")
            continue
        manifests.append(value)
    if not manifests:
        errors.append("no_fixture_manifests")
    return manifests, errors


def build_readiness_result(fixture_root: Path, dry_run: bool) -> Dict[str, Any]:
    """Return a deterministic readiness report without loading trajectory data."""
    manifests, errors = _load_manifests(fixture_root)
    source_classes = sorted(
        {
            str(manifest.get("source_class"))
            for manifest in manifests
            if manifest.get("source_class")
        }
    )
    missing_classes = sorted(REQUIRED_SOURCE_CLASSES - set(source_classes))
    payloads_ready = bool(manifests) and all(
        manifest.get("status") == "sanitized_payload_ready"
        for manifest in manifests
    )

    blockers = list(errors)
    blockers.extend(f"missing_source_class:{item}" for item in missing_classes)
    if not payloads_ready:
        blockers.append("sanitized_payloads_not_ready")
    blockers.append("trajectory_v2_schema_not_frozen")
    blockers.append("lane_b_c_contracts_not_versioned")

    return {
        "result_version": RESULT_VERSION,
        "status": "schema_not_ready",
        "reason_code": "TRAJECTORY_SCHEMA_NOT_READY",
        "dry_run": dry_run,
        "trajectory_v2_schema_frozen": False,
        "fixture_root": fixture_root.as_posix(),
        "fixture_manifests_found": len(manifests),
        "source_classes": source_classes,
        "planned_measurements": PLANNED_MEASUREMENTS,
        "planned_views": PLANNED_VIEWS,
        "required_contracts": REQUIRED_CONTRACTS,
        "blockers": sorted(set(blockers)),
        "measurements": [],
        "claims": [],
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report trajectory-store benchmark readiness."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        required=True,
        help="Directory containing fixture-manifest.json files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Emit readiness as a successful preflight command.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = build_readiness_result(args.fixture, args.dry_run)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if args.dry_run else 2


if __name__ == "__main__":
    raise SystemExit(main())

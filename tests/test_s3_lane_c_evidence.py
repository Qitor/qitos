from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "s3" / "lane_c"


def test_lane_c_manifest_digests_and_typed_waiting_status() -> None:
    manifest = json.loads((FIXTURES / "producer-manifest.json").read_text())
    evidence = json.loads((FIXTURES / "qualification-evidence.json").read_text())

    assert manifest["status"] == "waiting_on_lane_a_b"
    assert evidence["status"] == "waiting_on_lane_a_b"
    assert manifest["lane_a_exact_source"]["branch_head"] == (
        "feba1bf6d2312b82c7f03ce0b3c1f07e50712938"
    )
    assert manifest["lane_b_exact_source"]["status"] == "missing_producer_manifest"
    for item in manifest["files"]:
        path = ROOT / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_lane_c_evidence_bundle_has_all_stable_files() -> None:
    expected = {
        "README.md",
        "crash-window-matrix.json",
        "join-matrix.json",
        "operation-idempotency.json",
        "producer-manifest.json",
        "qualification-evidence.json",
        "runtime-handoff.json",
        "scheduler-conformance.json",
    }
    assert {path.name for path in FIXTURES.iterdir()} == expected
    for path in FIXTURES.glob("*.json"):
        assert json.loads(path.read_text())["schema_version"].startswith("qitos.s3.lane_c.")

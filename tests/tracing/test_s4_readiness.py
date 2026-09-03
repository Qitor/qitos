from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from qitos.tracing.s4_readiness import load_s4_readiness, qualify_s4_readiness


ROOT = Path(__file__).resolve().parents[2]


def test_committed_inventory_truthfully_waits_for_concurrent_s4_producers() -> None:
    inventory = load_s4_readiness(
        ROOT / "tests" / "fixtures" / "s4" / "lane_d" / "a-b-c-readiness-inventory.json"
    )
    result = qualify_s4_readiness(inventory, repository_root=ROOT)

    assert result.status == "waiting_on_a_b_c"
    assert result.qualified_lanes == ()
    assert set(result.finding_codes) == {
        "lane_a_producer_missing",
        "lane_b_producer_missing",
        "lane_c_producer_missing",
    }
    assert result.schema_frozen is False
    assert result.default_writer_enabled is False
    assert result.default_reader_switched is False
    assert result.publication_ready is False


def test_s3_or_self_declared_fixture_cannot_impersonate_s4_producer() -> None:
    fake = {
        "schema_version": "qitos.s4.lane_d.readiness/1",
        "lanes": {
            lane: {
                "exact_commit": "0" * 40,
                "producer_authority": "qitos.s3.g4.exact_source/1",
                "source_wave": "S3",
                "requirements": [],
            }
            for lane in ("A", "B", "C")
        },
    }
    result = qualify_s4_readiness(fake, repository_root=ROOT)
    assert result.status == "waiting_on_a_b_c"
    assert any(code.endswith("source_wave_rejected") for code in result.finding_codes)
    assert any(code.endswith("authority_invalid") for code in result.finding_codes)


def test_lane_d_manifest_binds_exact_committed_implementation_bytes() -> None:
    manifest = json.loads(
        (
            ROOT
            / "tests"
            / "fixtures"
            / "s4"
            / "lane_d"
            / "producer-manifest.json"
        ).read_text()
    )
    assert manifest["status"] == "waiting_on_a_b_c"
    assert manifest["exact_s4_producers"] == {
        "lane_a": None,
        "lane_b": None,
        "lane_c": None,
    }
    for binding in manifest["committed_bindings"]:
        data = subprocess.run(
            ["git", "show", f"{binding['commit']}:{binding['path']}"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        assert hashlib.sha256(data).hexdigest() == binding["sha256"]

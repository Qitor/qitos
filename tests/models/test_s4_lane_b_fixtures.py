from __future__ import annotations

import hashlib
import json
import re
import runpy
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[2]
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures" / "s4" / "lane_b"


def test_lane_b_semantic_fixtures_are_strict_json_and_cover_dispatch() -> None:
    expected = {
        "a-c-d-handoff.json",
        "config-handoff.json",
        "context-compaction-artifact.json",
        "failure-taxonomy.json",
        "multimodal.json",
        "multi-turn-tool-transaction.json",
        "parallel-out-of-order-completion.json",
        "provider-capability-matrix.json",
        "qualification-evidence.json",
        "reasoning-continuation.json",
        "steering-recovery.json",
        "streaming.json",
        "usage-budget.json",
    }
    assert expected <= {path.name for path in FIXTURES.glob("*.json")}
    for name in expected:
        payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        assert payload["schema_version"].startswith("qitos.s4.")


def test_lane_a_config_consumer_uses_only_public_structural_contracts() -> None:
    namespace = runpy.run_path(str(FIXTURES / "config_consumer.py"))
    consumed = namespace["consume_handoff"]()

    assert consumed["logical_profile_id"] == "fixture.semantic"
    assert consumed["target"]["api_mode"] == "semantic"
    assert consumed["capabilities"]["supports_continuation"] is True


def test_lane_b_producer_manifest_binds_current_bytes_and_test_nodes() -> None:
    manifest = json.loads(
        (FIXTURES / "producer-manifest.json").read_text(encoding="utf-8")
    )
    commit = manifest["producer_commit"]
    assert re.fullmatch(r"[0-9a-f]{40}", commit)
    subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for item in manifest["producer_files"]:
        path = REPOSITORY_ROOT / item["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}:{item['path']}"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    collected = subprocess.run(
        [
            "/opt/anaconda3/bin/python",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            *manifest["producer_test_node_ids"],
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr

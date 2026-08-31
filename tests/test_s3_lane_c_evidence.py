from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "s3" / "lane_c"


def test_lane_c_manifest_digests_commits_and_executable_nodes() -> None:
    manifest = json.loads((FIXTURES / "producer-manifest.json").read_text())
    evidence = json.loads((FIXTURES / "qualification-evidence.json").read_text())

    assert manifest["status"] == "qualified_integrated_a_b"
    assert evidence["status"] == "qualified_integrated_a_b"
    assert evidence["lane_a_consumed"] is True
    assert evidence["lane_b_consumed"] is True
    assert manifest["lane_a_exact_source"]["source_head"] == (
        "9442647767bc9a7c45ed3bf07bc4f289412544ed"
    )
    assert manifest["lane_b_exact_source"]["repair_commit"] == (
        "8bbfd6580e03f77f51777e696d78ee783bc09f75"
    )
    for commit in manifest["exact_commits"]:
        assert re.fullmatch(r"[0-9a-f]{40}", commit)
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    for item in manifest["files"]:
        path = ROOT / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    for node_id in manifest["test_node_ids"]:
        path_text, separator, function_name = node_id.partition("::")
        assert separator and function_name.startswith("test_")
        tree = ast.parse((ROOT / path_text).read_text(encoding="utf-8"))
        assert function_name in {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }


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

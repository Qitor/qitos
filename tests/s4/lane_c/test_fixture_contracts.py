from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qitos.kit.env.sandbox import SandboxPolicy, SandboxSnapshotComponent


FIXTURES = Path(__file__).parents[2] / "fixtures" / "s4" / "lane_c"


def test_producer_manifest_covers_every_evidence_fixture() -> None:
    manifest = json.loads((FIXTURES / "producer_manifest.json").read_text(encoding="utf-8"))
    expected = {path.name for path in FIXTURES.glob("*.json")} - {"producer_manifest.json"}
    assert set(manifest["artifacts"]) == expected
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest


def test_policy_and_snapshot_fixtures_use_runtime_contracts() -> None:
    policy = json.loads((FIXTURES / "sandbox_policy.json").read_text(encoding="utf-8"))
    limits = policy.pop("limits")
    from qitos.kit.env.sandbox import SandboxResourceLimits

    parsed = SandboxPolicy(**policy, limits=SandboxResourceLimits(**limits))
    assert parsed.digest

    snapshot = json.loads(
        (FIXTURES / "sandbox_snapshot_component.json").read_text(encoding="utf-8")
    )
    assert SandboxSnapshotComponent.from_dict(snapshot).to_dict() == snapshot


def test_qualification_fixture_records_real_run_without_counting_a_skip() -> None:
    evidence = json.loads(
        (FIXTURES / "qualification_evidence.json").read_text(encoding="utf-8")
    )
    assert evidence["status"] == "passed"
    assert evidence["real_create_inspect_probe_cleanup"] is True
    assert evidence["skip_counted_as_pass"] is False
    assert evidence["label_scoped_leaked_containers_observed"] == 0


def test_adversarial_matrix_covers_required_threats_without_secret_echoes() -> None:
    matrix = json.loads(
        (FIXTURES / "adversarial_matrix.json").read_text(encoding="utf-8")
    )
    required = {
        "relative_traversal", "absolute_path_escape", "symlink_escape",
        "toctou_stale_write", "vcs_and_credentials", "unexpected_mount",
        "docker_socket", "device_namespace_privileged", "host_network",
        "local_private_endpoint", "dns_egress_change", "secret_surfaces",
        "oversized_output", "fork_bomb", "pids_exhaustion",
        "cpu_memory_time_bounds", "sibling_session_contamination",
        "stale_owner_lease", "late_worker", "repeated_cleanup",
        "process_client_loss", "leaked_resource_detection",
    }
    assert set(matrix["cases"]) == required
    assert matrix["finding_echoes_sensitive_values"] is False
    assert {item["result"] for item in matrix["cases"].values()} <= {
        "passed", "platform_blocked"
    }

"""Validator unit fixtures are synthetic; they are never qualification receipts."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from qitos.tracing import s4_readiness as module


@pytest.fixture
def admitted_binding(monkeypatch):
    code, artifact_commit, execution_commit = "a" * 40, "b" * 40, "c" * 40
    identity = {"session_id": "session_" + "1" * 32, "run_id": "run_" + "2" * 32,
                "work_item_id": "work_" + "3" * 32, "attempt_id": "attempt_" + "4" * 32,
                "owner_generation": 3}
    # Use the actual core identity prefix, rather than inventing its spelling.
    from qitos.core.session import WorkItemIdentity
    identity["work_item_id"] = WorkItemIdentity.PREFIX + "_" + "3" * 32
    facts = dict(identity, source_fork_unchanged=True)
    execution = {"schema": "qitos.g5.controlled_execution/v1", "code_commit": code,
        "nodes": {}, "consumers": {"coding": {"outcome": "passed", "installed_distribution": True,
        "identity": identity, "code_commit": code, "wheel_sha256": "d" * 64, "runtime_facts": facts}}}
    files, pins, requirements = {}, {}, []
    for requirement, (writer, node) in module.REQUIREMENTS["A"].items():
        path = f"tests/fixtures/s4/g5/current-facts/a-{requirement}.json"
        artifact = {"schema": "qitos.g5.runtime_fact/v1", "writer": writer, "requirement_id": requirement,
                    "code_commit": code, "identity": identity, "runtime_facts": facts}
        encoded = json.dumps(artifact).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        files[(artifact_commit, path)] = encoded
        test_path, test_name = node.split("::")
        files[(code, test_path)] = files.get((code, test_path), b"") + f"\ndef {test_name}(): pass\n".encode()
        writer_module, symbol = writer.rsplit(".", 1)
        source_path = writer_module.replace(".", "/") + ".py"
        files[(code, source_path)] = files.get((code, source_path), b"") + f"\nclass {symbol}: pass\n".encode()
        execution["nodes"][node] = {"collected": True, "outcome": "passed", "skipped": False}
        requirements.append({"requirement_id": requirement, "committed_path": path,
            "artifact_commit": artifact_commit, "sha256": digest, "schema": artifact["schema"],
            "current_writer": writer, "consumer_test_node": node,
            "producer_authority": module.S4_PRODUCER_AUTHORITY, "no_identity_conflict": True})
        pins[("A", requirement)] = {"code_commit": code, "artifact_commit": artifact_commit,
            "artifact_sha256": digest, "qualification_commit": execution_commit,
            "execution_path": "tests/fixtures/s4/g5/controlled-execution.json",
            "consumer": "coding", "wheel_sha256": "d" * 64}
    execution_bytes = json.dumps(execution).encode()
    execution_path = "tests/fixtures/s4/g5/controlled-execution.json"
    files[(execution_commit, execution_path)] = execution_bytes
    for pin in pins.values():
        pin["execution_sha256"] = hashlib.sha256(execution_bytes).hexdigest()
    monkeypatch.setattr(module, "QUALIFICATION_PINS", pins)
    monkeypatch.setattr(module, "_git_bytes", lambda root, commit, path: files.get((commit, path)))
    binding = {"exact_commit": code, "producer_authority": module.S4_PRODUCER_AUTHORITY,
        "source_wave": "S4", "source_commit": module.SOURCE_HEADS["A"],
        "replay_commit": module.REPLAY_HEADS["A"], "requirements": requirements}
    return binding, files, pins, execution


def validate(binding):
    return module._validate_binding("A", binding, repository_root=Path("."))


def test_pinned_current_execution_accepts_distinct_code_fact_and_receipt_commits(admitted_binding):
    binding, *_ = admitted_binding
    assert validate(binding) == ()


@pytest.mark.parametrize("mutation", ["readme", "schema", "writer", "node", "stale_digest", "unknown",
    "duplicate", "historical_writer", "uncollected_node", "unpassed_consumer", "invalid_identity",
    "mismatched_lineage", "missing_execution", "self_report_only"])
def test_untrusted_producer_cannot_authorize_readiness(admitted_binding, mutation):
    binding, files, pins, execution = admitted_binding
    requirement = binding["requirements"][0]
    if mutation == "readme": requirement["committed_path"] = "README.md"
    elif mutation == "schema": requirement["schema"] = "invented/schema"
    elif mutation == "writer": requirement["current_writer"] = "invented.writer"
    elif mutation == "node": requirement["consumer_test_node"] += "_missing"
    elif mutation == "stale_digest": requirement["sha256"] = "0" * 64
    elif mutation == "unknown": requirement["requirement_id"] = "self_authorized"
    elif mutation == "duplicate": binding["requirements"].append(copy.deepcopy(requirement))
    elif mutation == "historical_writer":
        files.pop((binding["exact_commit"], "qitos/config/builder.py"))
    elif mutation in {"missing_execution", "self_report_only"}:
        if mutation == "missing_execution":
            files.pop(("c" * 40, "tests/fixtures/s4/g5/controlled-execution.json"))
        else:
            pins.clear()
    else:
        if mutation == "uncollected_node": execution["nodes"][requirement["consumer_test_node"]]["collected"] = False
        elif mutation == "unpassed_consumer": execution["consumers"]["coding"]["outcome"] = "failed"
        elif mutation == "invalid_identity": execution["consumers"]["coding"]["identity"]["session_id"] = "arbitrary string"
        elif mutation == "mismatched_lineage": execution["consumers"]["coding"]["runtime_facts"]["work_item_id"] = "wrong"
        data = json.dumps(execution).encode()
        files[("c" * 40, "tests/fixtures/s4/g5/controlled-execution.json")] = data
        for pin in pins.values(): pin["execution_sha256"] = hashlib.sha256(data).hexdigest()
    assert validate(binding)

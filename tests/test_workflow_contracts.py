from __future__ import annotations

from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOWS = tuple(sorted(WORKFLOW_DIR.glob("*.yml")))


def _workflow_text() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in WORKFLOWS}


def _jobs(path: Path) -> dict[str, object]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{path} must contain a YAML object"
    jobs = document.get("jobs")
    assert isinstance(jobs, dict), f"{path} must contain a jobs mapping"
    return jobs


def _run_commands(job: object) -> list[str]:
    assert isinstance(job, dict)
    steps = job.get("steps")
    assert isinstance(steps, list)
    return [
        step["run"]
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("run"), str)
    ]


def test_workflows_reject_invalid_predicates_and_masked_commands() -> None:
    forbidden = {
        "changed_files.*.filename": "changed_files is a count, not a file array",
        "|| true": "commands must not mask failures",
        "continue-on-error: true": "job failures must not be unconditionally advisory",
        "--reruns": "automatic reruns hide test instability",
        "pytest-rerunfailures": "automatic rerun plugins hide test instability",
    }

    for path, text in _workflow_text().items():
        for token, reason in forbidden.items():
            assert token not in text, f"{path}: {reason}: {token}"


def test_every_pytest_path_referenced_by_a_workflow_exists() -> None:
    test_path_pattern = re.compile(r"(?<![A-Za-z0-9_])tests(?:/[A-Za-z0-9_.-]+)*/?")

    for path, text in _workflow_text().items():
        for relative in test_path_pattern.findall(text):
            target = ROOT / relative.rstrip("/")
            assert target.exists(), f"{path} references missing test path {relative}"


def test_contribution_checks_use_supported_workflow_path_scope() -> None:
    path = WORKFLOW_DIR / "contribution-test.yml"
    text = path.read_text(encoding="utf-8")

    assert "github.event.pull_request.changed_files" not in text
    assert "qitos/engine/critic_decorator.py" in text
    assert "tests/engine/**" in text
    assert "advisory" in text


def test_stable_zero_debt_and_full_ratchet_are_distinct_jobs() -> None:
    jobs = _jobs(WORKFLOW_DIR / "ci.yml")
    lint_commands = _run_commands(jobs["lint-stable"])
    type_commands = _run_commands(jobs["type-stable"])
    ratchet_commands = _run_commands(jobs["static-ratchet"])

    assert "flake8 qitos/core qitos/engine qitos/models qitos/trace" in lint_commands
    assert "mypy qitos/core qitos/engine qitos/models qitos/trace" in type_commands
    assert "python scripts/static_quality.py check" in ratchet_commands
    assert jobs["static-ratchet"].get("name") == "full-package no-regression ratchet"


def test_ci_ownership_evidence_covers_every_workflow() -> None:
    evidence = (ROOT / "docs" / "internal" / "ci-job-ownership.md").read_text(
        encoding="utf-8"
    )

    for path in WORKFLOWS:
        assert f"`{path.name}`" in evidence

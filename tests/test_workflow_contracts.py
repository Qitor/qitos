from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

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


def test_contribution_tool_schema_entrypoint_executes_real_inventory() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/qualify_tool_schemas.py"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "qualified"
    assert report["modules_imported"] > 1
    assert report["class_definitions"] > 0
    assert report["class_tools_qualified"] > 0
    assert report["registered_class_tools"] == report["class_tools_qualified"]

    commands = _run_commands(
        _jobs(WORKFLOW_DIR / "contribution-test.yml")["tool-schema-check"]
    )
    assert "python scripts/qualify_tool_schemas.py" in commands


def test_contribution_tool_schema_entrypoint_rejects_invalid_spec(tmp_path: Path) -> None:
    fixture = tmp_path / "invalid-tool-spec.json"
    fixture.write_text(
        json.dumps(
            {
                "specs": [
                    {
                        "name": "",
                        "description": "controlled invalid spec",
                        "parameters": {},
                        "required": [],
                        "input_schema": {"type": "object", "properties": {}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/qualify_tool_schemas.py",
            "--spec-fixture",
            str(fixture),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 1
    failure = json.loads(completed.stderr)
    assert failure["status"] == "failed"
    assert failure["code"] == "invalid_tool_name"


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


def test_docs_workflow_navigation_and_translation_paths_exist() -> None:
    docs_root = ROOT / "docs"
    config = json.loads((docs_root / "docs.json").read_text(encoding="utf-8"))
    referenced: set[Path] = set()
    for language in config.get("navigation", {}).get("languages", []):
        for tab in language.get("tabs", []):
            for group in tab.get("groups", []):
                if group.get("root"):
                    referenced.add(docs_root / f"{group['root']}.mdx")
                referenced.update(
                    docs_root / f"{page}.mdx" for page in group.get("pages", [])
                )
    assert not [path for path in sorted(referenced) if not path.exists()]

    english = {
        path.relative_to(docs_root)
        for path in docs_root.rglob("*.mdx")
        if "zh" not in path.relative_to(docs_root).parts
        and "blog" not in path.relative_to(docs_root).parts
        and path.parent.name != "images"
    }
    missing_zh = [docs_root / "zh" / path for path in sorted(english)]
    assert not [path for path in missing_zh if not path.exists()]


def test_primary_branch_ci_is_read_only_bounded_and_keeps_release_manual() -> None:
    for name in ("ci.yml", "docs.yml"):
        path = WORKFLOW_DIR / name
        # BaseLoader preserves the YAML key `on` instead of YAML 1.1 boolean coercion.
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        events = document["on"]
        assert {"main", "master", "feat/campaign-absorption"} <= set(
            events["push"]["branches"]
        )
        assert "pull_request" in events and "workflow_dispatch" in events
        assert "pull_request_target" not in events
        assert document["permissions"] == {"contents": "read"}
        assert document["concurrency"]["cancel-in-progress"] == "true"
        for job in document["jobs"].values():
            assert 1 <= int(job["timeout-minutes"]) <= 30
        assert "secrets." not in path.read_text(encoding="utf-8")

    release = yaml.load(
        (WORKFLOW_DIR / "pypi.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader
    )
    assert set(release["on"]) == {"workflow_dispatch", "release"}
    assert release["on"]["release"]["types"] == ["published"]
    assert release["jobs"]["publish"]["needs"] == "build"

#!/usr/bin/env python3
"""Run integration-controlled nodes and installed consumers; never manifest code."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qitos.tracing._g5_requirements import REQUIREMENTS


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def verify_wheel(wheel: Path, commit: str) -> dict[str, str]:
    expected = [name for name in git("ls-tree", "-r", "--name-only", commit, "qitos").decode().splitlines()
                if name.endswith(".py")]
    with zipfile.ZipFile(wheel) as archive:
        actual = {name for name in archive.namelist() if name.startswith("qitos/") and name.endswith(".py")}
        if set(expected) != actual:
            raise ValueError("wheel_source_inventory_mismatch")
        checked = {}
        for name in expected:
            source = git("show", f"{commit}:{name}")
            if archive.read(name) != source:
                raise ValueError("wheel_source_bytes_mismatch")
            checked[name] = digest(source)
    return checked


def run(command: list[str], *, cwd: Path, log: Path, timeout: int) -> int:
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "QITOS_E2E_ENDPOINT", "QITOS_E2E_API_KEY"):
        environment.pop(key, None)
    with log.open("w") as stream:
        try:
            result = subprocess.run(command, cwd=cwd, env=environment, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            stream.write("\nG5_QUALIFICATION_TIMEOUT\n")
            return 124
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    wheel, output = args.wheel.resolve(), args.output.resolve()
    if git("status", "--porcelain").strip():
        raise ValueError("qualification_requires_clean_source")
    if output == ROOT or ROOT in output.parents:
        raise ValueError("qualification_output_must_be_outside_source")
    commit = git("rev-parse", "HEAD").decode().strip()
    package_sources = verify_wheel(wheel, commit)
    output.mkdir(parents=True, exist_ok=False)
    wheel_digest = digest(wheel.read_bytes())
    targets = sorted({node for requirements in REQUIREMENTS.values() for _, node in requirements.values()})
    report = {"schema": "qitos.g5.controlled_execution/v1", "code_commit": commit,
              "wheel_sha256": wheel_digest, "wheel_source_digests": package_sources,
              "nodes": {}, "consumers": {}, "outcome": "failed"}
    junit = output / "controlled.xml"
    command = [sys.executable, "-m", "pytest", "-q", "-rs", f"--junitxml={junit}", *targets]
    report["test_command"] = command
    result = run(command, cwd=ROOT, log=output / "controlled.log", timeout=300)
    cases = ET.parse(junit).findall(".//testcase") if junit.exists() else []
    for target in targets:
        path, function = target.split("::")
        module = path[:-3].replace("/", ".")
        selected = [case for case in cases if case.get("classname") == module
                    and (case.get("name") == function or case.get("name", "").startswith(function + "["))]
        passed = bool(selected) and all(not list(case) for case in selected)
        report["nodes"][target] = {
            "collected": bool(selected), "outcome": "passed" if passed else "failed",
            "skipped": any(case.find("skipped") is not None for case in selected),
            "executed_nodes": [f"{path}::{case.get('name')}" for case in selected],
            "source_sha256": digest(git("show", f"{commit}:{path}")),
        }
    report["junit_sha256"] = digest(junit.read_bytes()) if junit.exists() else None
    try:
        if result or not all(node["outcome"] == "passed" for node in report["nodes"].values()):
            raise ValueError("controlled_nodes_failed")
        # Independent fresh environments. Docker use is serial across consumers.
        for name in ("coding", "research"):
            source_path = f"tests/fixtures/s4/g5/installed_{name}_consumer.py"
            source = git("show", f"{commit}:{source_path}")
            with tempfile.TemporaryDirectory(prefix=f"g5-qualified-{name}-") as directory:
                root = Path(directory)
                venv.EnvBuilder(with_pip=True).create(root / "venv")
                python = root / "venv/bin/python"
                install = run([str(python), "-m", "pip", "install", str(wheel)], cwd=root,
                              log=output / f"{name}-install.log", timeout=600)
                if install:
                    raise ValueError(f"{name}_dependency_install_failed")
                script = root / "consumer.py"
                script.write_bytes(source)
                log = output / f"{name}-consumer.log"
                status = run([str(python), str(script), "--evidence-dir", str(output)],
                             cwd=root, log=log, timeout=240)
                lines = [line.partition("=")[2] for line in log.read_text().splitlines()
                         if line.startswith("G5_CONSUMER_RESULT=")]
                if status or len(lines) != 1:
                    raise ValueError(f"{name}_consumer_failed")
                facts = json.loads(lines[0])
                identity = {key: facts[key] for key in
                            ("session_id", "run_id", "work_item_id", "attempt_id", "owner_generation")}
                report["consumers"][name] = {
                    "outcome": "passed", "code_commit": commit,
                    "installed_distribution": facts["installed_distribution"], "identity": identity,
                    "wheel_sha256": wheel_digest, "runtime_facts": facts,
                    "consumer_source_path": source_path, "consumer_source_sha256": digest(source),
                    "log_sha256": digest(log.read_bytes()), "fresh_environment": True}
        report["outcome"] = "passed"
    except ValueError as error:
        report["reason_code"] = str(error)
    finally:
        (output / "controlled-execution.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"outcome": report["outcome"], "code_commit": commit,
                      "reason_code": report.get("reason_code"), "output": str(output)}))
    return 0 if report["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

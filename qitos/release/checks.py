"""Release hardening checks for single-kernel launch."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from benchmarks.plan_act_eval import run_eval as run_plan_act
from benchmarks.react_eval import run_eval as run_react
from benchmarks.swe_mini_eval import run_eval as run_swe
from benchmarks.voyager_eval import run_eval as run_voyager
from qitos.trace import TraceSchemaValidator


REQUIRED_TEMPLATE_FILES = {"agent.py", "config.yaml", "paper.md", "__init__.py"}


def check_template_contracts(root: str = "templates") -> Dict[str, Any]:
    base = Path(root)
    failures: List[str] = []
    checked = 0
    for item in sorted(base.iterdir()):
        if not item.is_dir() or item.name.startswith("__"):
            continue
        checked += 1
        files = {p.name for p in item.iterdir() if p.is_file()}
        missing = REQUIRED_TEMPLATE_FILES - files
        if missing:
            failures.append(f"{item.name}: missing {sorted(missing)}")
    return {"checked": checked, "failures": failures, "ok": not failures}


def check_architecture_consistency() -> Dict[str, Any]:
    targets = [
        Path("qitos/__init__.py"),
        Path("qitos/core/__init__.py"),
        Path("qitos/runtime/__init__.py"),
    ]
    banned = ["AgentModuleV", "DecisionV", "RuntimeV", "ToolRegistryV"]
    failures: List[str] = []
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                failures.append(f"{path}: contains banned token '{token}'")
    return {"checked": len(targets), "failures": failures, "ok": not failures}


def check_trace_schema_smoke() -> Dict[str, Any]:
    validator = TraceSchemaValidator()
    failures: List[str] = []
    with tempfile.TemporaryDirectory() as td:
        run_swe(trace_output_dir=td)
        run_voyager(trace_output_dir=td)
        for run_dir in [p for p in Path(td).iterdir() if p.is_dir()]:
            try:
                manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
                events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
                steps = [json.loads(line) for line in (run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
                validator.validate_manifest(manifest)
                validator.validate_events(events)
                validator.validate_steps(steps)
            except Exception as exc:
                failures.append(f"{run_dir.name}: {exc}")
    return {"checked": "swe+voyager", "failures": failures, "ok": not failures}


def check_benchmark_smoke() -> Dict[str, Any]:
    metrics = {
        "react": run_react(),
        "plan_act": run_plan_act(),
        "voyager": run_voyager(),
        "swe": run_swe(),
    }
    failures: List[str] = []
    for name, item in metrics.items():
        if item.get("success_rate", 0.0) <= 0.0:
            failures.append(f"{name}: success_rate<=0")
    return {"metrics": metrics, "failures": failures, "ok": not failures}


def run_release_checks() -> Dict[str, Any]:
    architecture = check_architecture_consistency()
    templates = check_template_contracts()
    trace = check_trace_schema_smoke()
    benchmarks = check_benchmark_smoke()
    overall_ok = architecture["ok"] and templates["ok"] and trace["ok"] and benchmarks["ok"]
    return {
        "ok": overall_ok,
        "architecture": architecture,
        "templates": templates,
        "trace": trace,
        "benchmarks": benchmarks,
    }


def write_release_readiness_report(path: str = "reports/release_readiness.md") -> Dict[str, Any]:
    report = run_release_checks()
    lines = [
        "# Release Readiness Report",
        "",
        f"- Overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- Architecture Checks: {'PASS' if report['architecture']['ok'] else 'FAIL'}",
        f"- Template Contracts: {'PASS' if report['templates']['ok'] else 'FAIL'}",
        f"- Trace Schema Smoke: {'PASS' if report['trace']['ok'] else 'FAIL'}",
        f"- Benchmark Smoke: {'PASS' if report['benchmarks']['ok'] else 'FAIL'}",
        "",
        "## Benchmark Metrics",
        f"- React success_rate: {report['benchmarks']['metrics']['react']['success_rate']:.2%}",
        f"- PlanAct success_rate: {report['benchmarks']['metrics']['plan_act']['success_rate']:.2%}",
        f"- Voyager success_rate: {report['benchmarks']['metrics']['voyager']['success_rate']:.2%}",
        f"- SWE success_rate: {report['benchmarks']['metrics']['swe']['success_rate']:.2%}",
    ]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


__all__ = [
    "check_architecture_consistency",
    "check_template_contracts",
    "check_trace_schema_smoke",
    "check_benchmark_smoke",
    "run_release_checks",
    "write_release_readiness_report",
]

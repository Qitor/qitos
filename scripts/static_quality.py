#!/usr/bin/env python3
"""Build and enforce the repository-wide flake8/mypy quality ratchet."""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "quality" / "static_baseline.json"
HANDOFF_PATH = ROOT / "quality" / "correctness_handoffs.md"
TOOLCHAIN_PATH = ROOT / "quality" / "toolchain.json"
MYPY_CONFIG_PATH = ROOT / "quality" / "mypy.ini"
W1_BASELINE_COMMIT = "fb75cd5902fedf50d5e67dd617e62cd981c3128f"

FLAKE8_PATTERN = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<column>\d+): "
    r"(?P<rule>[A-Z]\d+) (?P<message>.*)$"
)
MYPY_PATTERN = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<column>\d+): error: "
    r"(?P<message>.*)  \[(?P<rule>[^]]+)\]$"
)

VENDORED_SURFACES = (
    {
        "path": "qitos/benchmark/tau_bench/port",
        "kind": "vendored",
        "source": "Tau-Bench upstream port; exact upstream revision is legacy provenance debt",
        "owner": "Lane D / Task 10B",
        "exit_plan": (
            "Pin upstream source/license/version, isolate or move the port out of the "
            "core distribution, and retire it through the benchmark-to-recipes migration."
        ),
    },
)


class RatchetError(RuntimeError):
    """A deterministic ratchet or diagnostic-contract failure."""


@dataclass(frozen=True)
class RawFinding:
    tool: str
    rule: str
    path: str
    line: int
    column: int
    message: str


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RatchetError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RatchetError(f"expected an object in {path}")
    return value


def _tool_versions() -> dict[str, str]:
    return {
        package: importlib.metadata.version(package)
        for package in ("flake8", "mccabe", "mypy", "pycodestyle", "pyflakes")
    }


def verify_toolchain(expected: dict[str, Any] | None = None) -> dict[str, Any]:
    expected = expected or _load_json(TOOLCHAIN_PATH)
    actual_python = platform.python_version()
    expected_python = str(expected.get("python_runtime", ""))
    try:
        actual_tools = _tool_versions()
    except importlib.metadata.PackageNotFoundError as exc:
        raise RatchetError(
            "quality toolchain is incomplete; install requirements/quality.txt: "
            f"{exc}"
        ) from exc
    expected_tools = expected.get("tools")
    if not isinstance(expected_tools, dict):
        raise RatchetError("quality/toolchain.json has no tools object")
    mismatches: list[str] = []
    if actual_python != expected_python:
        mismatches.append(f"python expected {expected_python}, got {actual_python}")
    for package, expected_version in sorted(expected_tools.items()):
        actual_version = actual_tools.get(package)
        if actual_version != expected_version:
            mismatches.append(
                f"{package} expected {expected_version}, got {actual_version or 'missing'}"
            )
    if mismatches:
        raise RatchetError(
            "toolchain mismatch (rules upgrade is not source debt):\n  - "
            + "\n  - ".join(mismatches)
        )
    return {
        "python_runtime": actual_python,
        "mypy_target_python": str(expected.get("mypy_target_python", "")),
        "tools": actual_tools,
    }


def _run(command: Sequence[str]) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        text=True,
    )
    return completed.returncode, completed.stdout


def parse_flake8(output: str) -> list[RawFinding]:
    findings: list[RawFinding] = []
    malformed: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        match = FLAKE8_PATTERN.match(line)
        if match is None:
            malformed.append(line)
            continue
        findings.append(
            RawFinding(
                tool="flake8",
                rule=match.group("rule"),
                path=_normalize_path(match.group("path")),
                line=int(match.group("line")),
                column=int(match.group("column")),
                message=_normalize_message(match.group("message")),
            )
        )
    if malformed:
        raise RatchetError(
            "flake8 emitted unparseable diagnostics:\n  " + "\n  ".join(malformed[:10])
        )
    return findings


def parse_mypy(output: str) -> list[RawFinding]:
    findings: list[RawFinding] = []
    malformed_errors: list[str] = []
    for line in output.splitlines():
        match = MYPY_PATTERN.match(line)
        if match is not None:
            findings.append(
                RawFinding(
                    tool="mypy",
                    rule=match.group("rule"),
                    path=_normalize_path(match.group("path")),
                    line=int(match.group("line")),
                    column=int(match.group("column")),
                    message=_normalize_message(match.group("message")),
                )
            )
        elif ": error:" in line:
            malformed_errors.append(line)
    if malformed_errors:
        raise RatchetError(
            "mypy emitted unparseable errors:\n  " + "\n  ".join(malformed_errors[:10])
        )
    return findings


def _normalize_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        try:
            path = path.relative_to(ROOT)
        except ValueError as exc:
            raise RatchetError(
                f"diagnostic path is outside the repository: {value}"
            ) from exc
    normalized = path.as_posix()
    if not normalized.startswith("qitos/"):
        raise RatchetError(f"diagnostic path is outside qitos: {normalized}")
    return normalized


def _normalize_message(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).replace(str(ROOT), ".")


def collect_raw_findings() -> list[RawFinding]:
    flake8_status, flake8_output = _run(
        (
            sys.executable,
            "-m",
            "flake8",
            "--format=%(path)s:%(row)d:%(col)d: %(code)s %(text)s",
            "qitos",
        )
    )
    if flake8_status not in (0, 1):
        raise RatchetError(
            f"flake8 failed with status {flake8_status}:\n{flake8_output[-4000:]}"
        )
    mypy_status, mypy_output = _run(
        (
            sys.executable,
            "-m",
            "mypy",
            f"--config-file={MYPY_CONFIG_PATH.relative_to(ROOT)}",
            "qitos",
        )
    )
    if mypy_status not in (0, 1):
        raise RatchetError(
            f"mypy failed with status {mypy_status}:\n{mypy_output[-4000:]}"
        )
    return parse_flake8(flake8_output) + parse_mypy(mypy_output)


def _source_context(path: str, line: int) -> tuple[str, str]:
    source_path = ROOT / path
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RatchetError(f"cannot read diagnostic source {path}: {exc}") from exc
    lines = source.splitlines()
    source_line = lines[line - 1] if 0 < line <= len(lines) else ""
    normalized_line = re.sub(r"\s+", " ", source_line.strip())
    source_anchor = hashlib.sha256(normalized_line.encode("utf-8")).hexdigest()[:20]
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return "<module>", source_anchor
    return _enclosing_symbol(tree, line), source_anchor


def _enclosing_symbol(tree: ast.AST, line: int) -> str:
    best: tuple[int, str] | None = None

    def visit(node: ast.AST, prefix: tuple[str, ...]) -> None:
        nonlocal best
        for child in ast.iter_child_nodes(node):
            child_prefix = prefix
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                end_line = getattr(child, "end_lineno", child.lineno)
                if child.lineno <= line <= end_line:
                    child_prefix = (*prefix, child.name)
                    candidate = ".".join(child_prefix)
                    if best is None or len(child_prefix) > best[0]:
                        best = (len(child_prefix), candidate)
            visit(child, child_prefix)

    visit(tree, ())
    return best[1] if best else "<module>"


def _is_vendored(path: str) -> bool:
    return any(
        path == item["path"] or path.startswith(f"{item['path']}/")
        for item in VENDORED_SURFACES
    )


def _semantic_class(raw: RawFinding) -> tuple[str, str | None]:
    if raw.tool == "flake8":
        if raw.rule == "F821":
            return "correctness", "undefined-name"
        return "hygiene", None
    if raw.rule == "name-defined":
        return "correctness", "undefined-name"
    if raw.rule == "override":
        return "correctness", "invalid-override"
    if raw.rule == "return" and "Missing return statement" in raw.message:
        return "correctness", "explicit-runtime-error"
    if raw.rule == "operator" and "Unsupported operand types" in raw.message:
        return "correctness", "explicit-runtime-error"
    if raw.rule == "union-attr" or (
        raw.rule == "attr-defined" and '"None" has no attribute' in raw.message
    ):
        return "correctness", "unbound-resource"
    if raw.rule == "attr-defined" and raw.message.startswith("Module "):
        return "correctness", "impossible-import"
    return "contract", None


def _owner_for(raw: RawFinding, correctness_kind: str | None) -> str:
    path = raw.path
    if raw.rule == "override" and '"prepare"' in raw.message:
        return "Lane B / Task 02"
    if raw.rule == "override" and '"reduce"' in raw.message:
        return "Lane C / Task 03"
    if path.startswith(
        (
            "qitos/qita/",
            "qitos/render/",
            "qitos/trace/",
            "qitos/tracing/",
            "qitos/benchmark/",
            "qitos/recipes/benchmarks/",
            "qitos/evaluate/",
            "qitos/metric/",
            "qitos/hf/",
            "qitos/leaderboard/",
        )
    ):
        return "Lane D / Tasks 05/10"
    if path.startswith(
        (
            "qitos/models/",
            "qitos/kit/parser/",
            "qitos/kit/history/",
            "qitos/kit/context/",
            "qitos/kit/memory/",
            "qitos/kit/embedding/",
            "qitos/kit/search/",
        )
    ) or path in ("qitos/protocols.py", "qitos/prompting.py"):
        return "Lane B / Tasks 02/04"
    if path.startswith(
        (
            "qitos/checkpoint/",
            "qitos/mcp/",
            "qitos/func/",
            "qitos/kit/tool/",
            "qitos/kit/env/",
            "qitos/kit/permission/",
            "qitos/kit/skill/",
            "qitos/kit/vectorstore/",
            "qitos/kit/repl/",
            "qitos/kit/patterns/",
        )
    ):
        return "Lane C / Tasks 03/09/10"
    if path.startswith("qitos/recipes/") and correctness_kind:
        return "Lane C / Task 03"
    return "Lane D / Task 10 admission owner"


def build_findings(raw_findings: Iterable[RawFinding]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for raw in sorted(
        raw_findings,
        key=lambda item: (item.tool, item.path, item.line, item.column, item.rule),
    ):
        symbol, source_anchor = _source_context(raw.path, raw.line)
        semantic_category, correctness_kind = _semantic_class(raw)
        category = "vendored/generated" if _is_vendored(raw.path) else semantic_category
        prepared.append(
            {
                "tool": raw.tool,
                "rule": raw.rule,
                "path": raw.path,
                "line": raw.line,
                "column": raw.column,
                "message": raw.message,
                "symbol": symbol,
                "source_anchor": source_anchor,
                "category": category,
                "semantic_category": semantic_category,
                "correctness_kind": correctness_kind,
                "owner": _owner_for(raw, correctness_kind),
            }
        )

    occurrence_by_key: Counter[tuple[str, ...]] = Counter()
    for finding in prepared:
        occurrence_key = (
            finding["tool"],
            finding["rule"],
            finding["path"],
            finding["symbol"],
            finding["source_anchor"],
            finding["message"],
        )
        occurrence_by_key[occurrence_key] += 1
        occurrence = occurrence_by_key[occurrence_key]
        identity_parts = (*occurrence_key, str(occurrence))
        finding["occurrence"] = occurrence
        finding["id"] = hashlib.sha256(
            "\0".join(identity_parts).encode("utf-8")
        ).hexdigest()
    return prepared


def collect_findings() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    toolchain = verify_toolchain()
    return toolchain, build_findings(collect_raw_findings())


def _counts(findings: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(findings)
    active = [item for item in items if item["category"] != "vendored/generated"]
    vendored = [item for item in items if item["category"] == "vendored/generated"]

    def count(field: str, values: Iterable[dict[str, Any]]) -> dict[str, int]:
        return dict(sorted(Counter(str(item[field]) for item in values).items()))

    return {
        "total": len(items),
        "active": len(active),
        "vendored_generated": len(vendored),
        "by_tool": count("tool", items),
        "by_category": count("category", items),
        "by_semantic_category": count("semantic_category", items),
        "by_rule": count("rule", items),
        "by_owner": count("owner", items),
    }


def _new_baseline(
    toolchain: dict[str, Any],
    findings: list[dict[str, Any]],
    *,
    created_from: str = W1_BASELINE_COMMIT,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_from": created_from,
        "scope": {
            "root": "qitos",
            "active_non_vendored_policy": "all Python files under qitos outside special_surfaces",
            "flake8": "flake8 qitos (repository .flake8 configuration)",
            "mypy": "mypy --config-file=quality/mypy.ini qitos",
            "special_surfaces": list(VENDORED_SURFACES),
        },
        "toolchain": toolchain,
        "identity": {
            "fields": [
                "tool",
                "rule",
                "path",
                "symbol",
                "source_anchor",
                "message",
                "occurrence",
            ],
            "line_numbers_are_evidence_only": True,
        },
        "counts": _counts(findings),
        "findings": findings,
    }


def _write_baseline(baseline: dict[str, Any]) -> None:
    BASELINE_PATH.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_handoffs(baseline["findings"])


def _write_handoffs(findings: Iterable[dict[str, Any]]) -> None:
    correctness = [
        item for item in findings if item["semantic_category"] == "correctness"
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in correctness:
        grouped[item["owner"]].append(item)
    lines = [
        "# Correctness finding handoffs",
        "",
        f"Generated from `{BASELINE_PATH.relative_to(ROOT)}` at W1 baseline",
        f"`{W1_BASELINE_COMMIT}`. These findings are not hygiene debt. Lane A owns",
        "the gate; the named semantic lane owns the reproducer and fix.",
        "",
    ]
    for owner in sorted(grouped):
        lines.extend((f"## {owner}", ""))
        for item in sorted(
            grouped[owner], key=lambda value: (value["path"], value["line"])
        ):
            special = "; vendored" if item["category"] == "vendored/generated" else ""
            lines.append(
                f"- `{item['path']}:{item['line']}:{item['column']}` — "
                f"`{item['tool']}:{item['rule']}` / `{item['correctness_kind']}`"
                f"{special}: {item['message']}"
            )
        lines.append("")
    HANDOFF_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _finding_map(baseline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = baseline.get("findings")
    if not isinstance(findings, list):
        raise RatchetError("baseline findings must be a list")
    result: dict[str, dict[str, Any]] = {}
    for item in findings:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise RatchetError("baseline contains a finding without an id")
        if item["id"] in result:
            raise RatchetError(f"baseline contains duplicate finding id {item['id']}")
        result[item["id"]] = item
    return result


def _validate_exception(value: dict[str, Any], finding_ids: set[str]) -> dict[str, Any]:
    if value.get("schema_version") != 1:
        raise RatchetError("exception schema_version must be 1")
    maintainer = value.get("maintainer")
    reason = value.get("reason")
    expires_on = value.get("expires_on")
    declared_ids = value.get("finding_ids")
    if not isinstance(maintainer, str) or not maintainer.strip():
        raise RatchetError("exception maintainer is required")
    if not isinstance(reason, str) or len(reason.strip()) < 20:
        raise RatchetError("exception reason must contain at least 20 characters")
    if not isinstance(expires_on, str):
        raise RatchetError("exception expires_on is required")
    try:
        expiry = date.fromisoformat(expires_on)
    except ValueError as exc:
        raise RatchetError("exception expires_on must be YYYY-MM-DD") from exc
    if expiry <= date.today():
        raise RatchetError(f"exception expired or expires today: {expires_on}")
    if not isinstance(declared_ids, list) or not all(
        isinstance(item, str) for item in declared_ids
    ):
        raise RatchetError("exception finding_ids must be a list of strings")
    if set(declared_ids) != finding_ids:
        missing = sorted(finding_ids - set(declared_ids))
        extra = sorted(set(declared_ids) - finding_ids)
        raise RatchetError(
            f"exception finding_ids mismatch; missing={missing}, extra={extra}"
        )
    return {
        "maintainer": maintainer.strip(),
        "reason": reason.strip(),
        "expires_on": expires_on,
    }


def _validate_embedded_exceptions(findings: Iterable[dict[str, Any]]) -> None:
    for item in findings:
        exception = item.get("exception")
        if exception is None:
            continue
        if not isinstance(exception, dict):
            raise RatchetError(f"finding {item['id']} has malformed exception")
        _validate_exception(
            {
                "schema_version": 1,
                **exception,
                "finding_ids": [item["id"]],
            },
            {item["id"]},
        )


def _load_baseline_from_ref(ref: str) -> dict[str, Any] | None:
    completed = subprocess.run(
        ("git", "show", f"{ref}:quality/static_baseline.json"),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        return None
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RatchetError(f"baseline at {ref} is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RatchetError(f"baseline at {ref} is not an object")
    return value


def _validate_baseline_growth(baseline: dict[str, Any]) -> None:
    ref = os.environ.get("QUALITY_BASELINE_REF", "").strip()
    if not ref:
        return
    prior = _load_baseline_from_ref(ref)
    if prior is None:
        if baseline.get("created_from") != W1_BASELINE_COMMIT:
            raise RatchetError(
                f"no prior baseline at {ref}; bootstrap source is not W1"
            )
        return
    current_map = _finding_map(baseline)
    prior_ids = set(_finding_map(prior))
    added_ids = set(current_map) - prior_ids
    missing_exception = sorted(
        finding_id
        for finding_id in added_ids
        if not isinstance(current_map[finding_id].get("exception"), dict)
    )
    if missing_exception:
        raise RatchetError(
            "baseline grew relative to "
            f"{ref} without itemized maintainer exceptions:\n  "
            + "\n  ".join(missing_exception)
        )


def _format_finding(item: dict[str, Any]) -> str:
    return (
        f"{item['path']}:{item['line']}:{item['column']}: "
        f"{item['tool']}:{item['rule']} [{item['category']}] {item['message']}"
    )


def check() -> None:
    baseline = _load_json(BASELINE_PATH)
    baseline_map = _finding_map(baseline)
    _validate_embedded_exceptions(baseline_map.values())
    _validate_baseline_growth(baseline)
    toolchain, current_findings = collect_findings()
    if toolchain != baseline.get("toolchain"):
        raise RatchetError(
            "baseline toolchain differs from the pinned runtime; run a reviewed rules upgrade"
        )
    current_map = {item["id"]: item for item in current_findings}
    new_ids = set(current_map) - set(baseline_map)
    stale_ids = set(baseline_map) - set(current_map)
    if new_ids or stale_ids:
        parts: list[str] = []
        if new_ids:
            parts.append(
                "new findings (source debt; baseline additions require an exception):\n  "
                + "\n  ".join(
                    _format_finding(current_map[item]) for item in sorted(new_ids)
                )
            )
        if stale_ids:
            parts.append(
                "resolved findings still in baseline (baseline must shrink):\n  "
                + "\n  ".join(
                    _format_finding(baseline_map[item]) for item in sorted(stale_ids)
                )
            )
        raise RatchetError("\n".join(parts))
    expected_counts = baseline.get("counts")
    actual_counts = _counts(current_findings)
    if expected_counts != actual_counts:
        raise RatchetError("baseline counts do not match its current findings")
    print(
        "static quality ratchet passed: "
        f"{actual_counts['total']} findings baselined "
        f"({actual_counts['active']} active, "
        f"{actual_counts['vendored_generated']} vendored/generated)"
    )


def bootstrap() -> None:
    if BASELINE_PATH.exists():
        raise RatchetError(f"refusing to replace existing baseline {BASELINE_PATH}")
    toolchain, findings = collect_findings()
    baseline = _new_baseline(toolchain, findings)
    _write_baseline(baseline)
    print(f"created initial W1 baseline with {len(findings)} findings")


def update(exception_path: Path | None) -> None:
    baseline = _load_json(BASELINE_PATH)
    baseline_map = _finding_map(baseline)
    toolchain, findings = collect_findings()
    current_map = {item["id"]: item for item in findings}
    new_ids = set(current_map) - set(baseline_map)
    exception: dict[str, Any] | None = None
    if new_ids:
        if exception_path is None:
            raise RatchetError(
                f"baseline would grow by {len(new_ids)} findings; --exception is required"
            )
        exception = _validate_exception(_load_json(exception_path), new_ids)
    elif exception_path is not None:
        raise RatchetError("--exception was provided but the baseline does not grow")
    for finding_id, item in current_map.items():
        if finding_id in baseline_map and "exception" in baseline_map[finding_id]:
            item["exception"] = baseline_map[finding_id]["exception"]
        elif finding_id in new_ids and exception is not None:
            item["exception"] = exception
    updated = _new_baseline(
        toolchain,
        list(current_map.values()),
        created_from=str(baseline.get("created_from", W1_BASELINE_COMMIT)),
    )
    _write_baseline(updated)
    removed = len(set(baseline_map) - set(current_map))
    print(
        f"updated baseline: removed {removed}, added {len(new_ids)}, "
        f"total {len(current_map)}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="run diagnostics and enforce the baseline")
    subparsers.add_parser("bootstrap", help="create the one-time W1 baseline")
    update_parser = subparsers.add_parser(
        "update", help="shrink the baseline or add reviewed exceptions"
    )
    update_parser.add_argument("--exception", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            check()
        elif args.command == "bootstrap":
            bootstrap()
        else:
            update(args.exception)
    except RatchetError as exc:
        print(f"static quality ratchet failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

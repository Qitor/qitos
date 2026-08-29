from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import static_quality


FIXED_TODAY = date(2026, 8, 29)
PINNED_TOOLCHAIN: dict[str, Any] = {
    "python_runtime": "3.12.7",
    "mypy_target_python": "3.11",
    "tools": {
        "flake8": "7.0.0",
        "mccabe": "0.7.0",
        "mypy": "1.19.1",
        "pycodestyle": "2.11.1",
        "pyflakes": "3.2.0",
    },
}


def _finding(
    finding_id: str,
    *,
    path: str = "qitos/example.py",
    rule: str = "F401",
    symbol: str = "example_symbol",
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "tool": "flake8",
        "rule": rule,
        "path": path,
        "line": 7,
        "column": 1,
        "message": "'os' imported but unused",
        "symbol": symbol,
        "source_anchor": "fixed-source-anchor",
        "occurrence": 1,
        "category": "hygiene",
        "semantic_category": "hygiene",
        "correctness_kind": None,
        "owner": "Lane D / Task 10 admission owner",
    }


def _baseline(
    findings: list[dict[str, Any]],
    *,
    created_from: str = static_quality.W1_BASELINE_COMMIT,
    toolchain: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return static_quality._new_baseline(
        deepcopy(toolchain or PINNED_TOOLCHAIN),
        deepcopy(findings),
        created_from=created_from,
    )


def _install_baseline_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    baseline: dict[str, Any],
) -> Path:
    quality_dir = tmp_path / "quality"
    quality_dir.mkdir()
    baseline_path = quality_dir / "static_baseline.json"
    baseline_path.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(static_quality, "ROOT", tmp_path)
    monkeypatch.setattr(static_quality, "BASELINE_PATH", baseline_path)
    monkeypatch.setattr(
        static_quality, "HANDOFF_PATH", quality_dir / "correctness_handoffs.md"
    )
    monkeypatch.delenv("QUALITY_BASELINE_REF", raising=False)
    return baseline_path


def test_flake8_parser_retains_rule_path_and_position() -> None:
    findings = static_quality.parse_flake8(
        "qitos/example.py:7:11: F821 undefined name 'missing'\n"
    )

    assert findings == [
        static_quality.RawFinding(
            tool="flake8",
            rule="F821",
            path="qitos/example.py",
            line=7,
            column=11,
            message="undefined name 'missing'",
        )
    ]


def test_mypy_parser_rejects_unparseable_errors() -> None:
    with pytest.raises(static_quality.RatchetError, match="unparseable"):
        static_quality.parse_mypy("qitos/example.py: error: no position [misc]\n")


def test_flake8_parser_rejects_unparseable_diagnostics() -> None:
    with pytest.raises(static_quality.RatchetError, match="unparseable"):
        static_quality.parse_flake8("flake8 emitted an unexpected line\n")


@pytest.mark.parametrize(
    ("finding", "category", "kind"),
    [
        (
            static_quality.RawFinding(
                "flake8", "F821", "qitos/kit/parser/x.py", 1, 1, "undefined"
            ),
            "correctness",
            "undefined-name",
        ),
        (
            static_quality.RawFinding(
                "mypy", "override", "qitos/recipes/x.py", 1, 1, 'Signature of "reduce"'
            ),
            "correctness",
            "invalid-override",
        ),
        (
            static_quality.RawFinding(
                "mypy", "assignment", "qitos/render/x.py", 1, 1, "incompatible"
            ),
            "contract",
            None,
        ),
    ],
)
def test_semantic_classification(
    finding: static_quality.RawFinding, category: str, kind: str | None
) -> None:
    assert static_quality._semantic_class(finding) == (category, kind)


def test_vendored_correctness_retains_underlying_class(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "qitos/benchmark/tau_bench/port/example.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = missing\n", encoding="utf-8")
    monkeypatch.setattr(static_quality, "ROOT", tmp_path)

    findings = static_quality.build_findings(
        [
            static_quality.RawFinding(
                "flake8",
                "F821",
                "qitos/benchmark/tau_bench/port/example.py",
                1,
                9,
                "undefined name 'missing'",
            )
        ]
    )

    assert findings[0]["category"] == "vendored/generated"
    assert findings[0]["semantic_category"] == "correctness"
    assert findings[0]["correctness_kind"] == "undefined-name"
    assert findings[0]["owner"] == "Lane D / Tasks 05/10"


def test_identity_is_stable_when_only_line_number_moves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "qitos/example.py"
    source.parent.mkdir()
    source.write_text("\nvalue = missing\n", encoding="utf-8")
    monkeypatch.setattr(static_quality, "ROOT", tmp_path)
    moved = static_quality.build_findings(
        [
            static_quality.RawFinding(
                "flake8", "F821", "qitos/example.py", 2, 9, "undefined name 'missing'"
            )
        ]
    )[0]
    source.write_text("\n\nvalue = missing\n", encoding="utf-8")
    moved_again = static_quality.build_findings(
        [
            static_quality.RawFinding(
                "flake8", "F821", "qitos/example.py", 3, 9, "undefined name 'missing'"
            )
        ]
    )[0]

    assert moved["id"] == moved_again["id"]
    assert moved["line"] != moved_again["line"]


def test_exception_requires_maintainer_reason_and_future_expiry() -> None:
    finding_id = "abc"
    valid = {
        "schema_version": 1,
        "maintainer": "@quality-owner",
        "reason": "Temporary compatibility debt with a scheduled owner.",
        "expires_on": "2026-09-30",
        "finding_ids": [finding_id],
    }

    exception = static_quality._validate_exception(
        valid, {finding_id}, today=FIXED_TODAY
    )

    assert exception["maintainer"] == "@quality-owner"


@pytest.mark.parametrize("expires_on", ["2026-08-28", "2026-08-29"])
def test_exception_expired_or_expiring_today_is_rejected(expires_on: str) -> None:
    value = {
        "schema_version": 1,
        "maintainer": "@quality-owner",
        "reason": "Temporary compatibility debt with a scheduled owner.",
        "expires_on": expires_on,
        "finding_ids": ["abc"],
    }

    with pytest.raises(static_quality.RatchetError, match="expired or expires today"):
        static_quality._validate_exception(value, {"abc"}, today=FIXED_TODAY)


def test_toolchain_mismatch_is_reported_as_rules_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        static_quality,
        "_tool_versions",
        lambda: {
            "flake8": "7.0.0",
            "mccabe": "0.7.0",
            "mypy": "1.19.1",
            "pycodestyle": "2.11.1",
            "pyflakes": "3.2.0",
        },
    )
    with pytest.raises(static_quality.RatchetError, match="rules upgrade"):
        static_quality.verify_toolchain(
            {
                "python_runtime": "0.0.0",
                "tools": {
                    "flake8": "7.0.0",
                    "mccabe": "0.7.0",
                    "mypy": "1.19.1",
                    "pycodestyle": "2.11.1",
                    "pyflakes": "3.2.0",
                },
            }
        )


def test_check_blocks_new_finding_and_reports_rule_path_and_symbol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    baseline_path = _install_baseline_fixture(monkeypatch, tmp_path, _baseline([]))
    before = baseline_path.read_bytes()
    probe = _finding(
        "probe-id",
        path="qitos/_quality_ratchet_probe.py",
        rule="F401",
        symbol="probe_symbol",
    )
    monkeypatch.setattr(
        static_quality,
        "collect_findings",
        lambda: (deepcopy(PINNED_TOOLCHAIN), [probe]),
    )

    with pytest.raises(static_quality.RatchetError) as error:
        static_quality.check()

    message = str(error.value)
    assert "new findings (source debt" in message
    assert "qitos/_quality_ratchet_probe.py" in message
    assert "flake8:F401" in message
    assert "symbol=probe_symbol" in message
    assert "rules upgrade" not in message
    assert baseline_path.read_bytes() == before


def test_check_blocks_resolved_finding_left_in_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stale = _finding("stale-id")
    _install_baseline_fixture(monkeypatch, tmp_path, _baseline([stale]))
    monkeypatch.setattr(
        static_quality,
        "collect_findings",
        lambda: (deepcopy(PINNED_TOOLCHAIN), []),
    )

    with pytest.raises(static_quality.RatchetError, match="baseline must shrink"):
        static_quality.check()


def test_check_reports_rules_upgrade_separately_from_source_debt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_baseline_fixture(monkeypatch, tmp_path, _baseline([]))
    upgraded = deepcopy(PINNED_TOOLCHAIN)
    upgraded["tools"]["flake8"] = "8.0.0"
    monkeypatch.setattr(
        static_quality, "collect_findings", lambda: (upgraded, [_finding("new")])
    )

    with pytest.raises(static_quality.RatchetError) as error:
        static_quality.check()

    assert "reviewed rules upgrade" in str(error.value)
    assert "source debt" not in str(error.value)


def test_baseline_growth_without_exception_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = _baseline([_finding("existing")])
    current = _baseline([_finding("existing"), _finding("added")])
    monkeypatch.setenv("QUALITY_BASELINE_REF", "base-ref")
    monkeypatch.setattr(static_quality, "_load_baseline_from_ref", lambda ref: prior)

    with pytest.raises(static_quality.RatchetError, match="without itemized"):
        static_quality._validate_baseline_growth(current)


def test_itemized_future_exception_allows_baseline_growth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = _baseline([_finding("existing")])
    added = _finding("added")
    added["exception"] = {
        "maintainer": "@quality-owner",
        "reason": "Temporary compatibility debt with a scheduled owner.",
        "expires_on": "2026-09-30",
    }
    current = _baseline([_finding("existing"), added])
    monkeypatch.setenv("QUALITY_BASELINE_REF", "base-ref")
    monkeypatch.setattr(static_quality, "_load_baseline_from_ref", lambda ref: prior)
    monkeypatch.setattr(static_quality, "_today", lambda: FIXED_TODAY)

    static_quality._validate_embedded_exceptions(current["findings"])
    static_quality._validate_baseline_growth(current)


def test_missing_prior_baseline_rejects_non_w1_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _baseline([], created_from="not-the-w1-source")
    monkeypatch.setenv("QUALITY_BASELINE_REF", "base-ref")
    monkeypatch.setattr(static_quality, "_load_baseline_from_ref", lambda ref: None)

    with pytest.raises(static_quality.RatchetError, match="bootstrap source is not W1"):
        static_quality._validate_baseline_growth(current)


def test_explicit_update_shrinks_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    kept = _finding("kept")
    removed = _finding("removed", path="qitos/removed.py")
    baseline_path = _install_baseline_fixture(
        monkeypatch, tmp_path, _baseline([kept, removed])
    )
    monkeypatch.setattr(
        static_quality,
        "collect_findings",
        lambda: (deepcopy(PINNED_TOOLCHAIN), [kept]),
    )

    static_quality.update(None)

    updated = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert [item["id"] for item in updated["findings"]] == ["kept"]


def test_explicit_update_requires_and_applies_itemized_growth_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    existing = _finding("existing")
    added = _finding("added", path="qitos/added.py")
    baseline_path = _install_baseline_fixture(
        monkeypatch, tmp_path, _baseline([existing])
    )
    before = baseline_path.read_bytes()
    monkeypatch.setattr(static_quality, "_today", lambda: FIXED_TODAY)
    monkeypatch.setattr(
        static_quality,
        "collect_findings",
        lambda: (deepcopy(PINNED_TOOLCHAIN), [existing, added]),
    )

    with pytest.raises(static_quality.RatchetError, match="--exception is required"):
        static_quality.update(None)
    assert baseline_path.read_bytes() == before

    exception_path = tmp_path / "exception.json"
    exception_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "maintainer": "@quality-owner",
                "reason": "Temporary compatibility debt with a scheduled owner.",
                "expires_on": "2026-09-30",
                "finding_ids": ["added"],
            }
        ),
        encoding="utf-8",
    )
    static_quality.update(exception_path)

    updated = json.loads(baseline_path.read_text(encoding="utf-8"))
    updated_by_id = {item["id"]: item for item in updated["findings"]}
    assert updated_by_id["added"]["exception"]["maintainer"] == "@quality-owner"

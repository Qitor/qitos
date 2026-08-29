from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts import static_quality


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
        "expires_on": (date.today() + timedelta(days=30)).isoformat(),
        "finding_ids": [finding_id],
    }

    exception = static_quality._validate_exception(valid, {finding_id})

    assert exception["maintainer"] == "@quality-owner"
    expired = {**valid, "expires_on": date.today().isoformat()}
    with pytest.raises(static_quality.RatchetError, match="expired"):
        static_quality._validate_exception(expired, {finding_id})


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

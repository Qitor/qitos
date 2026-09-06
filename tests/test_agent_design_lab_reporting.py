import importlib.util
import json
from pathlib import Path

import pytest


def reporter():
    spec = importlib.util.spec_from_file_location(
        "lab_report",
        Path(__file__).resolve().parents[1] / "scripts/report_agent_design_lab.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summary_has_no_raw_values_and_does_not_count_false_success(tmp_path):
    (tmp_path / "installed-source.json").write_text('{"private-path": "secret"}')
    rows = [
        {
            "case": "react-0-0-default-recall",
            "exit_code": 0,
            "evaluation": {"passed": False, "message": "secret"},
            "report_present": True,
            "interventions": ["private-path"],
        },
        {
            "case": "react-0-1-default-recall",
            "exit_code": 0,
            "evaluation": {"passed": True},
            "report_present": True,
        },
    ]
    (tmp_path / "ledger.json").write_text(json.dumps(rows))
    result = reporter().summarize([tmp_path])
    assert result["counts"]["react/default/recall"]["passed"] == 1
    assert result["counts"]["react/default/recall"]["interventions"] == 1
    assert "secret" not in json.dumps(result)
    assert "private-path" not in json.dumps(result)
    with pytest.raises(ValueError, match="invalid_or_duplicate_case"):
        reporter().summarize([tmp_path, tmp_path])


def test_summary_rejects_untrusted_case_name_without_echo(tmp_path):
    (tmp_path / "installed-source.json").write_text("{}")
    (tmp_path / "ledger.json").write_text('[{"case": "private-secret"}]')
    with pytest.raises(ValueError, match="^invalid_or_duplicate_case$"):
        reporter().summarize([tmp_path])

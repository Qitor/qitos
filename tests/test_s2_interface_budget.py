"""Independent current-surface budget for S2 runtime convergence."""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

import qitos
from qitos.engine.engine import Engine


ROOT = Path(__file__).resolve().parents[1]
BUDGET = ROOT / "tests/fixtures/public_surface/s2-current-interface-budget.json"
CATEGORIES = {
    "beginner-facing",
    "extension-facing",
    "persistence-internal",
    "internal-private",
}
CANDIDATE_TRAJECTORY_EXPORTS = {
    "Trajectory",
    "TrajectoryRecord",
    "TrajectoryQuery",
    "TrajectoryStore",
    "TrajectoryReader",
    "TrajectoryExporter",
    "MemoryTrajectoryStore",
    "JsonTrajectoryStore",
}


def test_every_s2_aggregate_export_is_classified_once() -> None:
    payload = json.loads(BUDGET.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "qitos.s2_current_interface_budget/v1"
    total = 0
    for module_name, categories in payload["modules"].items():
        assert set(categories) == CATEGORIES
        classified = [
            name for category in CATEGORIES for name in categories[category]
        ]
        assert len(classified) == len(set(classified)), module_name
        module = importlib.import_module(module_name)
        assert set(classified) == set(module.__all__), module_name
        total += len(classified)
    assert total == payload["reviewed_policy"]["aggregate_exports"]


def test_s2_keeps_beginner_surface_and_composition_approval_bounded() -> None:
    payload = json.loads(BUDGET.read_text(encoding="utf-8"))
    policy = payload["reviewed_policy"]
    assert len(qitos.__all__) == policy["root_exports"] == 41
    parameters = inspect.signature(Engine.__init__).parameters
    assert len(parameters) == policy["engine_init_parameters_including_self"] == 34
    assert "runtime" in parameters
    assert policy["engine_runtime_parameter_approved"] is True


def test_candidate_trajectory_is_not_an_aggregate_public_export() -> None:
    import qitos.tracing

    assert CANDIDATE_TRAJECTORY_EXPORTS.isdisjoint(qitos.tracing.__all__)


def test_no_generation_suffix_type_names_enter_public_aggregates() -> None:
    payload = json.loads(BUDGET.read_text(encoding="utf-8"))
    forbidden = ("V1", "V2", "Legacy", "Next", "New")
    for categories in payload["modules"].values():
        for category in CATEGORIES - {"internal-private"}:
            assert all(not name.endswith(forbidden) for name in categories[category])

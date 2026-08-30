"""Executable public-surface budget for G2 convergence contracts."""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUDGET = ROOT / "tests" / "fixtures" / "public_surface" / "g2-interface-budget.json"
CATEGORIES = {
    "beginner-facing",
    "extension-facing",
    "persistence-internal",
    "internal-private",
}


def test_every_g2_module_export_has_exactly_one_interface_classification() -> None:
    payload = json.loads(BUDGET.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "qitos.g2_interface_budget/v1"
    classified_count = 0
    for module_name, categories in payload["modules"].items():
        assert set(categories) == CATEGORIES
        flattened = [
            name
            for category in CATEGORIES
            for name in categories[category]
        ]
        assert len(flattened) == len(set(flattened)), module_name
        module = importlib.import_module(module_name)
        assert set(flattened) == set(module.__all__), module_name
        classified_count += len(flattened)
    assert classified_count == 127


def test_g2_contracts_add_no_root_exports_and_no_engine_parameters() -> None:
    import qitos
    from qitos.engine.engine import Engine

    convergence_names = {
        "ArtifactRef",
        "ContinuationIdentity",
        "ProviderCapabilities",
        "RequestView",
        "SessionIdentity",
        "SessionSnapshot",
        "SnapshotComponentRegistry",
        "WorkGraph",
    }
    assert convergence_names.isdisjoint(qitos.__all__)
    parameters = set(inspect.signature(Engine.__init__).parameters)
    assert {
        "pause",
        "resume",
        "fork",
        "session_store",
        "snapshot_registry",
        "trajectory_store",
    }.isdisjoint(parameters)

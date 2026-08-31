"""Architecture gates for the S2 G3 runtime convergence."""

from __future__ import annotations

import ast
from pathlib import Path

from qitos.core.artifact import ArtifactRef as CoreArtifactRef
from qitos.tracing.trajectory import ArtifactRef as TrajectoryArtifactRef


ROOT = Path(__file__).resolve().parents[1]


def test_framework_has_one_artifact_ref_implementation() -> None:
    definitions: list[str] = []
    for path in (ROOT / "qitos").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef))
            and node.name == "ArtifactRef"
            for node in ast.walk(tree)
        ):
            definitions.append(str(path.relative_to(ROOT)))

    assert definitions == ["qitos/core/artifact.py"]


def test_trajectory_uses_canonical_artifact_identity() -> None:
    assert TrajectoryArtifactRef is CoreArtifactRef


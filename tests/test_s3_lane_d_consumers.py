from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, filename: str) -> Any:
    path = ROOT / "examples" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_two_unrelated_consumers_use_the_same_framework_primitives_offline() -> None:
    module = _module("s3_consumers", "s3_work_graph_consumers.py")
    research = module.bounded_research_fan_out()
    review = module.proposal_critique_transfer()

    assert len(research.graph.work_items) == 3
    assert research.graph.joins[0].policy == "all_successful"
    assert len(research.graph.joins[0].accepted_child_ids) == 2
    assert research.inspection["session_summary"]["work_item_count"] == 3
    assert research.inspection["timeline"]

    assert len(review.graph.work_items) == 1
    assert review.graph.transfers[0].committed_generation == 1
    assert review.inspection["work_items"][0]["owner_generation"] == 1
    assert len(review.inspection["work_items"][0]["ownership_history"]) == 1

    source = inspect.getsource(module)
    assert "ThreadPoolExecutor" not in source
    assert "_Engine" not in source
    assert "OpenAI" not in source
    assert "WorkGraph" in source and "SessionIdentity" in source


def test_coding_agent_acceptance_is_compact_public_and_executes_integrated_runtime() -> None:
    module = _module("s3_coding_acceptance", "s3_coding_agent_acceptance.py")
    status = module.current_status()
    assert status.status == "completed"
    assert status.code == "qualified_public_shape"
    assert status.child_count == 1

    path = ROOT / "examples" / "s3_coding_agent_acceptance.py"
    source = path.read_text(encoding="utf-8")
    code_lines = [
        line for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert 50 <= len(code_lines) <= 100
    assert "session._" not in source
    assert "restored._" not in source
    assert ".session(" in source
    assert ".run()" in source
    assert ".restore(" in source
    assert ".delegate(" in source
    assert ".join(" in source
    assert ".inspect()" in source

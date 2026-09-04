"""Process tools preserve a live worker in the canonical bounded-poll result."""
from types import SimpleNamespace

import pytest

from qitos.kit.toolset.env_coding import EnvCodingToolSet


@pytest.mark.parametrize("name", ["poll_process", "terminate_process", "run_command"])
def test_live_worker_is_not_replaced_by_semantic_error(name):
    raw = {"status": "running", "worker_still_running": True, "outcome_unknown": True}
    ops = SimpleNamespace(poll=lambda *a: raw, terminate=lambda *a: raw,
                          run=lambda *a, **kw: raw)
    tools = {tool.name: tool for tool in EnvCodingToolSet().tools()}
    args = ({"command": "owned"} if name == "run_command" else
            {"process_id": "owned", "owner_generation": 0})
    result = tools[name].execute(args, {"env": object(), "ops": {"process": ops, "process_control": ops}})
    assert result.worker_still_running and result.outcome_unknown
    assert result.status in {"timed_out", "cancelled"}
    assert result.error_kind == "execution"

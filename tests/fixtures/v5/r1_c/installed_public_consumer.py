"""Run from outside the checkout using an installed wheel and public APIs."""
import json
from pathlib import Path
import sys

import qitos
from qitos.core.action import Action
from qitos.core.observation import Observation
from qitos.core.tool_registry import ToolRegistry
from qitos.core.tool_result import ToolResult
from qitos.engine.action_executor import ActionExecutor
from qitos.kit.permission.pipeline import PermissionMode, PermissionPipeline
from qitos.kit.toolset.coding import CodingToolSet


def run(root):
    assert "site-packages" in qitos.__file__, qitos.__file__
    root.mkdir()
    file = root / "sample.txt"
    file.write_text("L1\nL2\nL3\nL4\n")
    registry = ToolRegistry().include_toolset(CodingToolSet(
        workspace_root=str(root), expose_modern_names=True))
    executor = ActionExecutor(tool_registry=registry, auto_approve=True,
                              permission_pipeline=PermissionPipeline(mode=PermissionMode.BYPASS))
    read = executor.execute_one(Action(name="Read", args={"file_path": "sample.txt", "offset": 2, "limit": 2}))
    assert read.status == "success" and read.output == "3\tL3\n4\tL4"
    file.write_text("x x x")
    args = {"file_path": "sample.txt", "old_string": "x", "new_string": "y"}
    denied = executor.execute_one(Action(name="Edit", args=args))
    assert denied.error_code == "ambiguous_edit" and file.read_text() == "x x x"
    edited = executor.execute_one(Action(name="Edit", args={**args, "replace_all": True}))
    assert edited.status == "success" and file.read_text() == "y y y"
    obs = Observation(step_id=1, task="before", action_results=[read])
    snapshot = obs.to_dict()
    obs.task = "after"
    assert obs["task"] == "after" and snapshot["task"] == "before"
    obs.update(task="mapped", step=2, step_id=2)
    assert obs.task == "mapped" and obs.step_id == 2
    assert isinstance(obs.action_results[0], ToolResult)
    assert json.loads(json.dumps(obs))["action_results"] == obs.to_legacy_dict()["action_results"]
    print("installed public API: Read/Edit/Observation passed")


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve())

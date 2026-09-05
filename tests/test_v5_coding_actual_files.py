"""Read/Edit outcomes through the real registry, executor and filesystem."""
import hashlib

import pytest

from qitos.core.action import Action
from qitos.core.tool_registry import ToolRegistry
from qitos.engine.action_executor import ActionExecutor
from qitos.kit.permission.pipeline import PermissionMode, PermissionPipeline
from qitos.kit.tool.internal.coding_impl import CodingToolSet
from qitos.kit.toolset.env_coding import EnvCodingToolSet
from qitos.kit.env import HostEnv


def _executor(root, *, env_tools=False, deny=False):
    toolset = (EnvCodingToolSet() if env_tools else CodingToolSet(
        workspace_root=str(root), expose_modern_names=True))
    registry = ToolRegistry().include_toolset(toolset)
    return ActionExecutor(tool_registry=registry, auto_approve=True, permission_pipeline=PermissionPipeline(
        mode=PermissionMode.PLAN if deny else PermissionMode.BYPASS))


@pytest.mark.parametrize("offset,limit,expected", [(2, 2, "3\tL3\n4\tL4"), (0, 2, "1\tL1\n2\tL2"), (4, 2, "")])
def test_read_pages_once(tmp_path, offset, limit, expected):
    (tmp_path / "file.txt").write_text("L1\nL2\nL3\nL4\n")
    result = _executor(tmp_path).execute_one(Action(name="Read", args={
        "file_path": "file.txt", "offset": offset, "limit": limit}))
    assert result.status == "success"
    assert result.output == expected


@pytest.mark.parametrize("content,expected", [("", ""), ("\n", "1\t"), ("\n\n", "1\t\n2\t")])
def test_read_empty_and_blank_lines(tmp_path, content, expected):
    (tmp_path / "file.txt").write_text(content)
    result = _executor(tmp_path).execute_one(Action(name="Read", args={"file_path": "file.txt"}))
    assert result.status == "success"
    assert result.output == expected


@pytest.mark.parametrize("args", [{"offset": -1}, {"limit": 0}, {"offset": "bad"}, {"limit": -1}, {"offset": True}])
def test_read_invalid_window_is_failure(tmp_path, args):
    (tmp_path / "file.txt").write_text("unchanged")
    result = _executor(tmp_path).execute_one(Action(name="Read", args={"file_path": "file.txt", **args}))
    assert result.status != "success"
    assert (tmp_path / "file.txt").read_text() == "unchanged"


def test_read_truncation_is_explicit(tmp_path):
    (tmp_path / "file.txt").write_text("x" * 200_001 + "\nsecond\n")
    result = _executor(tmp_path).execute_one(Action(name="Read", args={"file_path": "file.txt"}))
    assert result.status == "success"
    assert result.truncated
    assert result.metadata["selection_receipt"]["has_more"]
    assert "second" not in result.output


@pytest.mark.parametrize("env_tools", [False, True])
@pytest.mark.parametrize("case", ["ambiguous", "all", "missing", "sha", "denied"])
def test_edit_actual_content_and_outcome(tmp_path, env_tools, case):
    file = tmp_path / "file.txt"
    file.write_text("x x x")
    original_sha = hashlib.sha256(file.read_bytes()).hexdigest()
    env = HostEnv(workspace_root=str(tmp_path)) if env_tools else None
    args = ({"path": "file.txt", "old_text": "x", "replacement": "y"} if env_tools
            else {"file_path": "file.txt", "old_string": "x", "new_string": "y"})
    args["replace_all"] = case == "all"
    if case == "missing":
        args["old_text" if env_tools else "old_string"] = "absent"
    if case == "sha":
        args["expected_sha256"] = "0" * 64
    result = _executor(tmp_path, env_tools=env_tools, deny=case == "denied").execute_one(
        Action(name="edit_file" if env_tools else "Edit", args=args), env=env)
    if case == "all":
        assert result.status == "success", result
        assert file.read_text() == "y y y"
        if env_tools:
            assert result.effect_state == "committed"
    else:
        assert result.status != "success", result
        assert hashlib.sha256(file.read_bytes()).hexdigest() == original_sha
        if case == "sha":
            assert result.error_code == "stale_file"
        if case == "ambiguous":
            assert result.error_code == "ambiguous_edit"
        assert result.effect_state != "committed"


def test_env_tools_never_fall_back_to_host(tmp_path):
    file = tmp_path / "file.txt"
    file.write_text("x")
    result = _executor(tmp_path, env_tools=True).execute_one(Action(name="edit_file", args={
        "path": "file.txt", "old_text": "x", "replacement": "y"}))
    assert result.status != "success"
    assert file.read_text() == "x"

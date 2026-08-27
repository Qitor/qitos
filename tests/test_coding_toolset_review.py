"""Tests for CodingToolSet command-review behaviour used by benchmark adapters.

Extracted from tests/test_cybergym_agent_poc_profile.py when the vendored
cybergym agent tests were removed; these two cases cover the in-tree
CodingToolSet and must keep running.
"""

from __future__ import annotations

from pathlib import Path


def test_coding_toolset_internal_bash_can_allow_review_for_benchmark_adapters(
    tmp_path: Path,
) -> None:
    from qitos.kit.tool.internal.coding_impl import CodingToolSet

    script = tmp_path / "emit.py"
    script.write_text("print('BASH_OK')\n", encoding="utf-8")

    coding = CodingToolSet(workspace_root=str(tmp_path))

    result = coding._run_bash_command(  # noqa: SLF001 - verifies benchmark adapter hook.
        "python3 emit.py",
        allow_needs_review=True,
    )

    assert result["status"] == "success"
    assert result["returncode"] == 0
    assert result["stdout"].strip() == "BASH_OK"


def test_coding_toolset_run_command_still_requires_review_by_default(tmp_path: Path) -> None:
    from qitos.kit.tool.internal.coding_impl import CodingToolSet

    script = tmp_path / "emit.py"
    script.write_text("print('BASH_OK')\n", encoding="utf-8")
    coding = CodingToolSet(workspace_root=str(tmp_path))

    result = coding.run_command(command="python3 emit.py")

    assert result["status"] == "needs_user_input"
    assert "Command needs review" in result["message"]

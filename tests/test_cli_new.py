"""Tests for qit new and qit list-templates CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from qitos.cli import main as qit_main


class TestListTemplates:
    def test_list_all_templates(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = qit_main(["list-templates"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "qitos_new_agent" in out
        assert "react" in out

    def test_list_scaffold_only(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = qit_main(["list-templates", "--type", "scaffold"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "qitos_new_agent" in out
        assert "Scaffold templates" in out
        # Method templates should not appear
        assert "react" not in out

    def test_list_method_only(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = qit_main(["list-templates", "--type", "method"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "react" in out
        assert "Method templates" in out
        # Scaffold templates should not appear
        assert "qitos_new_agent" not in out


class TestNewCommand:
    def test_new_with_missing_template(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = qit_main(["new", "--template", "nonexistent"])
        assert rc == 1
        out = capsys.readouterr().err
        assert "not found" in out

    def test_new_with_method_template_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        # 'react' is a method template, not a scaffold template
        rc = qit_main(["new", "--template", "react"])
        assert rc == 1
        out = capsys.readouterr().err
        assert "not a scaffold template" in out

    def test_new_does_not_require_cookiecutter(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        import sys
        saved = {}
        for key in list(sys.modules):
            if key.startswith("cookiecutter"):
                saved[key] = sys.modules.pop(key)
        try:
            # Ensure cookiecutter.main is not importable
            sys.modules["cookiecutter"] = None
            sys.modules["cookiecutter.main"] = None
            rc = qit_main(
                [
                    "new",
                    "--agent-name",
                    "test_agent",
                    "--output-dir",
                    str(tmp_path),
                ]
            )
            assert rc == 0
            assert (tmp_path / "test_agent" / "agent.yaml").is_file()
            assert "Created agent project" in capsys.readouterr().out
        finally:
            sys.modules.update(saved)
            for key in list(sys.modules):
                if key.startswith("cookiecutter") and key not in saved:
                    del sys.modules[key]

    def test_new_creates_installable_source_layout(self, tmp_path: Path) -> None:
        rc = qit_main([
            "new",
            "--agent-name", "my_cool_agent",
            "--agent-description", "A cool agent",
            "--output-dir", str(tmp_path),
        ])
        assert rc == 0
        root = tmp_path / "my_cool_agent"
        assert (root / "pyproject.toml").is_file()
        assert (root / "src" / "my_cool_agent" / "app.py").is_file()
        assert "mode: durable" in (root / "agent.yaml").read_text()
        assert "store: sqlite" in (root / "agent.yaml").read_text()

    def test_new_passes_extra_context(self, tmp_path: Path) -> None:
        rc = qit_main([
            "new",
            "--agent-name", "my_agent",
            "--agent-description", "My test agent",
            "--author", "tester",
            "--default-model", "qwen-plus",
            "--max-steps", "20",
            "--output-dir", str(tmp_path),
        ])
        assert rc == 0
        root = tmp_path / "my_agent"
        assert "My test agent" in (root / "README.md").read_text()
        assert "max_steps: 20" in (root / "agent.yaml").read_text()

    def test_new_no_input_flag(self, tmp_path: Path) -> None:
        rc = qit_main([
            "new",
            "--no-input",
            "--output-dir", str(tmp_path),
        ])
        assert rc == 0
        assert (tmp_path / "my_agent" / "agent.yaml").is_file()


class TestMainHelp:
    def test_help_shows_new_and_list_templates(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = qit_main(["--help"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "new" in out
        assert "list-templates" in out

    def test_no_args_shows_new_and_list_templates(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = qit_main([])
        assert rc == 1
        out = capsys.readouterr().out
        assert "new" in out
        assert "list-templates" in out

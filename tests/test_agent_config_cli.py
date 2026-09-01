"""Thin CLI coverage for the canonical AgentConfig launch path."""

from __future__ import annotations

import json
from pathlib import Path

import qitos.config
from qitos.cli import main


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "config" / "agent.yaml"


def test_qit_run_dry_run_uses_strict_loader_without_resolving_credentials(
    capsys: object,
) -> None:
    assert main(["run", "--config", str(FIXTURE), "--dry-run"]) == 0
    payload = json.loads(getattr(capsys, "readouterr")().out)
    assert payload["schema"] == "qitos.agent/v1"
    assert len(payload["config_digest"]) == 64


def test_qit_run_dispatches_to_the_same_config_runner(
    monkeypatch: object, capsys: object, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_run(config: object, *, credential_resolver: object, task: str) -> dict[str, object]:
        captured.update(
            config=config,
            credential_resolver=credential_resolver,
            task=task,
        )
        return {"status": "passed"}

    getattr(monkeypatch, "setattr")(qitos.config, "run_agent_config", fake_run)
    assert (
        main(
            [
                "run",
                "--config",
                str(FIXTURE),
                "--credentials",
                str(tmp_path / "credentials.yaml"),
                "--task",
                "override task",
            ]
        )
        == 0
    )
    assert getattr(captured["config"], "name") == "example-coding-agent"
    assert captured["task"] == "override task"
    assert json.loads(getattr(capsys, "readouterr")().out) == {"status": "passed"}

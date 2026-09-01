from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "e2e" / "s3_g4_configured_process_fixture.py"


def _run(phase: str, config: Path, control: Path) -> dict[str, object]:
    environment = dict(os.environ)
    environment.update(
        {
            "QITOS_CONFIGURED_PHASE": phase,
            "QITOS_CONFIGURED_CONFIG": str(config),
            "QITOS_CONFIGURED_CONTROL": str(control),
        }
    )
    completed = subprocess.run(
        [sys.executable, str(FIXTURE)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_canonical_config_docker_pause_restore_trajectory_and_cleanup(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "calculator.py").write_text(
        "def clamp(value: int, low: int, high: int) -> int:\n"
        "    return min(low, max(value, high))\n",
        encoding="utf-8",
    )
    tests = workspace / "tests"
    tests.mkdir()
    (tests / "test_calculator.py").write_text(
        "from calculator import clamp\n\n"
        "def test_inside(): assert clamp(5, 0, 10) == 5\n"
        "def test_below(): assert clamp(-2, 0, 10) == 0\n"
        "def test_above(): assert clamp(12, 0, 10) == 10\n",
        encoding="utf-8",
    )
    trajectory = tmp_path / "trajectory.json"
    database = tmp_path / "sessions.sqlite3"
    config = tmp_path / "agent.yaml"
    config.write_text(
        f"""schema: qitos.agent
agent:
  name: configured-process-agent
  protocol: json_decision_multi_v1
  parser: auto
model:
  provider: openai_compatible
  model: fake-configured-coder
  credential:
    ref: offline-qualified
  request:
    temperature: 0
    max_tokens: 10240
    timeout_seconds: 180
    retries: 0
tools:
  preset: env_coding
  include: []
  options:
    native_tool_calls_required: true
  policy: required_before_final
runtime:
  environment:
    type: docker
    image: openclaw:staged
    workspace: {workspace}
    container_workspace: /workspace
    network: none
    read_only_root: true
    cap_drop: true
    no_new_privileges: true
    pids_limit: 256
    memory_mb: 2048
    cpus: 2.0
    cleanup_required: true
  session:
    enabled: true
    store: sqlite
    path: {database}
  trajectory:
    enabled: true
    output: {trajectory}
    privacy: private
    failure_policy: required
budgets:
  max_steps: 6
  max_runtime_seconds: 300
  max_requests: 12
dataset:
  - task: fix clamp and test it
""",
        encoding="utf-8",
    )
    control = tmp_path / "control.json"

    created = _run("create", config, control)
    restored = _run("restore", config, control)

    assert created["lifecycle"] == "paused"
    assert created["tool_calls"] == {
        "grep_file": 1,
        "read_file": 1,
        "run_command": 1,
        "write_file": 1,
    }
    assert created["sandbox"]["cleanup"] == "passed"
    assert restored["lifecycle"] == "completed"
    assert restored["final_result"] == "all three tests pass"
    assert restored["requests_after_restore"] == 1
    assert restored["config_digest"] == created["config_digest"]
    assert restored["trajectory_records"] > 10
    assert {"model_request", "model_response", "tool_slot"} <= set(
        restored["trajectory_kinds"]
    )
    assert restored["qita_session"] is True
    assert restored["qita_timeline"] is True
    assert restored["sandbox"]["cleanup"] == "passed"
    assert "return max(low, min(value, high))" in (
        workspace / "calculator.py"
    ).read_text(encoding="utf-8")
    private_text = trajectory.read_text(encoding="utf-8")
    assert "offline-secret-never-persist" not in private_text
    assert str(tmp_path) not in private_text

    containers = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=qitos-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert containers.stdout.strip() == ""

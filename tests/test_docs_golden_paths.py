"""Execute only named offline teaching programs from a fresh installed wheel."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest

ROOT = Path(__file__).resolve().parents[1]


def command(args, cwd, timeout=180):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env,
                            capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, f"{args[0:3]}: {result.stdout}\n{result.stderr}"
    return result.stdout


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    root = tmp_path_factory.mktemp("docs-installed")
    # A reviewed wheel may be supplied by CI; otherwise build from the frozen source.
    supplied = os.environ.get("QITOS_DOCS_WHEEL")
    if supplied:
        wheel = Path(supplied).resolve()
    else:
        command([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
                 "--wheel-dir", root, ROOT], root)
        wheel = next(root.glob("qitos-*.whl"))
    import zipfile
    with zipfile.ZipFile(wheel) as archive:
        for path in (ROOT / "qitos").rglob("*.py"):
            assert archive.read(path.relative_to(ROOT).as_posix()) == path.read_bytes()
    venv.EnvBuilder(with_pip=True).create(root / "venv")
    python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    command([python, "-m", "pip", "install", wheel, "pytest"], root)
    lessons = root / "lessons"
    shutil.copytree(ROOT / "examples/tutorials", lessons, ignore=shutil.ignore_patterns("__pycache__"))
    command([python, "-c", "import qitos; assert 'site-packages' in qitos.__file__"], root)
    return root, python, lessons


def test_complete_examples_are_not_placeholders():
    contracts = json.loads((ROOT / "docs/tutorial-contracts.json").read_text())
    for unit in contracts["units"]:
        path = ROOT / unit["example"]
        tree = ast.parse(path.read_text())
        assert not any(isinstance(node, ast.Constant) and node.value is Ellipsis for node in ast.walk(tree)), path
        for prefix in ("", "zh/"):
            page = ROOT / "docs" / f"{prefix}{unit['page']}.mdx"
            assert unit["example"] in page.read_text(), page


def test_installed_scaffold_and_configuration(installed):
    root, python, _ = installed
    bin_dir = python.parent
    for cli in ("qit", "qita"):
        command([bin_dir / cli, "--help"], root)
    command([bin_dir / "qit", "new", "--agent-name", "my_agent", "--output-dir", root, "--no-input"], root)
    command([python, "-m", "pip", "install", root / "my_agent"], root)
    command([python, "-m", "pytest", "-q", root / "my_agent/tests"], root)
    config = root / "agent.yaml"
    shutil.copy(ROOT / "examples/config/agent.yaml", config)
    command([python, "-c", "from qitos.config import load_agent_config; "
             "c=load_agent_config('agent.yaml'); assert c.budgets.max_requests == 12; print(c.digest())"], root)


def test_installed_session_and_readers(installed):
    root, python, lessons = installed
    run = root / "session-run"
    command([python, lessons / "session_walkthrough.py", "create", "--root", run], root)
    identity = json.loads((run / "control.json").read_text())["session_id"]
    inspected = command([python.parent / "qit", "session", "inspect", "--config", run / "agent.json",
                         "--session-id", identity], root)
    assert identity in inspected
    command([python, lessons / "session_walkthrough.py", "restore", "--root", run], root)
    command([python.parent / "qita", "inspect", "session", identity, "--logdir", run], root)
    run_id = json.loads((run / "control.json").read_text())["run_id"]
    # G5 CLI requires an existing run selector directory; the journal stays authoritative.
    (run / run_id).mkdir()
    command([python.parent / "qita", "export", "--run", run / run_id,
             "--html", root / "trajectory.html"], root)
    assert (root / "trajectory.html").stat().st_size > 100


@pytest.mark.parametrize("file,output", [
    ("custom_agent.py", "completed=2"),
    ("context_memory.py", "compaction loss recorded"),
    ("work_graph.py", "join=closed"),
])
def test_installed_extensions(installed, file, output):
    root, python, lessons = installed
    args = [python, lessons / file]
    if file != "custom_agent.py":
        args += ["--root", root / file.removesuffix(".py")]
    assert output in command(args, root)

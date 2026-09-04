"""Execute complete files copied from the public page, never hidden helpers."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import socket
import time
from urllib.request import urlopen
from urllib.error import URLError

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNC = load_script("sync_tutorial_docs")
API = load_script("sync_api_reference")
CONTRACT = SYNC.contracts()
CASES = [(prefix, unit) for unit in CONTRACT["units"] for prefix in ("", "zh/")
         if unit["runtime"] == "offline"]


def test_tutorial_source_and_api_contracts():
    assert SYNC.synchronize(check=True) == []
    assert API.synchronize(check=True) == []
    symbols = {(s["module"], s["name"]) for group in json.loads((ROOT / "docs/api-contracts.json").read_text())["groups"]
               for s in group["symbols"]}
    for unit in CONTRACT["units"]:
        en = SYNC.complete_files(ROOT / "docs" / f"{unit['page']}.mdx")
        zh = SYNC.complete_files(ROOT / "docs/zh" / f"{unit['page']}.mdx")
        assert en == zh, unit["page"]
        assert set(en) == {item["target"] for item in unit["files"]}
        for name, code in en.items():
            if name.endswith(".py"):
                tree = ast.parse(code, filename=f"{unit['page']}:{name}")
                assert not any(isinstance(n, ast.Constant) and n.value is Ellipsis for n in ast.walk(tree))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("qitos"):
                        for alias in node.names:
                            assert (node.module, alias.name) in symbols, (unit["page"], node.module, alias.name)


# Reuse the existing wheel fixture; executing this file with the golden suite
# shares the same installation rather than introducing an editable shortcut.
from test_docs_golden_paths import installed as _installed, command  # noqa: E402

installed = _installed


def materialize(page, directory):
    for name, code in SYNC.complete_files(page).items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")


def execute_unit(unit, directory, python):
    output = []
    for args in unit["commands"]:
        executable = python if args[0] == "python" else python.parent / args[0]
        output.append(command([executable, *args[1:]], directory, timeout=90))
    text = "\n".join(output)
    for expected in unit["expected"]:
        assert expected in text, f"{unit['page']}: missing {expected!r}: {text}"
    return text


@pytest.mark.parametrize("prefix,unit", CASES, ids=[p + u["page"] for p, u in CASES])
def test_page_files_execute_from_installed_wheel(installed, tmp_path, prefix, unit):
    _, python, _ = installed
    directory = tmp_path
    if unit["scaffold"]:
        command([python.parent / "qit", "new", "--agent-name", "notes_agent", "--output-dir", tmp_path, "--no-input"], tmp_path)
        directory = tmp_path / "notes_agent"
    materialize(ROOT / "docs" / f"{prefix}{unit['page']}.mdx", directory)
    if unit["scaffold"]:
        command([python, "-m", "pip", "install", directory], directory)
        command([python, "-m", "pytest", "-q", "tests"], directory)
    try:
        execute_unit(unit, directory, python)
    except AssertionError as error:
        pytest.fail(f"page={prefix}{unit['page']}; complete-files execution: {error}")
    if unit["page"] == "guides/observability":
        control = json.loads((directory / "notes-run/control.json").read_text())
        run = directory / "notes-run" / control["run_id"]
        command([python.parent / "qit", "session", "inspect", "--config", "notes-run/agent.json",
                 "--session-id", control["session_id"]], directory)
        command([python.parent / "qita", "inspect", "session", control["session_id"], "--logdir", "notes-run"], directory)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with (directory / "replay.log").open("w") as log:
            process = subprocess.Popen([str(python.parent / "qita"), "replay", "--run", str(run),
                                        "--port", str(port)], cwd=directory, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 20
                while True:
                    assert process.poll() is None, "replay server exited before HTTP verification"
                    try:
                        with urlopen(f"http://127.0.0.1:{port}", timeout=1) as response:
                            html = response.read().decode()
                            assert response.status == 200 and "qita" in html.lower()
                        break
                    except URLError:
                        if time.monotonic() >= deadline:
                            raise AssertionError("replay HTTP endpoint did not become ready")
                        time.sleep(0.1)
            finally:
                process.terminate()
                process.wait(timeout=10)
        command([python.parent / "qita", "export", "--run", run, "--html", "trajectory.html"], directory)
        assert (directory / "trajectory.html").stat().st_size > 100


def test_chapters_run_in_learning_order(installed, tmp_path):
    _, python, _ = installed
    directory = tmp_path / "notes_project"
    directory.mkdir()
    for unit in CONTRACT["units"]:
        if unit["runtime"] != "offline":
            continue
        materialize(ROOT / "docs" / f"{unit['page']}.mdx", directory)
        if unit["page"] == "guides/observability":
            unit = {**unit, "commands": unit["commands"][1:]}
        execute_unit(unit, directory, python)


@pytest.mark.skipif(os.environ.get("QITOS_DOCS_DOCKER") != "1", reason="explicit Docker qualification; not ordinary docs CI")
def test_page_docker_publication(installed, tmp_path):
    _, python, _ = installed
    unit = next(u for u in CONTRACT["units"] if u["runtime"] == "docker")
    for prefix in ("", "zh/"):
        directory = tmp_path / ("zh" if prefix else "en")
        directory.mkdir()
        materialize(ROOT / "docs" / f"{prefix}{unit['page']}.mdx", directory)
        execute_unit(unit, directory, python)
        assert (directory / "sandbox-private/source/report.txt").read_text() == "original\n"
        assert (directory / "sandbox-published/source/report.txt").read_text() == "Session, Artifact\n"

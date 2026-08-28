from __future__ import annotations

from types import SimpleNamespace

from qitos.kit.env.docker_env import DockerEnv, DockerFSCapability


def test_docker_fs_keeps_absolute_paths_and_resolves_relative_paths() -> None:
    fs = DockerFSCapability(container="demo", workdir="/workspace")

    assert fs._inner_path("/task/repo/app.py") == "/task/repo/app.py"
    assert fs._inner_path("src/app.py") == "/workspace/src/app.py"
    assert fs._inner_path("") == "/workspace"


def test_docker_env_passes_sorted_container_environment(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], timeout: int = 60):
        commands.append(list(cmd))
        if cmd[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="missing")
        return SimpleNamespace(returncode=0, stdout="container-id", stderr="")

    monkeypatch.setattr("qitos.kit.env.docker_env._run", fake_run)
    env = DockerEnv(
        image="python:3.12",
        auto_create=True,
        container_env={"Z_FLAG": "last", "A_FLAG": "first"},
    )

    env._ensure_container()

    run_cmd = next(cmd for cmd in commands if cmd[:3] == ["docker", "run", "-d"])
    first_index = run_cmd.index("A_FLAG=first")
    last_index = run_cmd.index("Z_FLAG=last")
    assert run_cmd[first_index - 1] == "-e"
    assert run_cmd[last_index - 1] == "-e"
    assert first_index < last_index

"""Required G5 Docker tests. No skip substitutes for platform qualification."""

import json
import subprocess
import time

from qitos.kit.env.docker_env import DockerEnv
from qitos.kit.env.sandbox import SandboxPolicy, SandboxResourceLimits


def test_g5_real_docker_process_group_and_cleanup(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "input.txt").write_bytes(b"input")
    env = DockerEnv(
        image="qitos-s3-g4-qualification:pytest-debian", host_workspace=str(source),
        auto_create=True, remove_on_close=True, strict_workspace=True,
        policy=SandboxPolicy(
            image="qitos-s3-g4-qualification:pytest-debian",
            limits=SandboxResourceLimits(cpu_count=.5, memory_bytes=256 * 1024 * 1024,
                                         pids=32, wall_seconds=120, command_seconds=10),
        ),
    )
    identity = None
    try:
        env.setup()
        inspection = subprocess.run(["docker", "inspect", env.container],
                                    capture_output=True, text=True, timeout=20, check=True)
        fact = json.loads(inspection.stdout)[0]
        identity = fact["Config"]["Labels"]["qitos.sandbox.id"]
        host = fact["HostConfig"]
        assert fact["Config"]["User"] == "65532:65532"
        assert host["ReadonlyRootfs"] is True
        assert host["NetworkMode"] == "none"
        assert "ALL" in host["CapDrop"]
        assert "no-new-privileges:true" in host["SecurityOpt"]
        assert not fact["Mounts"]
        assert host["PidsLimit"] == 32
        assert host["Memory"] == 256 * 1024 * 1024
        assert env.cmd.run("cat input.txt", timeout=5)["stdout"].strip() == "input"
        handle = env.processes.start("sleep 60 & echo $! > /workspace/child.pid; exit 0")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = env.cmd.run("test -s child.pid", timeout=5)
            if result["returncode"] == 0:
                break
            time.sleep(.05)
        result = env.processes.terminate(handle, timeout=1)
        assert result["status"] == "terminal"
        assert result["worker_still_running"] is False
        assert result["completion_source"] == "backend_supervisor"
        assert env.processes.terminate(handle, timeout=1)["status"] == "terminal"
        env.cmd.run("printf untrusted > input.txt", timeout=5)
    finally:
        env.close()
    assert (source / "input.txt").read_bytes() == b"input"
    assert not (source / "child.pid").exists()
    assert env.cleanup_receipt["container_absent"] is True
    assert identity is not None
    absence = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=qitos.sandbox.id={identity}"],
                             capture_output=True, text=True, timeout=20, check=True)
    assert absence.stdout.strip() == ""


def test_g5_real_docker_publication_uses_permission_effect_and_artifact(tmp_path):
    from dataclasses import replace
    from qitos.config import EnvironmentConfig, SessionConfig, build_agent_composition
    from qitos.core.action import Action
    from qitos.kit.tool.internal.publication import SandboxPublicationTool
    from test_s4_lane_a_public_authoring import _config, _FinalModel

    source = tmp_path / "source"
    source.mkdir()
    target = source / "code.py"
    target.write_bytes(b"before")
    config = _config(source)
    config = replace(config, tool_preset="env_coding", runtime=replace(
        config.runtime, data_root=str(tmp_path / "runtime"), session=SessionConfig(),
        environment=EnvironmentConfig(workspace=str(source), image="qitos-s3-g4-qualification:pytest-debian",
                                      cpus=.5, memory_mb=256, pids_limit=32),
    ))
    with build_agent_composition(config, model_override=_FinalModel()) as composition:
        publication = SandboxPublicationTool(composition.env, paths=["code.py"],
                                             expected_input_digest=composition.env.input_digest)
        composition.tool_registry.register(publication)
        result = composition.engine.executor.execute_one(Action("write_file", {"path": "code.py", "content": "after"}),
                                                         env=composition.env)
        assert result.status == "success"
        assert target.read_bytes() == b"before"
        result = composition.engine.executor.execute_one(Action("publish_workspace", {}), env=composition.env)
        assert result.status == "success", result.to_dict()
        assert result.effect_state == "committed"
        assert target.read_bytes() == b"after"
        resolver = composition.agent.config["artifact_resolver"]
        assert resolver.resolve(result.artifact_refs[0]).body == b"after"
        composition.engine.executor.execute_one(Action("write_file", {"path": "code.py", "content": "later"}),
                                                env=composition.env)
    assert target.read_bytes() == b"after"
    assert composition.sandbox_receipt["cleanup_receipt"]["container_absent"] is True


def test_g5_real_docker_command_parent_exit_waits_for_children(tmp_path):
    env = DockerEnv(image="qitos-s3-g4-qualification:pytest-debian", host_workspace=str(tmp_path),
                    auto_create=True, remove_on_close=True, strict_workspace=True,
                    policy=SandboxPolicy(image="qitos-s3-g4-qualification:pytest-debian",
                                         limits=SandboxResourceLimits(cpu_count=.5, memory_bytes=256 * 1024 * 1024, pids=32)))
    try:
        env.setup()
        result = env.cmd.run("sleep 60 & exit 0", timeout=1)
        assert result["timed_out"] is True
        assert result["worker_still_running"] is False
        assert result["completion_source"] == "backend_supervisor"
        result = env.cmd.run("python3 -c 'print(\"x\" * 100000)'", timeout=5)
        assert result["status"] == "success"
        assert result["stdout_bytes"] == 100001
    finally:
        env.close()
    assert env.cleanup_receipt["container_absent"] is True


def test_g5_worker_cannot_forge_process_completion_in_mutable_files(tmp_path):
    import shlex
    env = DockerEnv(image="qitos-g5-qualification:20260904", host_workspace=str(tmp_path),
                    auto_create=True, remove_on_close=True, strict_workspace=True,
                    policy=SandboxPolicy(image="qitos-g5-qualification:20260904",
                        limits=SandboxResourceLimits(cpu_count=.5, memory_bytes=256 * 1024 * 1024, pids=32)))
    supervisor = None
    try:
        env.setup()
        handle = env.processes.start("sleep 60")
        path = "/tmp/qitos-processes/" + handle.process_id + ".state"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = env.cmd.run("cat " + shlex.quote(path), timeout=2)
            if state.get("returncode") == 0:
                supervisor = json.loads(state["stdout"])["supervisor_pid"]
                break
        assert supervisor is not None
        forged = json.dumps({"status": "terminal", "returncode": 0, "worker_still_running": False,
                             "outcome_unknown": False, "stdout": "", "stderr": "",
                             "completion_source": "backend_supervisor"})
        env.cmd.run("kill -STOP " + str(supervisor) + "; printf '%s' " + shlex.quote(forged)
                    + " > " + shlex.quote(path), timeout=2)
        observed = env.processes.poll(handle)
        assert observed["worker_still_running"] is True
        assert observed["status"] != "terminal"
    finally:
        if supervisor is not None:
            env.cmd.run("kill -CONT " + str(supervisor), timeout=2)
        env.close()
    assert env.cleanup_receipt["container_absent"] is True


def test_g5_unknown_backend_exit_keeps_ownership_and_cleanup_failure(tmp_path):
    import pytest
    from qitos.core.env import EnvCapabilityError
    (tmp_path / "input.py").write_text("original")
    env = DockerEnv(image="qitos-g5-qualification:20260904", host_workspace=str(tmp_path),
                    auto_create=True, remove_on_close=True, strict_workspace=True,
                    policy=SandboxPolicy(image="qitos-g5-qualification:20260904",
                        limits=SandboxResourceLimits(cpu_count=.5, memory_bytes=256 * 1024 * 1024, pids=32)))
    killed = False
    try:
        env.setup()
        env.fs.write_text("json.py", "raise RuntimeError('workspace import must not run')\n")
        assert env.cmd.run("printf isolated", timeout=2)["stdout"] == "isolated"
        env.fs.write_text("input.py", "unpublished")
        handle = env.processes.start("sleep 60")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = env.processes.poll(handle)
            if state.get("supervisor_pid"):
                break
            time.sleep(.05)
        assert state.get("supervisor_pid")
        assert env.cmd.run("kill -KILL " + str(state["supervisor_pid"]), timeout=2)["returncode"] == 0
        killed = True
        result = env.processes.terminate(handle, timeout=0)
        assert result["outcome_unknown"] and result["worker_still_running"]
        assert handle.process_id in env.processes._owned
    finally:
        if killed:
            with pytest.raises(EnvCapabilityError, match="process_cleanup_incomplete"):
                env.close()
        else:
            env.close()
    assert env.cleanup_receipt["container_absent"] is True
    assert env.cleanup_receipt["process_cleanup_confirmed"] is False
    assert (tmp_path / "input.py").read_text() == "original"
    with pytest.raises(EnvCapabilityError, match="process_cleanup_incomplete"):
        env.close()
    assert handle.process_id in env.processes._owned

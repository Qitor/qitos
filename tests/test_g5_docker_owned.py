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

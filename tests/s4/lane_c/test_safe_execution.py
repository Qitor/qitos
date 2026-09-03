from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from qitos.core.action import Action
from qitos.core.env import EnvCapabilityError, ProcessHandle
from qitos.core.tool import BaseTool, FunctionTool, ToolMeta, ToolSpec
from qitos.core.tool_registry import ToolRegistry
from qitos.core.tool_runtime import ToolEffectDeclaration, ToolResourceKind
from qitos.engine.action_executor import ActionExecutor
from qitos.engine.tool_runtime import (
    ReferenceEffectPolicy,
    assert_tool_effect_policy_conformance,
    run_tool_executor_conformance,
)
from qitos.kit.env.docker_env import DockerEnv
from qitos.kit.env.host_env import HostEnv
from qitos.kit.env.sandbox import (
    SANDBOX_SNAPSHOT_COMPONENT_CODEC,
    DockerSandboxBackend,
    SandboxAllocation,
    SandboxCapabilityMismatch,
    SandboxHandle,
    SandboxIdentity,
    SandboxLease,
    SandboxPolicy,
    SandboxResourceLimits,
)
from qitos.kit.toolset.env_coding import EnvCodingToolSet


def _tools() -> dict[str, BaseTool]:
    return {tool.name: tool for tool in EnvCodingToolSet().tools()}


def _context(env: HostEnv) -> dict[str, object]:
    return {
        "env": env,
        "ops": {
            "file": env.fs,
            "process": env.cmd,
            "process_control": env.processes,
        },
    }


def test_native_aci_is_small_env_only_and_permissions_are_split() -> None:
    tools = _tools()
    assert set(tools) == {
        "read_file", "list_files", "grep_file", "write_file", "edit_file",
        "run_command", "run_test", "start_process", "poll_process",
        "terminate_process",
    }
    source = inspect.getsource(__import__("qitos.kit.toolset.env_coding", fromlist=["*"]))
    assert "subprocess" not in source
    assert "pathlib" not in source
    assert tools["write_file"].spec.permissions.filesystem_write is True
    assert tools["write_file"].spec.permissions.command is False
    assert tools["run_command"].spec.permissions.command is True
    assert tools["run_command"].spec.permissions.filesystem_write is False


def test_read_edit_test_and_effect_receipt_use_canonical_executor(tmp_path: Path) -> None:
    (tmp_path / "test_value.py").write_text(
        "VALUE = 1\n\ndef test_value():\n    assert VALUE == 2\n",
        encoding="utf-8",
    )
    env = HostEnv(str(tmp_path))
    registry = ToolRegistry().include_toolset(EnvCodingToolSet())
    executor = ActionExecutor(registry)
    read = executor.execute_one(Action("read_file", {"path": "test_value.py"}), env=env)
    edit = executor.execute_one(
        Action(
            "edit_file",
            {
                "path": "test_value.py",
                "old_text": "VALUE = 1",
                "replacement": "VALUE = 2",
                "expected_sha256": read.output["snapshot"]["sha256"],
            },
        ),
        env=env,
    )
    tested = executor.execute_one(
        Action("run_test", {"target": "test_value.py", "timeout": 30}), env=env
    )
    assert read.status == edit.status == tested.status == "success"
    assert edit.effect_state == "committed"
    assert edit.idempotency_ref is not None
    assert edit.filesystem_changes[0]["before_sha256"] != edit.filesystem_changes[0]["after_sha256"]
    env.close()


def test_atomic_edit_rejects_stale_snapshot_without_mutation(tmp_path: Path) -> None:
    target = tmp_path / "value.txt"
    target.write_text("first", encoding="utf-8")
    env = HostEnv(str(tmp_path))
    before = env.fs.snapshot("value.txt")
    env.fs.atomic_write_text("value.txt", "second", expected_sha256=before.sha256)
    result = _tools()["edit_file"].execute(
        {
            "path": "value.txt",
            "old_text": "second",
            "replacement": "third",
            "expected_sha256": before.sha256,
        },
        _context(env),
    )
    assert result.status == "error"
    assert result.error_code == "stale_file"
    assert target.read_text(encoding="utf-8") == "second"
    env.close()


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd", ".git/config", ".ssh/id"])
def test_native_paths_fail_closed_without_echoing_sensitive_values(
    tmp_path: Path, path: str
) -> None:
    env = HostEnv(str(tmp_path))
    result = _tools()["read_file"].execute({"path": path}, _context(env))
    assert result.status == "error"
    assert result.error_code in {"path_outside_workspace", "protected_path"}
    assert "passwd" not in json.dumps(result.to_trace_safe_dict())
    env.close()


def test_symlink_escape_is_rejected_at_capability_boundary(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-qitos-fixture"
    outside.write_text("fixture", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(outside)
    env = HostEnv(str(tmp_path))
    with pytest.raises(PermissionError, match="symbolic-link"):
        env.fs.read_text("link")
    link.unlink()
    outside.unlink()
    env.close()


def test_large_output_retains_canonical_value_and_publishes_artifact(tmp_path: Path) -> None:
    body = "x" * 50_000
    (tmp_path / "large.txt").write_text(body, encoding="utf-8")
    env = HostEnv(str(tmp_path))
    result = _tools()["read_file"].execute({"path": "large.txt"}, _context(env))
    assert result.output["content"] == body
    assert result.truncated is True
    assert result.complete is True
    assert result.omitted["model_output_characters"] > 0
    assert result.artifact_refs[0].byte_length == len(body)
    env.close()


def test_owned_process_control_and_stale_generation(tmp_path: Path) -> None:
    env = HostEnv(str(tmp_path))
    handle = env.processes.start("printf process-ok")
    terminal = env.processes.terminate(handle)
    assert terminal["worker_still_running"] is False
    env.processes.close()
    with pytest.raises(EnvCapabilityError, match="stale_generation"):
        env.processes.poll(ProcessHandle(handle.process_id, handle.owner_generation))


def test_host_command_timeout_reaps_its_owned_process_group(tmp_path: Path) -> None:
    env = HostEnv(str(tmp_path))
    started = time.monotonic()
    result = env.cmd.run("python -c 'import time; time.sleep(20)'", timeout=1)
    assert time.monotonic() - started < 6
    assert result["timed_out"] is True
    assert result["worker_still_running"] is False
    assert result["outcome_unknown"] is False
    env.close()


def test_async_remote_timeout_preserves_unknown_effect() -> None:
    async def remote_call() -> str:
        await asyncio.sleep(0.1)
        return "late"

    tool = FunctionTool(
        remote_call,
        meta=ToolMeta(
            name="remote_call",
            timeout_s=0.01,
            lifecycle=ToolResourceKind.MCP_REQUEST,
            effect=ToolEffectDeclaration(effect_ref="remote:fixture"),
        ),
    )
    result = ActionExecutor(ToolRegistry().register(tool)).execute_one(
        Action("remote_call", {})
    )
    assert result.status == "timed_out"
    assert result.outcome_unknown is True
    assert result.reconciliation_required is True
    assert result.retry_disposition == "requires_reconciliation"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"privileged": True},
        {"host_pid": True},
        {"host_ipc": True},
        {"allow_devices": True},
        {"read_only_root": False},
        {"run_as_uid": 0},
        {"secrets": ("provider",)},
    ],
)
def test_unsafe_sandbox_policy_is_typed_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        SandboxPolicy(image="example@sha256:" + "a" * 64, **kwargs)


def test_docker_policy_args_are_typed_private_and_bounded(tmp_path: Path) -> None:
    limits = SandboxResourceLimits(
        cpu_count=1,
        memory_bytes=256 * 1024 * 1024,
        pids=32,
        file_descriptors=128,
        tmpfs_bytes=32 * 1024 * 1024,
        disk_bytes=64 * 1024 * 1024,
        output_bytes=64 * 1024,
        command_seconds=10,
        wall_seconds=60,
    )
    policy = SandboxPolicy.coding("example:locked", limits=limits)
    env = DockerEnv(
        image=policy.image,
        host_workspace=str(tmp_path),
        auto_create=True,
        remove_on_close=True,
        strict_workspace=True,
        policy=policy,
    )
    args = env._policy_run_args()
    rendered = " ".join(args)
    assert "--network none" in rendered
    assert "--read-only" in args
    assert "--cap-drop ALL" in rendered
    assert "no-new-privileges:true" in rendered
    assert "--pids-limit 32" in rendered
    assert "--memory 268435456" in rendered
    assert "--tmpfs /workspace:" in rendered
    assert "--tmpfs /results:" in rendered
    assert " -v " not in f" {rendered} "
    assert "/var/run/docker.sock" not in rendered


def test_docker_backend_rejects_unimplemented_egress_before_setup() -> None:
    policy = SandboxPolicy(
        image="example:locked",
        network_mode="allowlist",
        egress_rules=("example.invalid:443",),
    )
    env = SimpleNamespace(policy=policy)
    backend = DockerSandboxBackend(env, config_digest="a" * 64)
    with pytest.raises(SandboxCapabilityMismatch, match="allowlists"):
        backend.prepare()


def test_repeated_unallocated_cleanup_is_idempotent(tmp_path: Path) -> None:
    policy = SandboxPolicy.coding("example:locked")
    env = DockerEnv(
        image=policy.image,
        host_workspace=str(tmp_path),
        policy=policy,
    )
    env.close()
    env.close()
    assert env.cleanup_receipt["container_absent"] is True
    assert env.cleanup_receipt["staging_absent"] is True
    assert env.cleanup_receipt["repeated"] is True


def test_sandbox_handle_component_and_allocation_round_trip() -> None:
    identity = SandboxIdentity(
        "sandbox:test", "session:test", "run:test", "work:child",
        "attempt:test", 4,
    )
    handle = SandboxHandle(
        identity=identity,
        backend_type="external-backend",
        policy_digest="a" * 64,
        image_digest="b" * 64,
        capability_set=("filesystem.read", "process.bounded"),
        lease=SandboxLease("lease:test", 4),
    )
    component = handle.snapshot_component(
        workspace_digest="c" * 64,
        input_digest="d" * 64,
        quiescence="processes_terminal",
        cleanup_state="pending",
    )
    payload = SANDBOX_SNAPSHOT_COMPONENT_CODEC.encode(component)
    assert SANDBOX_SNAPSHOT_COMPONENT_CODEC.decode(payload) == component
    allocation = SandboxAllocation(
        "allocation:test", "delegate:test", "work:parent", "work:child", handle
    ).to_dict()
    assert allocation["sandbox"]["identity"]["work_item_id"] == "work:child"
    assert allocation["sandbox"]["lease"]["owner_generation"] == 4


class _Echo(BaseTool):
    def __init__(self) -> None:
        super().__init__(ToolSpec("echo", "echo", parameters={"value": {"type": "string"}}, required=["value"]))

    def execute(self, args, runtime_context=None):
        return args["value"]


class ExternalPackageExecutor:
    """Independent package-style adapter using only the public executor protocol."""

    def __init__(self) -> None:
        self.delegate = ActionExecutor(ToolRegistry().register(_Echo()))

    def execute_one(self, action, **kwargs):
        return self.delegate.execute_one(action, **kwargs)

    def execute_batch(self, actions, **kwargs):
        return self.delegate.execute_batch(actions, **kwargs)


def test_public_third_party_tool_runtime_and_policy_conformance() -> None:
    report = run_tool_executor_conformance(
        ExternalPackageExecutor(), [Action("echo", {"value": "ok"}, action_id="call:echo")]
    )
    policy = assert_tool_effect_policy_conformance(
        ReferenceEffectPolicy(), Action("echo", {"value": "ok"}), _Echo()
    )
    assert report["status"] == policy["status"] == "passed"


def test_delegation_adapters_contain_no_nested_executor_or_thread_pool() -> None:
    import qitos.kit.tool.delegate as delegate_module
    import qitos.kit.tool.fanout as fanout_module

    source = inspect.getsource(delegate_module) + inspect.getsource(fanout_module)
    assert "Engine(" not in source
    assert "ThreadPoolExecutor" not in source

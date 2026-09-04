"""Executed G5 boundary probes; all adversarial paths/processes are task-owned."""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import time

import pytest

from qitos.cli import main as qit_main
from qitos.config import SessionConfig, build_agent_composition
from qitos.core.conversation import ExchangeLog, UserItem
from qitos.core.multimodal import ContentBlock
from qitos.core.request_view import RequestView
from qitos.kit.env.docker_env import DockerEnv, DockerProcessControlCapability
from qitos.kit.env.host_env import HostEnv
from qitos.kit.env.sandbox import SandboxPolicy
from qitos.models.provider import ProviderFailure, execute_provider_request
from qitos.tracing.journal_store import JournalTrajectoryStore
from qitos.tracing.s4_readiness import (
    REQUIRED_LANE_REQUIREMENTS, S4_PRODUCER_AUTHORITY, qualify_s4_readiness,
)
from qitos.tracing.trajectory import RecordKind, TrajectoryQuery, TrajectoryRecord
from test_s4_lane_a_public_authoring import (
    _ActionModel, _FinalModel, _PauseAfterFirstStep, _config,
)


ROOT = Path(__file__).resolve().parents[1]


def test_g5_c1_cleanup_never_publishes_into_input(tmp_path, monkeypatch):
    import qitos.kit.env.docker_env as module

    source, outside = tmp_path / "input", tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    (source / "original.txt").write_bytes(b"original")
    (source / "link").symlink_to(outside, target_is_directory=True)
    staging = tmp_path / "owned-staging"
    staging.mkdir()
    env = DockerEnv(container="g5-fake-owned", host_workspace=str(source),
                    policy=SandboxPolicy(image="g5-fake-image"), remove_on_close=True)
    env._created_here = True
    env._private_staging_root = str(staging)

    def transport(args, timeout=60):
        if args[1] == "cp":
            exported = Path(args[-1])
            for path in ("link/escaped.txt", ".ssh/authorized_keys", "original.txt"):
                target = exported / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"untrusted")
        return subprocess.CompletedProcess(args, 1 if args[1] == "inspect" else 0, "", "")

    monkeypatch.setattr(module, "_run", transport)
    monkeypatch.setattr(env, "_owns_container", lambda: True)
    env.close()
    assert not (outside / "escaped.txt").exists()
    assert not (source / ".ssh").exists()
    assert (source / "original.txt").read_bytes() == b"original"


class _LocalOwnedTransport:
    def __init__(self, root):
        self.root = root

    def run(self, command, timeout=10):
        command = command.replace("/tmp/qitos-processes", str(self.root / "processes"))
        result = subprocess.run(["/bin/sh", "-c", command], capture_output=True,
                                text=True, timeout=timeout, cwd=self.root)
        return {"returncode": result.returncode, "stdout": result.stdout,
                "stderr": result.stderr}


def _alive(pid):
    result = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                            capture_output=True, text=True, check=False)
    return bool(result.stdout.strip()) and not result.stdout.strip().startswith("Z")


def test_g5_c2_parent_exit_is_not_descendant_completion(tmp_path):
    control = DockerProcessControlCapability(_LocalOwnedTransport(tmp_path))
    pid_path = tmp_path / "child.pid"
    handle = control.start(f"sleep 120 & echo $! > '{pid_path}'; exit 0")
    child = None
    try:
        deadline = time.monotonic() + 5
        while not pid_path.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        child = int(pid_path.read_text())
        result = control.terminate(handle, timeout=1)
        assert result["worker_still_running"] or not _alive(child)
        assert result["termination"] != "owned_process_reaped" or not _alive(child)
    finally:
        if child is not None and _alive(child):
            os.kill(child, signal.SIGKILL)
        control.close()


def _persisted_config(tmp_path):
    config = _config(tmp_path)
    return replace(config, runtime=replace(config.runtime, session=SessionConfig(
        store="sqlite", path=str(tmp_path / "sessions.sqlite3"))))


def test_g5_a1_cli_fork_preserves_source_head(tmp_path, monkeypatch, capsys):
    import qitos.config
    from qitos.checkpoint import SqliteCheckpointStore

    config = _persisted_config(tmp_path)
    with build_agent_composition(config, model_override=_ActionModel(),
                                 env_override=HostEnv(workspace_root=str(tmp_path))) as first:
        first.runtime.lifecycle_policy = _PauseAfterFirstStep()
        parent = first.session("pause before fork")
        parent.run()
        session_id = parent.session_id.value
        before = first.runtime.checkpoint_store.get_session_head(session_id)
    composed = build_agent_composition(config, model_override=_FinalModel(),
                                      env_override=HostEnv(workspace_root=str(tmp_path)))
    monkeypatch.setattr(qitos.config, "load_agent_config", lambda _: config)
    monkeypatch.setattr(qitos.config, "build_agent_composition", lambda *a, **k: composed)
    assert qit_main(["session", "fork", "--config", "logical.yaml",
                     "--session-id", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["session_id"] != session_id
    store = SqliteCheckpointStore(config.runtime.session.path)
    try:
        assert store.get_session_head(session_id) == before
    finally:
        store.close()


def test_g5_a2_default_durable_store_is_cross_process():
    assert SessionConfig().store == "sqlite"


def test_g5_a2_inspect_needs_no_runtime_or_provider(tmp_path, monkeypatch, capsys):
    import qitos.config

    config = _persisted_config(tmp_path)
    with build_agent_composition(config, model_override=_FinalModel(),
                                 env_override=HostEnv(workspace_root=str(tmp_path))) as first:
        parent = first.session("finish")
        parent.run()
        session_id = parent.session_id.value
    changed = replace(config, name="different-input-config")
    monkeypatch.setattr(qitos.config, "load_agent_config", lambda _: changed)

    def forbidden(*a, **k):
        pytest.fail("read-only inspection constructed runtime/provider resources")

    monkeypatch.setattr(qitos.config, "build_agent_composition", forbidden)
    assert qit_main(["session", "inspect", "--config", "logical.yaml",
                     "--session-id", session_id]) == 0
    assert json.loads(capsys.readouterr().out)["config_digest"] == config.digest()


def _provider_request():
    module = runpy.run_path(str(ROOT / "tests/fixtures/s4/lane_b/third_party_adapter.py"))
    adapter = module["ExampleSemanticAdapter"]()
    log = ExchangeLog(log_id="g5-log")
    log.append(UserItem(item_id="g5-user", exchange_id="g5-exchange",
                        content=[ContentBlock(type="text", text="test")]))
    request = RequestView.from_exchange_log(log, target=adapter.qitos_request_target())
    return adapter, request


def test_g5_b1_missing_capture_preserves_dispatch_fact():
    adapter, request = _provider_request()
    adapter.qitos_continuation_resolver = None
    calls = []
    original = adapter.qitos_transport
    adapter.qitos_transport = lambda payload: (calls.append(1), original(payload))[1]
    with pytest.raises(ProviderFailure) as raised:
        execute_provider_request(adapter, request)
    assert len(calls) == 1
    assert raised.value.error_code == "continuation_capture_unavailable"
    assert raised.value.provider_request_sent is True
    assert raised.value.stage == "decode"


@pytest.mark.parametrize("stage", ["admission", "cancel", "transport", "normalizer",
                                   "decode", "capture", "attachment", "assistant", "response"])
def test_g5_b1_failure_accounting_is_conserved(stage, monkeypatch):
    import qitos.models.provider as module

    adapter, request = _provider_request()
    calls = []
    original = adapter.qitos_transport
    adapter.qitos_transport = lambda payload: (calls.append(1), original(payload))[1]

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_PROVIDER_BODY")

    options = {}
    if stage == "admission":
        options["request_admission"] = fail
    elif stage == "cancel":
        options["cancellation_check"] = lambda: True
    elif stage in {"transport", "normalizer"}:
        adapter.qitos_transport = lambda payload: (calls.append(1), fail())[1]
        if stage == "normalizer":
            adapter.qitos_normalize_failure = fail
    elif stage == "decode":
        codec = adapter.qitos_provider_codec()
        codec.decode = fail
        adapter.qitos_provider_codec = lambda: codec
    elif stage == "capture":
        adapter.qitos_continuation_resolver.capture = fail
    elif stage == "attachment":
        monkeypatch.setattr(module, "OpaqueContinuationAttachment", fail)
    elif stage == "assistant":
        monkeypatch.setattr(module.AssistantItem, "validate", fail)
    elif stage == "response":
        monkeypatch.setattr(module, "model_response_from_assistant", fail)
    with pytest.raises(ProviderFailure) as raised:
        execute_provider_request(adapter, request, **options)
    assert len(calls) == int(stage not in {"admission", "cancel"})
    assert raised.value.provider_request_sent == bool(calls)
    assert "PRIVATE_PROVIDER_BODY" not in json.dumps(raised.value.to_dict())
    assert json.loads(json.dumps(raised.value.to_dict()))["provider_request_sent"] == bool(calls)


def _record(index):
    return TrajectoryRecord.create(RecordKind.RUN, record_id=f"g5-{index}",
                                   run_id="g5-run", session_id="g5-session",
                                   payload={"index": index})


def test_g5_d1_short_write_must_not_acknowledge_partial_frame(tmp_path, monkeypatch):
    path = tmp_path / "journal"
    store = JournalTrajectoryStore(path)
    original = Path.open

    class ShortWriter:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def write(self, data):
            return self.handle.write(data[:max(1, len(data) // 2)])

        def fileno(self):
            return self.handle.fileno()

    def open_file(self, mode="r", *args, **kwargs):
        handle = original(self, mode, *args, **kwargs)
        return ShortWriter(handle) if self == path and mode == "ab" else handle

    monkeypatch.setattr(Path, "open", open_file)
    receipt = store.append(_record(0))
    assert receipt.persisted_count == 1
    assert len(store.read_run("g5-run").records) == 1


def test_g5_d2_whole_run_read_is_complete(tmp_path):
    store = JournalTrajectoryStore(tmp_path / "journal", max_query_records=2)
    store.append_batch(_record(i) for i in range(3))
    assert len(store.read_run("g5-run").records) == 3
    assert len(store.read_session("g5-session").records) == 3


def test_g5_d3_readme_and_fake_test_cannot_authorize_readiness():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    digest = hashlib.sha256(subprocess.check_output(
        ["git", "show", f"{commit}:README.md"], cwd=ROOT)).hexdigest()
    inventory = {"schema_version": "qitos.s4.lane_d.readiness/1", "lanes": {
        lane: {"exact_commit": commit, "source_wave": "S4",
               "producer_authority": S4_PRODUCER_AUTHORITY,
               "requirements": [{"requirement_id": req, "committed_path": "README.md",
                                 "sha256": digest, "schema": "not-a-schema",
                                 "current_writer": "nonexistent.writer",
                                 "consumer_test_node": "tests/test_no_local_paths.py::test_does_not_exist",
                                 "producer_authority": S4_PRODUCER_AUTHORITY,
                                 "no_identity_conflict": True}
                                for req in required]}
        for lane, required in REQUIRED_LANE_REQUIREMENTS.items()}}
    result = qualify_s4_readiness(inventory, repository_root=ROOT)
    assert result.status == "waiting_on_a_b_c"
    assert result.qualified_lanes == ()

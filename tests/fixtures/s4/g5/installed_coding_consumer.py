"""Standalone coding consumer. Run only from a fresh installed-wheel environment."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import qitos
from qitos.config import (AgentConfig, BudgetConfig, DatasetItem, EnvironmentConfig,
                          ModelConfig, RuntimeConfig, SessionConfig, TrajectoryConfig,
                          build_agent_composition)
from qitos.core.artifact import ArtifactRef
from qitos.core.work_graph import WorkGraph
from qitos.engine.runtime import LifecyclePolicy
from qitos.engine.work_runtime import DurableWorkRuntime, LocalWorkScheduler
from qitos.kit.tool.internal.publication import SandboxPublicationTool
from qitos.qita import ReadOnlyInspection
from qitos.qita.reader import candidate_file_reader
from qitos.tracing.trajectory import PrivacyView


def handle_in(value):
    if isinstance(value, str):
        try:
            return handle_in(json.loads(value))
        except (ValueError, TypeError):
            return None
    if isinstance(value, dict):
        if {"process_id", "owner_generation"} <= set(value):
            return value
        for child in value.values():
            found = handle_in(child)
            if found:
                return found
    if isinstance(value, list):
        for child in value:
            found = handle_in(child)
            if found:
                return found
    return None


class FakeProvider:
    model = "offline-coding"
    qitos_protocol = "json_decision_multi_v1"
    context_window = 128000
    max_tokens = 1024

    def __init__(self, stage=0):
        self.stage = stage

    def call_raw(self, messages, **options):
        stage = self.stage
        self.stage += 1
        if "G5_CHILD_FACT" in json.dumps(messages):
            if stage == 0:
                actions = [("list_files", {"path": "."})]
            else:
                return {"choices": [{"message": {"content": "Final Answer: child completed"}}]}
        elif stage == 0:
            actions = [("read_file", {"path": "large.txt"}), ("grep_file", {"query": "RESULT", "path": "."}),
                       ("list_files", {"path": "."})]
        elif stage == 1:
            actions = [("write_file", {"path": "code.py", "content": "RESULT = 42\n"})]
        elif stage == 2:
            actions = [("edit_file", {"path": "code.py", "old_text": "42", "replacement": "43"})]
        elif stage == 3:
            actions = [("run_test", {"target": "test_code.py", "timeout": 15})]
        elif stage == 4:
            actions = [("start_process", {"command": "sleep 30"})]
        elif stage == 5:
            actions = [("poll_process", handle_in(messages))]
        elif stage == 6:
            actions = [("terminate_process", handle_in(messages))]
        elif stage == 7:
            actions = [("run_command", {"command": "python3 -c 'print(\"x\" * 20000)'", "timeout": 10})]
        elif stage == 8:
            actions = [("publish_workspace", {})]
        else:
            return {"choices": [{"message": {"content": "Final Answer: coding complete"}}]}
        return {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": f"coding-{stage}-{index}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(arguments)}}
            for index, (name, arguments) in enumerate(actions)
        ]}}]}


class PauseAfterWrite(LifecyclePolicy):
    policy_id = "consumer.coding.pause_after_write"

    def should_pause(self, context):
        return context.step_id == 1


def configuration(root):
    return AgentConfig(
        name="coding-consumer", model=ModelConfig(provider="openai-compatible", model="offline-coding"),
        protocol="json_decision_multi_v1", tool_preset="env_coding",
        tool_options={"native_tool_calls_required": True, "max_concurrency": 3},
        dataset=(DatasetItem(task="G5_CODING_MAIN: update and verify code"),),
        budgets=BudgetConfig(max_steps=16, max_requests=20, max_runtime_seconds=90),
        runtime=RuntimeConfig(data_root=str(root / "data"), session=SessionConfig(),
                              trajectory=TrajectoryConfig(enabled=True, output=str(root / "trajectory.journal")),
                              environment=EnvironmentConfig(workspace=str(root / "source"),
                                  image="qitos-s3-g4-qualification:pytest-debian", cpus=.5, memory_mb=256, pids_limit=32)),
    )


def composition(root, *, restoring=False):
    result = build_agent_composition(configuration(root), model_override=FakeProvider(2 if restoring else 0))
    result.runtime.lifecycle_policy = PauseAfterWrite()
    return result


def wait_work(session, operation):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        graph = WorkGraph.from_canonical_dict(session.inspect().work_graph)
        receipt = next(item for item in graph.operation_receipts if item.operation_id == operation.operation_id)
        if receipt.state in {"completed", "failed", "outcome_unknown"}:
            assert receipt.state == "completed", receipt
            return graph
        time.sleep(.05)
    raise AssertionError("child execution did not complete within its bound")


def create(root):
    with composition(root) as current:
        class Resolver:
            resolver_id = "consumer.coding.child"

            def resolve(self, descriptor):
                def run():
                    if descriptor.operation != "join":
                        for identity in descriptor.child_session_ids:
                            result = subprocess.run([sys.executable, __file__, "work-child", str(root), identity],
                                                    capture_output=True, text=True, timeout=60)
                            assert result.returncode == 0, result.stdout + result.stderr
                    return {"children": list(descriptor.child_session_ids)}
                return run
        current.runtime.work_runtime = DurableWorkRuntime(LocalWorkScheduler(Resolver(), max_workers=1))
        session = current.session()
        result = session.run()
        assert session.lifecycle.value == "paused"
        assert (root / "source" / "code.py").read_text() == "RESULT = 0\n"
        head = session.current_head
        fork = current.fork(session.session_id)
        assert session.current_head == head
        work = session.submit_work("spawn", {"agent": "coding-consumer", "task": "G5_CHILD_FACT",
                                             "budget": {"model_requests": 2}}, operation_id="spawn:coding")
        wait_work(session, work)
        joined = session.join([work.operation_id], operation_id="join:coding")
        graph = wait_work(session, joined)
        assert graph.joins[0].state == "closed" and len(graph.completions) == 1
        (root / "control.json").write_text(json.dumps({
            "session_id": session.session_id.value, "run_id": result.run_id,
            "fork_id": fork.session_id.value, "child_ids": work.descriptor["child_session_ids"],
            "work_item_id": session.work_item_id.value, "attempt_id": session.attempt_id.value,
            "owner_generation": session.current_head.generation.value,
            "join_closed": True, "source_fork_unchanged": True,
        }))


def work_child(root, identity):
    with build_agent_composition(configuration(root), model_override=FakeProvider()) as current:
        child = current.restore(identity)
        result = child.run()
        assert result.state.final_result == "child completed", result.state.final_result


def resume(root, evidence=None):
    control = json.loads((root / "control.json").read_text())
    with composition(root, restoring=True) as current:
        session = current.restore(control["session_id"])
        assert current.env.fs.read_text("code.py") == "RESULT = 42\n"
        current.tool_registry.register(SandboxPublicationTool(current.env, paths=["code.py"],
                                                              expected_input_digest=current.env.input_digest))
        result = session.run(steering="Keep all unrelated input files unchanged.")
        assert result.state.final_result == "coding complete"
        assert (root / "source" / "code.py").read_text() == "RESULT = 43\n"
        reader = candidate_file_reader(current.trajectory_path)
        trajectory = reader.read_session(session.session_id.value, view=PrivacyView.RAW_PRIVATE)
        artifacts, tool_outcomes = [], {}
        for record in trajectory.records:
            def collect(value):
                if isinstance(value, dict):
                    if value.get("schema_version") == "qitos.tool_result/v2" and value.get("tool_name"):
                        tool_outcomes.setdefault(value["tool_name"], set()).add(value["status"])
                    if value.get("schema_version") == "qitos.artifact_ref/v1":
                        artifacts.append(ArtifactRef.from_dict(value))
                    else:
                        for item in value.values():
                            collect(item)
                elif isinstance(value, (list, tuple)):
                    for item in value:
                        collect(item)
            collect(record.payload)
        assert artifacts
        required = {"read_file", "grep_file", "list_files", "write_file", "edit_file", "run_test",
                    "run_command", "start_process", "poll_process", "terminate_process", "publish_workspace"}
        assert required <= set(tool_outcomes), tool_outcomes
        for name in required:
            assert tool_outcomes[name] <= ({"success", "timed_out"} if name == "poll_process" else {"success"}), (name, tool_outcomes[name])
        control["tool_outcomes"] = {name: sorted(values) for name, values in tool_outcomes.items()}
        for artifact in artifacts:
            body = current.agent.config["artifact_resolver"].resolve(artifact).body
            assert hashlib.sha256(body).hexdigest() == artifact.sha256
        assert ReadOnlyInspection(reader).session(session.session_id.value).records
        assert any(record.kind.value == "steering" for record in trajectory.records)
        if evidence is not None:
            from qitos.tracing.exporter import CanonicalTrajectoryExporter
            exporter = CanonicalTrajectoryExporter()
            exported = exporter.export(trajectory, view=PrivacyView.REDACTED_PUBLIC)
            reimported = exporter.reimport(exported)
            assert len(reimported.records) == len(trajectory.records)
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / "coding-trajectory.json").write_bytes(exported.data)
            control["public_export_sha256"] = exported.digest
            control["public_export_lossless"] = exported.loss.is_lossless
        control.update(run_id=result.run_id, attempt_id=session.attempt_id.value,
                       owner_generation=session.current_head.generation.value,
                       artifact_count=len(artifacts), trajectory_records=len(trajectory.records),
                       tool_calls=result.tool_calls_by_name, cleanup=current.env.cleanup_receipt)
    assert control["cleanup"]["container_absent"]
    control["installed_distribution"] = "site-packages" in qitos.__file__
    assert control["installed_distribution"]
    print("G5_CONSUMER_RESULT=" + json.dumps(control, sort_keys=True))


def main():
    if len(sys.argv) > 1 and sys.argv[1] != "--evidence-dir":
        phase, root = sys.argv[1], Path(sys.argv[2])
        if phase == "create":
            create(root)
        elif phase == "restore":
            resume(root, Path(sys.argv[3]) if len(sys.argv) > 3 else None)
        else:
            work_child(root, sys.argv[3])
        return
    evidence_args = [str(Path(sys.argv[2]).resolve())] if len(sys.argv) > 2 else []
    with tempfile.TemporaryDirectory(prefix="g5-installed-coding-") as directory:
        root = Path(directory)
        (root / "source").mkdir()
        (root / "source" / "code.py").write_text("RESULT = 0\n")
        (root / "source" / "large.txt").write_text("artifact-body\n" * 3000)
        (root / "source" / "test_code.py").write_text("from code import RESULT\ndef test_result(): assert RESULT == 43\n")
        for phase in ("create", "restore"):
            completed = subprocess.run([sys.executable, __file__, phase, str(root), *evidence_args], capture_output=True,
                                       text=True, timeout=120)
            assert completed.returncode == 0, completed.stdout + completed.stderr
            if phase == "restore":
                print(completed.stdout)


if __name__ == "__main__":
    main()

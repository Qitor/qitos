"""Standalone offline survey consumer using an installed QitOS wheel."""
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time

from importlib.util import find_spec
from qitos.config import (AgentConfig, BudgetConfig, DatasetItem, EnvironmentConfig,
                          ModelConfig, RuntimeConfig, SessionConfig, TrajectoryConfig,
                          build_agent_composition)
from qitos.core.artifact import ArtifactRef
from qitos.core.context import DeclaredContextBudgetPolicy, PriorityContextSelectionPolicy, StaticContextContributor
from qitos.core.function_tool_decorator import function_tool
from qitos.core.tool_result import ToolResult
from qitos.core.work_graph import WorkGraph
from qitos.engine.runtime import LifecyclePolicy
from qitos.engine.work_runtime import DurableWorkRuntime, LocalWorkScheduler, WorkRuntimeError
from qitos.core.session import ContinuationIdentity, SessionContractError
from qitos.core.request_view import CompactionReceipt, ContinuationRef, RequestTarget
from qitos.models.codec import report_for_request, validate_codec_result
from qitos.models.provider import (ContinuationResolution, decode_openai_like_response,
    legacy_capabilities, normalize_provider_failure, request_view_to_compat_messages)
from qitos.qita import ReadOnlyInspection
from qitos.qita.reader import candidate_file_reader
from qitos.tracing.trajectory import PrivacyView

FINISHED = threading.Event()
SELECTIONS = []
COMPACTIONS = []
CONTINUATION_RESOLUTIONS = []
CANONICAL_NOTES = "retained survey evidence " * 800


class Continuations:
    """Consumer-owned durable opaque-state resolver; no framework private API."""
    resolver_key = "consumer.research.continuations"

    def __init__(self, root):
        self.root = root / "data" / "continuations"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def capture(self, *, target, payload, attachment_id, expires_at=None):
        resolution = ContinuationResolution("resolved", payload=payload)
        identity = ContinuationIdentity.generate()
        path = self.root / identity.value
        with path.open("x", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        return ContinuationRef(reference_id=identity, resolver_key=self.resolver_key,
            provider=target.provider, model=target.model, api_mode=target.api_mode,
            attachment_id=attachment_id, payload_digest=resolution.payload_digest)

    def resolve(self, reference):
        if reference.resolver_key != self.resolver_key:
            return ContinuationResolution("missing", reason_code="wrong_resolver")
        path = self.root / reference.reference_id.value
        if not path.is_file():
            return ContinuationResolution("missing", reason_code="missing_state")
        resolution = ContinuationResolution("resolved", payload=json.loads(path.read_text()),
                                            payload_digest=reference.payload_digest)
        CONTINUATION_RESOLUTIONS.append(reference.reference_id.value)
        return resolution


class Compactor:
    policy_id = "consumer.research.omit_closed"

    def compact(self, **values):
        COMPACTIONS.append(values)
        return CompactionReceipt(receipt_id="compaction_" + values["selected_digest"][:24],
            input_exchange_ids=tuple(values["exchange_ids"]), policy_id=self.policy_id,
            output_digest=hashlib.sha256(b"").hexdigest(),
            declared_losses=("closed_exchange_omitted_without_summary",))


class Codec:
    codec_id = "consumer.research.semantic"
    codec_version = "1"

    def encode(self, request, *, capabilities=None, transport=None, allow_loss=False):
        assert transport == request.target
        messages, losses = request_view_to_compat_messages(request)
        report = report_for_request(request, capabilities, codec_id=self.codec_id,
            codec_version=self.codec_version, supported=request.capability_requirements,
            reasoning="dropped" if losses else "not_present", lossy_fields=losses,
            continuation="resolver_required" if request.continuation else "not_requested")
        return validate_codec_result({"messages": messages}, report, allow_loss=allow_loss)

    def apply_continuation(self, payload, resolution, *, request, report):
        return {**payload, "continuation": resolution.payload}, replace(report, continuation="applied")

    def decode(self, response, *, request):
        decoded = decode_openai_like_response(response, request=request)
        return replace(decoded, continuation_payload={"turn": response["next_turn"],
            "private_marker": "OPAQUE_RESEARCH_STATE"},
            continuation_attachment_id="attachment_" + request.request_id)


@function_tool(read_only=True, concurrency_safe=True)
def survey_statistics(runtime_context=None):
    values = list(range(3000))
    body = json.dumps(values).encode()
    resolver = runtime_context["artifact_resolver"]
    digest = hashlib.sha256(body).hexdigest()
    reference = ArtifactRef(artifact_id=f"sha256:{digest}", resolver_key=resolver.resolver_key,
                            sha256=digest, media_type="application/json", byte_length=len(body))
    resolver.put(reference, body)
    summary = {"count": len(values), "mean": statistics.mean(values)}
    return ToolResult(output={"sample": values, **summary}, model_output=summary,
                      artifact_refs=(reference,))


@function_tool(read_only=True, concurrency_safe=True)
def validate_sample():
    return {"method": "deterministic census", "valid": True, "notes": CANONICAL_NOTES}


@function_tool(timeout_s=.02, read_only=True, concurrency_safe=True)
def slow_reference():
    time.sleep(.15)
    FINISHED.set()
    return {"reference": "late but completed"}


class PauseAfterBatch(LifecyclePolicy):
    policy_id = "consumer.research.pause_first"

    def should_pause(self, context):
        return context.step_id == 0


class Selector(PriorityContextSelectionPolicy):
    def select(self, contributions, **options):
        values = tuple(contributions)
        SELECTIONS.extend(item.contribution_id for item in values)
        return super().select(values, **options)


class Provider:
    model = "offline-research"
    qitos_protocol = "json_decision_multi_v1"
    context_window = 128000
    max_tokens = 512

    def qitos_request_target(self):
        return RequestTarget("research-fixture", self.model, "semantic", "messages")

    def qitos_provider_capabilities(self):
        base = legacy_capabilities(self.qitos_request_target())
        return replace(base, supports_continuation=True,
            supported_features=base.supported_features + ("continuation", "steering"))

    def qitos_provider_codec(self):
        return Codec()

    def qitos_normalize_failure(self, error, *, report=None):
        return normalize_provider_failure(error, target=self.qitos_request_target(), report=report)

    def qitos_stream_transport(self, payload, *, on_delta=None):
        raise NotImplementedError("streaming is not declared")

    def qitos_transport(self, payload):
        messages = payload["messages"]
        rendered = json.dumps(messages)
        assert "RESEARCH_PROTOCOL" in rendered and "RECALL_FACT" in rendered
        assert len(rendered) < 20000
        turn = payload.get("continuation", {}).get("turn", 0)
        if turn == 0:
            names = ["survey_statistics", "validate_sample"]
        elif turn == 1:
            names = ["slow_reference"]
        else:
            assert FINISHED.wait(1), "the owned thread did not finish; no hard cancellation is claimed"
            return {"next_turn": 3, "choices": [{"message": {"content": "Final Answer: survey verified"}}]}
        return {"next_turn": turn + 1, "choices": [{"message": {"content": None,
            "reasoning_content": "PRIVATE_RESEARCH_REASONING", "tool_calls": [
            {"id": f"research-{name}", "type": "function", "function": {"name": name, "arguments": "{}"}}
            for name in names]}}]}


def configuration(root):
    return AgentConfig(name="survey-research", model=ModelConfig(provider="openai-compatible", model="offline-research"),
        protocol="json_decision_multi_v1", tool_preset="none", tool_options={"native_tool_calls_required": True, "max_concurrency": 2},
        context={"contributors": ["protocol"], "selector": "selector", "budget_policy": "budget",
                 "continuation_resolver": "continuation", "allow_codec_loss": True},
        compaction={"provider": "compactor"}, memory={"sources": ["recall"]},
        lifecycle={"policy": "pause"}, dataset=(DatasetItem(task="Summarize a deterministic survey"),),
        budgets=BudgetConfig(max_steps=6, max_requests=6, max_runtime_seconds=30),
        runtime=RuntimeConfig(data_root=str(root / "data"), session=SessionConfig(),
            trajectory=TrajectoryConfig(enabled=True, output=str(root / "trajectory.journal")),
            environment=EnvironmentConfig(workspace=str(root / "source"), image="qitos-g5-qualification:20260904",
                                          cpus=.5, memory_mb=256, pids_limit=32)))


def composition(root):
    current = build_agent_composition(configuration(root), model_override=Provider(), extensions={
        "protocol": lambda: StaticContextContributor("research.protocol", "project", "RESEARCH_PROTOCOL"),
        "recall": lambda: StaticContextContributor("research.recall", "memory", "RECALL_FACT"),
        "selector": Selector, "pause": PauseAfterBatch, "compactor": Compactor,
        "budget": lambda: DeclaredContextBudgetPolicy(default_max_input_units=8192, protected_recent_exchanges=0),
        "continuation": lambda: Continuations(root)})
    for tool in (survey_statistics, validate_sample, slow_reference):
        current.tool_registry.register(tool)
    return current


def create(root):
    with composition(root) as current:
        class Resolver:
            resolver_id = "consumer.research.handoff"

            def resolve(self, descriptor):
                # This scheduler records dispatch. The target executes in the
                # next fresh process through the same persisted Session head.
                assert descriptor.operation == "handoff"
                return lambda: {"target": descriptor.operation}
        current.runtime.work_runtime = DurableWorkRuntime(LocalWorkScheduler(Resolver(), max_workers=1))
        session = current.session()
        session.run()
        assert session.lifecycle.value == "paused"
        before = session.current_head
        source_snapshot = current.runtime.checkpoint_store.get_session_snapshot(before.snapshot_id.value)
        assert CANONICAL_NOTES in json.dumps(source_snapshot.payload)
        operation = session.handoff("survey-research", operation_id="handoff:research")
        assert operation.descriptor["transfer_receipts"]
        graph = WorkGraph.from_canonical_dict(session.inspect().work_graph)
        assert len(graph.transfers) == 1
        try:
            session.run()
        except (SessionContractError, WorkRuntimeError) as error:
            code = getattr(error, "error_code", getattr(error, "code", None))
            assert getattr(code, "value", code) == "superseded_owner"
        else:
            raise AssertionError("source owner was allowed to execute after handoff")
        (root / "control.json").write_text(json.dumps({"session_id": session.session_id.value,
            "old_run_id": before.owner_run_id.value, "source_fenced": True,
            "source_snapshot_id": before.snapshot_id.value,
            "transfer_count": len(graph.transfers), "work_item_id": session.work_item_id.value}))


def restore(root, evidence=None):
    control = json.loads((root / "control.json").read_text())
    with composition(root) as current:
        session = current.restore(control["session_id"])
        result = session.run(steering="Report the sample size and uncertainty explicitly.")
        assert result.state.final_result == "survey verified", result.state.final_result
        assert {"research.protocol", "research.recall"} <= set(SELECTIONS)
        reader = candidate_file_reader(current.trajectory_path)
        raw = reader.read_session(session.session_id.value, view=PrivacyView.RAW_PRIVATE)
        artifacts, timeout_facts = [], []
        def collect(value):
            if isinstance(value, dict):
                if value.get("schema_version") == "qitos.artifact_ref/v1":
                    artifacts.append(ArtifactRef.from_dict(value))
                if value.get("status") == "timed_out" and value.get("worker_still_running"):
                    timeout_facts.append(value)
                for item in value.values():
                    collect(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    collect(item)
        for record in raw.records:
            collect(record.payload)
        assert artifacts and timeout_facts and FINISHED.is_set()
        for artifact in artifacts:
            assert current.agent.config["artifact_resolver"].resolve(artifact).body
        assert len(ReadOnlyInspection(reader).session(session.session_id.value).records) == len(raw.records)
        assert any(record.kind.value == "steering" for record in raw.records)
        assert COMPACTIONS and CONTINUATION_RESOLUTIONS
        assert any(record.kind.value == "compaction" and not record.loss.is_lossless for record in raw.records)
        assert any(record.kind.value == "continuation" for record in raw.records)
        snapshot = current.runtime.checkpoint_store.get_session_snapshot(session.current_head.snapshot_id.value)
        source_snapshot = current.runtime.checkpoint_store.get_session_snapshot(control["source_snapshot_id"])
        assert CANONICAL_NOTES in json.dumps(source_snapshot.payload)
        assert "PRIVATE_RESEARCH_REASONING" in json.dumps(snapshot.payload)
        assert "OPAQUE_RESEARCH_STATE" not in json.dumps(snapshot.payload)
        if evidence is not None:
            from qitos.tracing.exporter import CanonicalTrajectoryExporter
            exporter = CanonicalTrajectoryExporter()
            exported = exporter.export(raw, view=PrivacyView.REDACTED_PUBLIC)
            reimported = exporter.reimport(exported)
            assert len(reimported.records) == len(raw.records)
            assert b"OPAQUE_RESEARCH_STATE" not in exported.data
            assert b"PRIVATE_RESEARCH_REASONING" not in exported.data
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / "research-trajectory.json").write_bytes(exported.data)
            control["public_export_sha256"] = exported.digest
            control["public_export_lossless"] = exported.loss.is_lossless
        control.update(run_id=result.run_id, attempt_id=session.attempt_id.value,
                       owner_generation=session.current_head.generation.value,
                       artifact_count=len(artifacts), trajectory_records=len(raw.records),
                       timeout_unknown=True, worker_eventually_finished=True, cleanup=current.env.cleanup_receipt)
        control.update(compactions=len(COMPACTIONS), continuation_resolutions=len(CONTINUATION_RESOLUTIONS),
                       canonical_notes_retained=True, opaque_state_isolated=True)
    assert control["cleanup"]["container_absent"]
    control["installed_distribution"] = "site-packages" in find_spec("qitos").origin
    assert control["installed_distribution"]
    print("G5_CONSUMER_RESULT=" + json.dumps(control, sort_keys=True))


def main():
    if len(sys.argv) > 1 and sys.argv[1] != "--evidence-dir":
        if sys.argv[1] == "create":
            create(Path(sys.argv[2]))
        else:
            restore(Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None)
        return
    evidence_args = [str(Path(sys.argv[2]).resolve())] if len(sys.argv) > 2 else []
    with tempfile.TemporaryDirectory(prefix="g5-installed-research-") as directory:
        root = Path(directory)
        (root / "source").mkdir()
        for phase in ("create", "restore"):
            completed = subprocess.run([sys.executable, __file__, phase, str(root), *evidence_args], capture_output=True,
                                       text=True, timeout=90)
            assert completed.returncode == 0, completed.stdout + completed.stderr
            if phase == "restore":
                print(completed.stdout)


if __name__ == "__main__":
    main()

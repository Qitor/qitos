"""Same-wheel offline composition proof. SDK I/O is scripted; runtime stays real."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace as NS
from typing import Any
from unittest.mock import patch

import qitos
from qitos.config import FakeCredentialResolver, build_agent_composition, load_agent_config
from qitos.core.artifact import ArtifactRef
from qitos.core.tool_result import ToolResult
from qitos.kit.artifact.store import FileArtifactStore
from qitos.core.context import DeclaredContextBudgetPolicy
from qitos.core.conversation import AssistantItem, ExchangeLog
from qitos.core.function_tool_decorator import function_tool
from qitos.core.memory import MemoryRecord
from qitos.core.session import PauseSafety, SafeBoundaryKind
from qitos.core.work_graph import WorkGraph
from qitos.engine.work_runtime import DurableWorkRuntime, LocalWorkScheduler
from qitos.kit.context.compaction import ClosedExchangeWindowCompactor
from qitos.kit.memory.adapter import MemorySourceAdapter
from qitos.kit.memory.memdir_memory import MemdirMemory
from qitos.qita.reader import candidate_file_reader
from qitos.tracing.exporter import CanonicalTrajectoryExporter, ExportArtifact
from qitos.tracing.paging import iter_records
from qitos.tracing.trajectory import LossReport, PrivacyView, TrajectoryQuery


def write_config(root):
    (root / "agent.yaml").write_text(
        f"""schema: qitos.agent
agent:
  name: combined
  protocol: json_decision_multi_v1
model:
  provider: openai_compatible
  model: offline
  context_window: 100000
  base_url: https://offline.invalid/v1
  credential: {{ref: offline}}
  request: {{max_tokens: 10240, retries: 0}}
tools:
  preset: none
context:
  budget_policy: budget
  allow_codec_loss: true
memory:
  sources: [memory]
compaction:
  provider: closed
lifecycle:
  policy: pause
runtime:
  data_root: {root / 'runtime'}
  environment: {{type: unsafe_host, workspace: {root}}}
  session: {{mode: durable, store: sqlite, path: {root / 'sessions.sqlite3'}}}
  trajectory: {{enabled: true, output: {root / 'trajectory.journal'}, privacy: private}}
budgets: {{max_steps: 15, max_requests: 12, max_runtime_seconds: 120}}
"""
    )


def snapshot_log(composition, session):
    snapshot = composition.runtime.checkpoint_store.get_session_snapshot(
        session.current_head.snapshot_id.value
    )
    component = next(c for c in snapshot.payload["components"] if c["slot"] == "conversation")
    return ExchangeLog.from_dict(component["payload"]["exchange_log"])


def artifact():
    body = b"required-artifact-body"
    return ArtifactRef(
        "required-artifact",
        "tool-result-output",
        hashlib.sha256(body).hexdigest(),
        "text/plain",
        len(body),
        encoding="utf-8",
        model_summary="required-artifact",
        required=True,
    )


def seed(root):
    root.mkdir(parents=True, exist_ok=False)
    memory = MemdirMemory(str(root / "memory"), create=True)
    memory.append(MemoryRecord("user", "remembered-value=17", 0))
    MemdirMemory(str(root / "other"), create=True)
    write_config(root)
    FileArtifactStore(root / "artifacts").put(artifact(), b"required-artifact-body")
    (root / "memory-seed.json").write_text(
        json.dumps(
            [
                x.to_dict()
                for x in MemorySourceAdapter(memory, namespace="project", required=True).contribute(None)
            ]
        )
    )


def execute(root, mode):
    failed = mode == "failure"
    no_loss = mode == "no-loss"
    restored = mode == "restore"
    memory = MemdirMemory(str(root / "memory"))
    source = MemorySourceAdapter(memory, namespace="project", required=True)
    assert [x.to_dict() for x in source.contribute(None)] == json.loads(
        (root / "memory-seed.json").read_text()
    )
    assert MemorySourceAdapter(MemdirMemory(str(root / "other")), namespace="other").contribute(None) == ()
    resources: list[Any] = []
    executions: list[int | str] = []
    requests, completions, views = [], [], []
    prior = json.loads((root / "first.json").read_text()) if restored else {}
    offset = len(prior["requests"]) if prior else 0
    released = threading.Event()
    worker_ack = threading.Event()
    prior_threads = {thread.ident for thread in threading.enumerate()}

    @function_tool(read_only=True, concurrency_safe=True)
    def read_chunk(index: int) -> str:
        """Read an offline fixture chunk."""
        executions.append(index)
        if index == 0:
            assert released.wait(10), "parallel fast tool must commit first"
        return f"chunk-{index:02d}:" + "x" * 1400

    @function_tool(read_only=True, concurrency_safe=True)
    def fast() -> ToolResult:
        """Return the fixture marker that releases the slow first call."""
        executions.append("fast")
        return ToolResult(status="success", output=17, artifact_refs=(artifact(),))

    class Hook:
        def on_event(self, event, state, record, engine):
            if event.payload.get("stage") == "request_view":
                views.append(event.payload["request_view"])
            if event.payload.get("stage") == "tool_slot_terminal":
                result = event.payload["tool_result"]
                completions.append(result["tool_name"])
                if result["tool_name"] == "fast":
                    released.set()

    class Pause:
        policy_id = "consumer.pause"
        supports_pause = True

        def should_pause(self, context):
            return not restored and not failed and context.step_id == 4

        def pause_safety(self, context):
            return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)

    def chunk(text="", reasoning=None, calls=None, finish=None):
        return NS(
            choices=[
                NS(
                    delta=NS(content=text, reasoning_content=reasoning, tool_calls=calls),
                    finish_reason=finish,
                )
            ],
            usage=NS(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        )

    def call(index, identity, name, arguments):
        return NS(index=index, id=identity, function=NS(name=name, arguments=arguments))

    class Stream:
        def __init__(self, items, broken=False):
            self.items, self.closed, self.broken = iter(items), 0, broken
            resources.append(self)

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.items)

        def close(self):
            self.closed += 1
            if self.broken:
                raise RuntimeError("SYNTHETIC_PRIVATE_MARKER")

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.closed = 0
            self.chat = NS(completions=self)
            resources.append(self)

        def create(self, **kwargs):
            assert kwargs.get("stream", False) is (not restored)
            messages = kwargs["messages"]
            (root / "sdk-request.json").write_text(json.dumps(messages))
            assert json.dumps(messages).count("remembered-value=17") == 1
            assert all(not key.startswith("_") for m in messages for key in m)
            requests.append(messages)
            stage = offset + len(requests) - 1
            # Existing codecs explicitly opt into dropping unsupported Chat reasoning.
            assert "reasoning_content" not in json.dumps(messages)
            calls = [c["id"] for m in messages for c in m.get("tool_calls", [])]
            results = [m["tool_call_id"] for m in messages if m["role"] == "tool"]
            assert sorted(calls) == sorted(results), (calls, results)
            assert len(results) == len(set(results))
            if stage == 1:
                outputs = {m["tool_call_id"]: m["content"] for m in messages if m["role"] == "tool"}
                assert json.loads(outputs["fast0"]) == 17
                assert outputs["chunk0"].startswith("chunk-00:")
            if restored:
                tool_calls = (
                    [
                        {
                            "id": f"chunk{stage}",
                            "type": "function",
                            "function": {"name": "read_chunk", "arguments": json.dumps({"index": stage})},
                        }
                    ]
                    if stage < 9
                    else None
                )
                return NS(
                    choices=[
                        NS(
                            message=NS(
                                content="" if stage < 9 else '{"final_answer":"remembered-value=17"}',
                                reasoning_content=f"plan round-{stage}" if stage < 9 else None,
                                tool_calls=tool_calls,
                            ),
                            finish_reason="tool_calls" if stage < 9 else "stop",
                        )
                    ],
                    usage=NS(prompt_tokens=2, completion_tokens=3, total_tokens=5),
                )
            if stage < 9:
                tools = [call(0, f"chunk{stage}", "read_chunk", json.dumps({"index": stage}))]
                if stage == 0:
                    tools.append(call(1, "fast0", "fast", "{}"))
                if failed and stage == 1:
                    tools[0].function.arguments = '{"index":'
                    return Stream(
                        [chunk(reasoning="plan "), chunk(reasoning="truncated", calls=tools)], broken=True
                    )
                return Stream(
                    [
                        chunk(reasoning="plan "),
                        chunk(reasoning=f"round-{stage}", calls=tools),
                        chunk(finish="tool_calls"),
                    ]
                )
            return Stream([chunk('{"final_answer":"remembered-value=17"}'), chunk(finish="stop")])

        def close(self):
            self.closed += 1
            if failed and len(requests) == 2:
                raise RuntimeError("SYNTHETIC_PRIVATE_MARKER")

    class Resolver:
        resolver_id = "consumer.handoff"

        def resolve(self, descriptor):
            # Ack only. The next clean process owns destination restoration.
            def ack():
                worker_ack.set()
                return None

            return ack

    config_path = root / "agent.yaml"
    if no_loss:
        config_path = root / "no-loss.yaml"
        config_path.write_text(
            (root / "agent.yaml").read_text().replace("allow_codec_loss: true", "allow_codec_loss: false")
        )
    config = load_agent_config(config_path)
    scheduler = LocalWorkScheduler(Resolver(), max_workers=1, queue_capacity=1)
    with patch.dict(
        sys.modules,
        {"openai": NS(OpenAI=Client, APIConnectionError=ConnectionError, APITimeoutError=TimeoutError)},
    ):
        with build_agent_composition(
            config,
            credential_resolver=FakeCredentialResolver(),
            extensions={
                "memory": lambda: source,
                "closed": ClosedExchangeWindowCompactor,
                "budget": lambda: DeclaredContextBudgetPolicy(
                    default_max_input_units=100000, protected_recent_exchanges=2
                ),
                "pause": Pause,
            },
        ) as composition:
            composition.runtime.work_runtime = DurableWorkRuntime(scheduler)
            composition.tool_registry.register(read_chunk)
            composition.tool_registry.register(fast)
            composition.engine.stream_callback = lambda text: None
            composition.engine.hooks.append(Hook())
            session = (
                composition.restore(prior["session_id"])
                if restored
                else composition.session("Read nine chunks and recall memory.")
            )
            # An independent work item under the same configured Agent stays untouched.
            unrelated = composition.session("unrelated") if not restored else None
            if unrelated is not None:
                other_id = unrelated.session_id.value
                other_head = unrelated.current_head.snapshot_id.value
            else:
                other_id, other_head = prior["other_id"], prior["other_head"]
            result = session.run()
            views = [
                event.payload["request_view"]
                for record in result.records
                for event in record.phase_events
                if event.payload.get("stage") == "request_view"
            ]
            log = snapshot_log(composition, session)
            inspection = session.inspect()
            assert inspection.budget["model_requests_consumed"] == offset + len(requests)
            if no_loss:
                assert result.state.final_result is None
                assert result.error_code == "provider_capability_loss", result.failure
                assert len(requests) == 1 and len(executions) == 2
            elif failed:
                assert result.state.final_result is None
                assert result.error_code == "provider_stream_protocol_error", result.failure
                assert executions == [0, "fast"] or executions == ["fast", 0]
                assert 1 not in executions
                assert len(requests) == 2
                failures = [
                    event.payload["provider_failure"]
                    for record in result.records
                    for event in record.phase_events
                    if event.payload.get("stage") == "provider_failure"
                ]
                failure = failures[-1]
                assert failure["provider_request_sent"] and failure["stage"] == "stream"
                assert failure["redacted_details"]["cleanup_failures"] == 2
                assert failure["redacted_details"]["usage"]["total_tokens"] == 5
                assert failure["redacted_details"]["partial_tool_calls"] == 1
                assert failure["redacted_details"]["partial_reasoning_characters"] == len("plan truncated")
                assert log.open_batch_id() is None
                completed = [i for i in log.items if i.kind == "tool_result"]
                assert len(completed) == 2
                before_recovery = len(requests)
                session.recover_work()
                assert len(requests) == before_recovery
                serialized = json.dumps(
                    result.failure.to_dict() if hasattr(result.failure, "to_dict") else result.failure
                )
                assert "SYNTHETIC_PRIVATE_MARKER" not in serialized
            elif not restored:
                assert session.lifecycle.value == "paused", result.failure
                receipt = session.handoff("combined", operation_id="handoff-combined")
                assert worker_ack.wait(10)
                assert receipt.state == "transfer_admitted"
                assert (
                    WorkGraph.from_canonical_dict(session.inspect().work_graph).operation_receipts[0].state
                    != "completed"
                )
            else:
                assert result.state.final_result == "remembered-value=17", result.failure
                graph = WorkGraph.from_canonical_dict(inspection.work_graph)
                assert graph.operation_receipts[0].state == "completed"
                assert len(prior["requests"]) + len(requests) == 10
            store = composition.runtime.checkpoint_store
            assert store is not None
            independent_head = store.get_session_head(other_id)
            assert independent_head is not None and independent_head.snapshot_id == other_head
            payload = {
                "session_id": session.session_id.value,
                "run_id": session.run_id.value,
                "other_id": other_id,
                "other_head": other_head,
                "requests": requests,
                "views": views,
                "executions": executions,
                "completions": completions,
                "log": log.to_persistence_dict(),
            }
            (root / ("failure.json" if failed else "last.json" if restored else "first.json")).write_text(
                json.dumps(payload)
            )
    assert all(resource.closed == 1 for resource in resources)
    assert not ({t.ident for t in threading.enumerate()} - prior_threads), "owned worker remains"
    assert memory.retrieve()[0].content == "remembered-value=17"
    if restored:
        verify(root, prior, payload)
    print(
        json.dumps(
            {"mode": mode, "requests": len(requests), "executions": len(executions), "source": qitos.__file__}
        )
    )


def verify(root, first, last):
    all_views = first["views"] + last["views"]
    compacted = [v for v in all_views if v["compaction_receipts"]]
    assert len(compacted) >= 2, len(compacted)
    log = ExchangeLog.from_dict(last["log"])
    assert log.open_batch_id() is None
    batches = [
        item.batch_id
        for item in log.items
        if isinstance(item, AssistantItem) and item.tool_calls() and item.batch_id is not None
    ]
    assert len(batches) == 9, len(batches)
    assert [item.identity.call_id for item in log.results_for_batch(batches[0])] == ["fast0", "chunk0"]
    assert first["completions"][:2] == ["fast", "read_chunk"]
    reasoning = [
        p
        for item in last["log"]["items"]
        if item["kind"] == "assistant"
        for p in item["parts"]
        if p["kind"] == "reasoning_block"
    ]
    assert len(reasoning) == 9
    assert sorted(p["summary"] for p in reasoning) == [f"plan round-{i}" for i in range(9)]
    old_items = {i["item_id"]: i for i in first["log"]["items"]}
    new_items = {i["item_id"]: i for i in last["log"]["items"]}
    assert all(new_items.get(key) == item for key, item in old_items.items())
    for view in all_views:
        assert view["context_budget"]["protected_recent_exchanges"] == 2
        assert len(view["context_contributions"]) in {1, 2}
        if view["artifact_refs"]:
            assert view["artifact_refs"][0]["artifact_id"] == "required-artifact"
            assert any(
                p.get("call_id") == "fast0" for i in view["selected_items"] for p in i.get("parts", [])
            )
        assert all(c["required"] for c in view["context_contributions"])
        for receipt in view["compaction_receipts"]:
            assert receipt["input_exchange_ids"] == view["selection"]["omitted_exchange_ids"]
            assert receipt["declared_losses"] == ["closed_exchange_omitted_without_summary"]
        assert view["selection"]["selected_units"] <= view["context_budget"]["available_input_units"]
    protections(log, all_views[-1])
    reader = candidate_file_reader(root / "trajectory.journal")
    try:
        query = TrajectoryQuery(session_id=last["session_id"], limit=17)
        records = tuple(iter_records(reader, query, view=PrivacyView.RAW_PRIVATE))
        pages, cursor = [], None
        while True:
            page = reader.read_page(query, cursor=cursor, view=PrivacyView.RAW_PRIVATE)
            pages.extend(page.records)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert [r.to_dict() for r in pages] == [r.to_dict() for r in records]
        exporter = CanonicalTrajectoryExporter()
        target = root / "canonical.json"
        receipt = exporter.export_file(reader, query, target, view=PrivacyView.RAW_PRIVATE)
        value = json.loads(target.read_bytes())
        artifact = ExportArtifact(
            exporter.capabilities.exporter_id,
            exporter.capabilities.format_version,
            "application/json",
            target.read_bytes(),
            receipt.digest,
            PrivacyView.RAW_PRIVATE,
            True,
            value["provenance"],
            LossReport.from_dict(value["loss"]),
        )
        assert [r.to_dict() for r in exporter.reimport(artifact).records] == [r.to_dict() for r in records]
        assert receipt.completed and receipt.digest == hashlib.sha256(target.read_bytes()).hexdigest()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "qitos.qita",
                "inspect",
                "session",
                last["session_id"],
                "--candidate-store",
                str(root / "trajectory.journal"),
            ],
            check=True,
            capture_output=True,
        )
        print(
            json.dumps(
                {
                    "combined": "passed",
                    "compactions": len(compacted),
                    "records": len(records),
                    "batches": len(batches),
                }
            )
        )
    finally:
        reader.close()


def protections(log, recorded):
    from dataclasses import replace
    from qitos.core.request_view import (
        ContextBudget,
        ContextBudgetExceededError,
        ContinuationRef,
        IncompatibleContinuationError,
        MissingArtifactError,
        RequestTarget,
        RequestView,
    )
    from qitos.core.session import ContinuationIdentity
    from qitos.core.conversation import AssistantItem, CallIdentity, IncompleteToolBatchError, ToolCall

    target = RequestTarget.from_dict(recorded["target"])
    before = log.to_persistence_dict()
    options: dict[str, Any] = dict(
        target=target,
        compaction_policy=ClosedExchangeWindowCompactor(),
        context_budget=ContextBudget(
            max_input_units=100000, reserved_output_units=10240, protected_recent_exchanges=2
        ),
        available_artifact_ids=["required-artifact"],
    )
    continuation = ContinuationRef(
        ContinuationIdentity.generate(),
        "consumer.continuation",
        target.provider,
        target.model,
        target.api_mode,
    )
    try:
        RequestView.from_exchange_log(log, continuation=continuation, **options)
    except ContextBudgetExceededError:
        pass
    else:
        raise AssertionError("opaque continuation must protect complete history")
    try:
        RequestView.from_exchange_log(log, continuation=replace(continuation, model="different"), **options)
    except IncompatibleContinuationError:
        pass
    else:
        raise AssertionError("continuation model mismatch must reject")
    try:
        RequestView.from_exchange_log(log, **{**options, "available_artifact_ids": []})
    except MissingArtifactError:
        pass
    else:
        raise AssertionError("required artifact cannot silently disappear")
    assert log.to_persistence_dict() == before
    pending = ExchangeLog.from_dict(before)
    pending.append(
        AssistantItem(
            "pending",
            "pending-exchange",
            [ToolCall(CallIdentity("consumer", "pending-call"), "pending-batch", "fast", "{}")],
        )
    )
    try:
        RequestView.from_exchange_log(pending, **options)
    except IncompleteToolBatchError:
        pass
    else:
        raise AssertionError("open tool batch must reject next request")


def namespace(root):
    from qitos.engine.runtime import LifecyclePolicy

    source = MemorySourceAdapter(MemdirMemory(str(root / "other")), namespace="other")
    seen = []

    class Client:
        def __init__(self, **kwargs):
            self.chat = NS(completions=self)

        def create(self, **kwargs):
            assert "remembered-value=17" not in json.dumps(kwargs["messages"])
            seen.append(True)
            return {"choices": [{"message": {"content": '{"final_answer":"empty namespace"}'}}]}

        def close(self):
            pass

    # A normal request without loss authorization remains executable.
    path = root / "namespace.yaml"
    path.write_text(
        (root / "agent.yaml").read_text().replace("allow_codec_loss: true", "allow_codec_loss: false")
    )
    with patch.dict(sys.modules, {"openai": NS(OpenAI=Client)}):
        with build_agent_composition(
            load_agent_config(path),
            credential_resolver=FakeCredentialResolver(),
            extensions={
                "memory": lambda: source,
                "budget": DeclaredContextBudgetPolicy,
                "closed": ClosedExchangeWindowCompactor,
                "pause": LifecyclePolicy,
            },
        ) as composition:
            assert composition.session("Inspect this namespace").run().state.final_result == "empty namespace"
    assert len(seen) == 1
    print("namespace: isolated actual provider request without loss opt-in")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["seed", "first", "restore", "failure", "no-loss", "namespace"])
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    assert "site-packages" in qitos.__file__, qitos.__file__
    root = args.root.resolve()
    if args.mode == "seed":
        seed(root)
    elif args.mode == "namespace":
        namespace(root)
    else:
        execute(root, args.mode)

"""Read-only, offline counterexamples for the V5 R1 candidate review.

Run with the pinned interpreter, from the selected lane checkout, passing A/B/C.
Exit zero means the diagnostic completed, NOT that framework qualification passed.
Synthetic transports only; no credential lookup, network or repository mutation.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch


HEADS = {
    "A": "5c6c2c370c0465e5471024a6e4870a9feb8c2b2a",
    "B": "4b62f46712f1683338c0b7590ae1290c492cb542",
    "C": "5b8a4363e59fd01286009741b26597f197de706b",
}


def emit(**facts):
    print(json.dumps(facts, sort_keys=True))


def model_probes():
    from qitos.models.codec import ProviderFailure
    from qitos.models.openai import OpenAICompatibleModel

    model = OpenAICompatibleModel(
        model="offline", api_key="offline", base_url="https://offline.invalid/v1"
    )

    def chunk(content="", reasoning=None, finish=None):
        return NS(choices=[NS(delta=NS(content=content, reasoning_content=reasoning,
                                      tool_calls=None), finish_reason=finish)], usage=None)

    class Stream:
        def __init__(self, items, close_error=False):
            self.items = iter(items)
            self.close_error = close_error

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.items)

        def close(self):
            if self.close_error:
                raise RuntimeError("SYNTHETIC_PRIVATE_MARKER")

    cases = (
        ("R1-M1", [chunk(reasoning="synthetic reasoning"), chunk("answer"),
                   chunk(finish="stop")], False),
        ("R1-M2", [chunk("partial")], True),
    )
    for finding, items, close_error in cases:
        stream = Stream(items, close_error)
        closed = []
        client = NS(chat=NS(completions=NS(create=lambda **kw: stream)),
                    close=lambda: closed.append(True))
        with patch("openai.OpenAI", return_value=client):
            try:
                response = model.qitos_stream_transport({"messages": []})
                emit(finding=finding, text=response.text,
                     finish_reason=response.finish_reason,
                     native_items=response.native_items, client_closed=len(closed))
            except Exception as exc:
                emit(finding=finding, exception_type=type(exc).__name__,
                     typed_provider_failure=isinstance(exc, ProviderFailure),
                     synthetic_marker_exposed="SYNTHETIC_PRIVATE_MARKER" in str(exc),
                     client_closed=len(closed))


def config_probes():
    import yaml
    from qitos.config.loader import load_agent_config

    raw = yaml.safe_load(Path("examples/v5/r1_b_memory_context/agent.yaml").read_text())
    for context in ({"budget_policy": "budget"}, {"allow_codec_loss": True}):
        encoded = yaml.safe_dump({**raw, "context": context}).encode()
        # Exercise the public YAML loader; replace file bytes, not its parser.
        with patch.object(Path, "read_bytes", return_value=encoded):
            try:
                load_agent_config("review-agent.yaml")
                emit(finding="R1-DX1", key=next(iter(context)), accepted=True)
            except Exception as exc:
                emit(finding="R1-DX1", key=next(iter(context)),
                     error_type=type(exc).__name__, detail=str(exc))


def work_probes():
    from qitos.core.session import (
        AgentIdentity, RunIdentity, SessionIdentity, SessionLifecycle, WorkItemIdentity,
    )
    from qitos.core.work_graph import (
        WorkDescriptor, WorkGraph, WorkItem, WorkOperationReceipt, WorkOwner,
    )
    from qitos.engine.session_runtime import Session
    from qitos.engine.work_runtime import DurableWorkRuntime, WorkRuntimeError

    agent, old = AgentIdentity.generate(), AgentIdentity.generate()
    identities = {name: WorkItemIdentity.generate() for name in ("current", "unrelated")}
    sessions = {name: SessionIdentity.generate() for name in identities}

    def descriptor(name):
        return WorkDescriptor(
            name, "handoff", sessions[name].value, identities[name].value,
            [], [], [], {}, [], [], [], [], [], [], 0, 1,
        )

    graph = WorkGraph("review-graph")
    for name, identity in identities.items():
        graph.add_work_item(WorkItem(identity, sessions[name], "task", "paused", WorkOwner(old, 0)))
        graph.transfer_owner(identity, expected_generation=0, to_agent_id=agent,
                             transfer_id="ownership:" + name)
        graph.operation_receipts.append(WorkOperationReceipt(
            name, "handoff", "a" * 64, "transfer_admitted", outcome_unknown=True,
            descriptor=descriptor(name).to_dict(),
        ))
    graph = WorkGraph.from_canonical_dict(graph.to_persistence_dict())
    # Unit-level production-method counterexample, NOT a public multi-process E2E.
    session = object.__new__(Session)
    session._engine = NS(_qitos_work_graph=graph)
    session._work_item_id = identities["current"]
    session._agent_id = agent
    session._session_id = sessions["current"]
    session._run_id = RunIdentity.generate()
    session._reconcile_handoff(SessionLifecycle.COMPLETED)
    first, unrelated = graph.operation_receipts
    emit(finding="R1-C1", current_state=first.state, unrelated_state=unrelated.state,
         same_terminal_reference=first.terminal_receipt_ref == unrelated.terminal_receipt_ref)

    class Rejected:
        scheduler_id = "review-rejected"
        calls = 0

        def dispatch(self, request):
            self.calls += 1
            raise WorkRuntimeError("queue_capacity_exceeded", "synthetic queue is full")

        def reattach(self, request, worker_ref):
            return None

        def close(self):
            pass

    scheduler = Rejected()
    runtime = DurableWorkRuntime(scheduler)
    graph = WorkGraph("queue-graph")
    saved = []
    work = descriptor("current")
    persist = lambda: saved.append(graph.to_persistence_dict())
    try:
        runtime.submit(graph=graph, descriptor=work, persist=persist)
    except WorkRuntimeError as exc:
        current = graph.operation_receipts[0]
        retry = runtime.submit(graph=graph, descriptor=work, persist=persist)
        emit(finding="R1-C2", error=exc.code, state=current.state,
             admission_state=current.admission_state, outcome_unknown=current.outcome_unknown,
             persisted_snapshots=len(saved), retry_state=retry.state,
             dispatch_calls_including_retry=scheduler.calls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=HEADS)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != HEADS[args.lane]:
        raise SystemExit("Run from the exact reviewed lane HEAD; this is historical evidence.")
    # Script lives in the main documentation draft, imports must come from the lane.
    import sys
    sys.path.insert(0, str(root))
    import qitos
    if not Path(qitos.__file__).resolve().is_relative_to(root):
        raise SystemExit("Source identity mismatch")
    emit(lane=args.lane, head=head, qualification="diagnostic_only")
    {"A": model_probes, "B": config_probes, "C": work_probes}[args.lane]()


if __name__ == "__main__":
    main()

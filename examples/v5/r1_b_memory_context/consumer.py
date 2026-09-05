"""Installed two-process consumer: seed, exit, then rebuild configured recall."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

import qitos
from qitos.config import build_agent_composition, load_agent_config
from qitos.core.context import DeclaredContextBudgetPolicy
from qitos.core.function_tool_decorator import function_tool
from qitos.core.memory import MemoryRecord
from qitos.kit.context.compaction import ClosedExchangeWindowCompactor
from qitos.kit.memory.adapter import MemorySourceAdapter
from qitos.kit.memory.memdir_memory import MemdirMemory


@function_tool(read_only=True, concurrency_safe=True)
def read_chunk(index: int) -> str:
    """Return a deterministic text chunk; no network or filesystem side effects."""
    return f"chunk-{index:02d}:" + "x" * 1400


class DeterministicProvider:
    """Observe actual encoded requests and drive real Engine/tool transactions."""
    model = "memory-context-deterministic"
    qitos_protocol = "react_text_v1"

    def __init__(self):
        self.requests = []

    def call_raw(self, messages, **options):
        snapshot = json.loads(json.dumps(messages))
        encoded = json.dumps(snapshot)
        assert encoded.count("remembered-value=17") == 1
        assert all(not key.startswith("_") for message in snapshot for key in message)
        self.requests.append(snapshot)
        stage = len(self.requests) - 1
        content = (f"Thought: read a chunk\nAction: read_chunk(index={stage})"
                   if stage < 9 else "Final Answer: remembered-value=17")
        return {"choices": [{"message": {"content": content}}]}


class EmptyNamespaceProvider:
    model = "memory-context-deterministic"
    qitos_protocol = "react_text_v1"

    def call_raw(self, messages, **options):
        assert "remembered-value=17" not in json.dumps(messages)
        return {"choices": [{"message": {"content": "Final Answer: empty namespace"}}]}


def seed(root):
    root.mkdir(parents=True, exist_ok=False)
    memory = MemdirMemory(str(root / "project"), create=True)
    memory.append(MemoryRecord("user", "remembered-value=17", 0))
    values = MemorySourceAdapter(memory, namespace="project").contribute(None)
    assert len(values) == 1
    (root / "seed.json").write_text(json.dumps([item.to_dict() for item in values]))
    MemdirMemory(str(root / "other"), create=True)
    print("seed: one durable text record; process may exit")


def run(root):
    memory = MemdirMemory(str(root / "project"))
    source = MemorySourceAdapter(memory, namespace="project")
    assert [item.to_dict() for item in source.contribute(None)] == json.loads((root / "seed.json").read_text())
    other = MemorySourceAdapter(MemdirMemory(str(root / "other")), namespace="other")
    assert other.contribute(None) == ()
    config = load_agent_config(Path(__file__).with_name("agent.yaml"))
    config = replace(config, runtime=replace(
        config.runtime, data_root=str(root / "runtime"),
        environment=replace(config.runtime.environment, workspace=str(root)),
        session=replace(config.runtime.session, path=str(root / "sessions.sqlite3")),
        trajectory=replace(config.runtime.trajectory, output=str(root / "trajectory.journal")),
    ))
    provider = DeterministicProvider()
    # The resolver/factory binds the namespace to its resource. Namespace does
    # not grant directory access. The YAML configuration explicitly opts into codec loss.
    with build_agent_composition(config, model_override=provider, extensions={
        "project_memory": lambda: MemorySourceAdapter(memory, namespace="project", required=True),
        "closed_window": ClosedExchangeWindowCompactor,
        "budget": lambda: DeclaredContextBudgetPolicy(
            default_max_input_units=100000, protected_recent_exchanges=2,
        ),
    }) as composition:
        composition.tool_registry.register(read_chunk)
        session = composition.session("Read nine text chunks and recall the remembered value.")
        result = session.run()
        assert result.state.final_result == "remembered-value=17", result.failure
        views = [event.payload["request_view"] for record in result.records for event in record.phase_events
                 if event.payload.get("stage") == "request_view"]
        assert len(views) == len(provider.requests) == 10
        compacted = [view for view in views if view["compaction_receipts"]]
        assert len(compacted) >= 2
        for view, messages in zip(views, provider.requests):
            selection = view["selection"]
            assert selection["selected_units"] <= view["context_budget"]["available_input_units"]
            assert view["context_budget"]["protected_recent_exchanges"] == 2
            assert len(view["context_contributions"]) == 1
            projected = json.dumps(view["selected_items"])
            encoded = json.dumps(messages)
            for index in range(9):
                marker = f"chunk-{index:02d}:"
                assert (marker in projected) == (marker in encoded)
            assert str(root) not in json.dumps(view["context_contributions"])
        assert session.inspect().last_request_view.request_id == views[-1]["request_id"]
    with build_agent_composition(config, model_override=EmptyNamespaceProvider(), extensions={
        "project_memory": lambda: other,
        "closed_window": ClosedExchangeWindowCompactor,
        "budget": lambda: DeclaredContextBudgetPolicy(
            default_max_input_units=100000, protected_recent_exchanges=2,
        ),
    }) as isolated:
        assert isolated.session("Check the bound namespace.").run().state.final_result == "empty namespace"
    assert memory.retrieve()[0].content == "remembered-value=17"
    report = {"requests": len(views), "budget_compactions": len(compacted),
              "memory_records": 1, "namespace_isolated": True, "namespace_requests": 1,
              "qitos_source": qitos.__file__}
    (root / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seed", "run"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    {"seed": seed, "run": run}[args.mode](args.root.resolve())

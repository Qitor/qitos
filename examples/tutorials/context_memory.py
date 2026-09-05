"""Explicit contributor, memory, selector and compactor factories; no network."""
import argparse
from dataclasses import replace
from pathlib import Path

from qitos.config import build_agent_composition
from qitos.core.context import (
    DeclaredContextBudgetPolicy, PriorityContextSelectionPolicy, StaticContextContributor,
)
from qitos.core.memory import MemoryRecord
from qitos.kit.context.compaction import ClosedExchangeWindowCompactor
from qitos.kit.memory.adapter import MemorySourceAdapter
from qitos.kit.memory.memdir_memory import MemdirMemory
from qitos.qita.reader import default_reader
from qitos.tracing.trajectory import PrivacyView

from session_walkthrough import FakeProvider, add, configuration


class ContextProvider(FakeProvider):
    """Four scripted tool turns make closed-exchange omission observable."""

    def __init__(self):
        self.stage = 0

    def call_raw(self, messages, **options):
        content = (f"Thought: inspect\nAction: add(a=20, b=22)"
                   if self.stage < 4 else "Final Answer: arithmetic complete")
        self.stage += 1
        return {"choices": [{"message": {"content": content}}]}


class AuditedSelector(PriorityContextSelectionPolicy):
    def __init__(self):
        self.seen = set()

    def select(self, contributions, **options):
        contributions = tuple(contributions)
        self.seen.update(item.contribution_id for item in contributions)
        return super().select(contributions, **options)


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    config = replace(
        configuration(root),
        context={"contributors": ["project"], "selector": "selector", "budget_policy": "budget", "allow_codec_loss": True},
        memory={"sources": ["project_memory"]}, compaction={"provider": "closed_window"})
    config = replace(config, budgets=replace(config.budgets, max_steps=6, max_requests=6))
    selector = AuditedSelector()
    memory = MemdirMemory(str(root / "memory"), create=True)
    memory.append(MemoryRecord("user", '20 + 22 = 42', 0))
    with build_agent_composition(config, model_override=ContextProvider(), extensions={
        "project": lambda: StaticContextContributor("lesson.project", "project", "Use arithmetic only."),
        "project_memory": lambda: MemorySourceAdapter(memory, namespace="notes", required=True),
        "selector": selector, "closed_window": ClosedExchangeWindowCompactor,
        "budget": lambda: DeclaredContextBudgetPolicy(default_max_input_units=30000, protected_recent_exchanges=2),
    }) as composition:
        composition.tool_registry.register(add)
        session = composition.session("Compute, then conclude")
        assert session.run().state.final_result == "arithmetic complete"
        assert "lesson.project" in selector.seen
        assert any(identity.startswith("memory:notes:") for identity in selector.seen)
        trajectory = default_reader(root).read_session(session.session_id.value, view=PrivacyView.RAW_PRIVATE)
        assert any(record.kind.value == "compaction" and not record.loss.is_lossless for record in trajectory.records)
    print("context selected; memory selected; compaction loss recorded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    run(parser.parse_args().root.resolve())

"""Explicit contributor, memory, selector and compactor factories; no network."""
import argparse
from dataclasses import replace
import hashlib
from pathlib import Path

from qitos.config import build_agent_composition
from qitos.core.context import (
    DeclaredContextBudgetPolicy, PriorityContextSelectionPolicy, StaticContextContributor,
)
from qitos.core.request_view import CompactionReceipt
from qitos.qita.reader import default_reader
from qitos.tracing.trajectory import PrivacyView

from session_walkthrough import FakeProvider, add, configuration


class AuditedSelector(PriorityContextSelectionPolicy):
    def __init__(self):
        self.seen = set()

    def select(self, contributions, **options):
        contributions = tuple(contributions)
        self.seen.update(item.contribution_id for item in contributions)
        return super().select(contributions, **options)


class OmitClosedExchange:
    """Explicitly lossy omission for this arithmetic fixture only."""
    policy_id = "tutorial.omit_closed"

    def __init__(self):
        self.calls = 0

    def compact(self, **values):
        self.calls += 1
        return CompactionReceipt(
            receipt_id="compaction_" + values["selected_digest"][:24],
            input_exchange_ids=tuple(values["exchange_ids"]), policy_id=self.policy_id,
            output_digest=hashlib.sha256(b"").hexdigest(),
            declared_losses=("closed_exchange_omitted_without_summary",),
        )


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    config = replace(
        configuration(root),
        context={"contributors": ["project"], "selector": "selector", "budget_policy": "budget"},
        memory={"sources": ["memory"]}, compaction={"provider": "compactor"})
    selector, compactor = AuditedSelector(), OmitClosedExchange()
    with build_agent_composition(config, model_override=FakeProvider(), extensions={
        "project": lambda: StaticContextContributor("lesson.project", "project", "Use arithmetic only."),
        "memory": lambda: StaticContextContributor("lesson.memory", "memory", "20 + 22 = 42"),
        "selector": selector, "compactor": compactor,
        "budget": lambda: DeclaredContextBudgetPolicy(default_max_input_units=4096, protected_recent_exchanges=0),
    }) as composition:
        composition.tool_registry.register(add)
        session = composition.session("Compute, then conclude")
        assert session.run().state.final_result == "arithmetic complete"
        assert {"lesson.project", "lesson.memory"} <= selector.seen
        assert compactor.calls > 0
        trajectory = default_reader(root).read_session(session.session_id.value, view=PrivacyView.RAW_PRIVATE)
        assert any(record.kind.value == "compaction" and not record.loss.is_lossless for record in trajectory.records)
    print("context selected; memory selected; compaction loss recorded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    run(parser.parse_args().root.resolve())

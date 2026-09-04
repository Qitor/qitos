"""Replace the provider and inject context, without changing the kernel."""
import argparse
from dataclasses import replace
from pathlib import Path

from notes import FakeProvider, configuration, summarize_note
from qitos.config import build_agent_composition
from qitos.core.context import StaticContextContributor


class ObservedFakeProvider(FakeProvider):
    """Keep the public provider call shape and validate selected context."""
    def __init__(self):
        super().__init__()
        self.requests = 0

    def call_raw(self, messages, **options):
        assert "notes-project-context" in str(messages)
        self.requests += 1
        return super().call_raw(messages, **options)


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    config = replace(configuration(root), context={"contributors": ["project"]})
    provider = ObservedFakeProvider()
    with build_agent_composition(config, model_override=provider, extensions={
        "project": lambda: StaticContextContributor("notes.project", "project", "notes-project-context"),
    }) as composition:
        composition.tool_registry.register(summarize_note)
        result = composition.session("Index both notes").run()
        assert result.state.final_result == "Indexed 2 notes: Session, Artifact."
        assert provider.requests == 3
    print("provider replaced; context observed; requests=3")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    run(parser.parse_args().root.resolve())

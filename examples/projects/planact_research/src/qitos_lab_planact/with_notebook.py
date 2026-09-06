"""Compose installed projects through public extension slots, not Engine changes.

Install qitos-lab-pi alongside this project before importing this optional module.
The caller selects/owns the Memdir root and explicitly opts into compaction loss.
"""

from contextlib import contextmanager
from dataclasses import replace

from qitos.config import build_agent_composition
from qitos.kit.context.compaction import ClosedExchangeWindowCompactor
from qitos.kit.memory.adapter import MemorySourceAdapter
from qitos.kit.memory.memdir_memory import MemdirMemory
from qitos_lab_pi.extension import statistics_tools
from .agent import build_factory


@contextmanager
def composition_with_notebook(
    config,
    task,
    *,
    notebook,
    credential_resolver=None,
    model_override=None,
    context_budget=None
):
    memory = MemdirMemory(str(notebook))  # Reopen; never clear or silently initialize.
    base_factory = build_factory(task)

    def factory(**bindings):
        for tool in statistics_tools():
            bindings["tool_registry"].register(tool)
        return base_factory(**bindings)

    config = replace(
        config,
        memory={"sources": ["research_notebook"]},
        context={**dict(config.context), "allow_codec_loss": True},
        compaction={"provider": "closed_window"},
    )
    extensions = {
        "research_notebook": MemorySourceAdapter(memory, namespace="research"),
        "closed_window": ClosedExchangeWindowCompactor(),
    }
    if context_budget is not None:
        config = replace(
            config, context={**dict(config.context), "budget_policy": "research_budget"}
        )
        extensions["research_budget"] = context_budget
    with build_agent_composition(
        config,
        credential_resolver=credential_resolver,
        model_override=model_override,
        agent_factory=factory,
        extensions=extensions,
    ) as current:
        yield current

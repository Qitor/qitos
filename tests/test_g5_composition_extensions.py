"""Public composition resolves and invokes caller-owned context extensions."""
from dataclasses import replace
import json

import pytest

from qitos.config import build_agent_composition
from qitos.config.errors import CompositionError
from qitos.core.context import PriorityContextSelectionPolicy, StaticContextContributor
from test_s4_lane_a_public_authoring import _config, _FinalModel


def test_configured_context_memory_and_selector_reach_the_provider(tmp_path):
    selected = []
    calls = []

    class Selector(PriorityContextSelectionPolicy):
        def select(self, contributions, **kwargs):
            values = tuple(contributions)
            selected.extend(item.contribution_id for item in values)
            return super().select(values, **kwargs)

    class Model(_FinalModel):
        def call_raw(self, messages, **options):
            calls.append(json.dumps(messages))
            return super().call_raw(messages, **options)

    config = replace(_config(tmp_path), context={"contributors": ["project"], "selector": "selector"},
                     memory={"sources": ["memory"]})
    with build_agent_composition(config, model_override=Model(), extensions={
        "project": lambda: StaticContextContributor("project", "project", "PROJECT_SENTINEL"),
        "memory": lambda: StaticContextContributor("memory", "memory", "MEMORY_SENTINEL"),
        "selector": Selector,
    }) as composition:
        result = composition.session().run()
    assert result.state.final_result == "done"
    assert {"project", "memory"} <= set(selected)
    assert len(calls) == 1
    assert "PROJECT_SENTINEL" in calls[0] and "MEMORY_SENTINEL" in calls[0]


@pytest.mark.parametrize("values", [
    {"context": {"unused": 1}}, {"memory": {"policy": "automatic"}},
    {"compaction": {"threshold": 1}}, {"lifecycle": {"background": True}},
    {"failure_policy": {"provider": "resend"}}, {"tool_options": {"max_concurrency": 0}},
    {"tool_options": {"safe_tools_by_name": ["read_file"]}},
])
def test_unimplemented_configuration_rejects_before_model_construction(tmp_path, values, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("model was constructed before configuration admission")
    monkeypatch.setattr("qitos.config.builder.build_model", forbidden)
    with pytest.raises(CompositionError):
        build_agent_composition(replace(_config(tmp_path), **values))

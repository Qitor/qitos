"""Bidirectional mutations and atomic rejection for the public Observation."""
from copy import deepcopy
import json

import pytest

from qitos.core.observation import Observation
from qitos.core.tool_result import ToolResult


def test_attributes_and_mapping_have_one_authority():
    obs = Observation(step_id=2, task="before")
    obs.task = "after"
    assert obs["task"] == obs.to_dict()["task"] == obs.to_legacy_dict()["task"] == "after"
    obs["task"] = "mapped"
    assert obs.task == "mapped"
    obs["step"] = 3
    assert obs.step_id == obs["step_id"] == 3
    obs.step_id = 4
    assert obs["step"] == 4
    obs.update(step_id=5, step=5)
    assert obs.step_id == 5


def test_nested_values_and_snapshots_are_independent():
    source = {"nested": {"values": [1]}}
    obs = Observation(step_id=0, state=source, metadata=source)
    source["nested"]["values"].append(9)
    assert obs.state["nested"]["values"] == [1]
    canonical, legacy = obs.to_dict(), obs.to_legacy_dict()
    obs.state["nested"]["values"].append(2)
    obs["metadata"]["nested"]["values"].append(3)
    assert obs["state"]["nested"]["values"] == [1, 2]
    assert obs.metadata["nested"]["values"] == [1, 3]
    assert canonical["state"]["nested"]["values"] == legacy["state"]["nested"]["values"] == [1]


@pytest.mark.parametrize("mutation", [
    lambda o: o.update(task="partial", step=2, step_id=3),
    lambda o: o.update(task="partial", step=True, step_id=1),
    lambda o: o.update(task="partial", state=[]),
    lambda o: o.update(task=None),
    lambda o: o.update(action_results={}),
    lambda o: o.update(step=-1),
    lambda o: o.pop("step"),
    lambda o: o.pop("step_id"),
    lambda o: o.clear(),
    lambda o: o.__delitem__("metadata"),
])
def test_invalid_mutations_are_atomic(mutation):
    obs = Observation(step_id=1, task="original", metadata={"keep": [1]})
    before = obs.to_dict()
    with pytest.raises((TypeError, ValueError)):
        mutation(obs)
    assert obs.to_dict() == before


def test_constructor_alias_conflicts_are_rejected():
    with pytest.raises(ValueError, match="conflict"):
        Observation.from_value({"task": "x", "step": 1, "step_id": 2})


def test_mapping_results_are_legacy_projection_of_canonical_objects():
    obs = Observation(step_id=0)
    obs["action_results"] = [{"status": "success", "output": {"answer": [1]}}]
    assert isinstance(obs.action_results[0], ToolResult)
    assert obs.to_dict()["action_results"][0] == obs.action_results[0].to_dict()
    assert obs["action_results"] == obs.to_legacy_dict()["action_results"]
    snapshot = obs.to_dict()
    obs.action_results = [ToolResult(output="new")]
    assert obs["action_results"][0]["output"] == "new"
    assert snapshot["action_results"][0]["output"] == {"answer": [1]}
    assert dict(obs)["action_results"] == obs["action_results"]
    assert dict(obs.items())["action_results"] == obs["action_results"]
    assert json.loads(json.dumps(obs))["action_results"] == obs["action_results"]


def test_extension_mutators_and_copy():
    obs = Observation(step_id=1)
    obs |= {"extra": {"n": [1]}, "task": "updated"}
    assert obs.task == "updated"
    assert obs.setdefault("other", [2]) == [2]
    assert obs.popitem() == ("other", [2])
    assert obs.pop("extra") == {"n": [1]}
    assert obs.pop("missing", None) is None
    assert obs.setdefault("task", "ignored") == "updated"
    copied = obs.copy()
    assert copied.to_dict() == obs.to_dict()
    copied.metadata["changed"] = True
    assert obs.metadata == {}
    assert deepcopy(obs).to_dict() == obs.to_dict()

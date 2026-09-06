"""Installed PlanAct + persistent notebook + independent Pi extension consumer."""

from dataclasses import replace
from importlib.resources import files
import json
from pathlib import Path
import sys
import tempfile

from qitos.config import (
    EnvironmentConfig,
    SessionConfig,
    TrajectoryConfig,
    load_agent_config,
)
from qitos.core.context import DeclaredContextBudgetPolicy
from qitos.core.memory import MemoryRecord
from qitos.kit.memory.memdir_memory import MemdirMemory
from qitos_lab_planact.with_notebook import composition_with_notebook
from installed_consumer import Model


def run(config_path, root):
    notebook = root / "notebook"
    memory = MemdirMemory(str(notebook), create=True)
    memory.append(MemoryRecord(role="user", content="APPROVED_WEIGHT=0.8", step_id=0))
    config = load_agent_config(config_path)
    # Mechanism proof only: no filesystem/command action is requested in this test.
    env = EnvironmentConfig(
        type="unsafe_host",
        image="",
        workspace=str(root),
        container_workspace="",
        network="host",
        read_only_root=False,
        cap_drop=False,
        no_new_privileges=False,
        pids_limit=None,
        memory_mb=None,
        cpus=None,
        cleanup_required=False,
    )
    config = replace(
        config,
        runtime=replace(
            config.runtime,
            environment=env,
            session=SessionConfig(store="sqlite", path=str(root / "sessions.sqlite3")),
            trajectory=TrajectoryConfig(output=str(root / "trajectory.journal")),
        ),
    )
    actions = [
        ("revise_plan", {"steps": [str(index) + "x" * 6000], "evidence": "new data"})
        for index in range(10)
    ]
    actions.append(("weighted_summary", {"values": [10, 20], "weights": [3, 7]}))
    model = Model(actions)
    task = json.loads(files("qitos_lab_planact").joinpath("tasks.json").read_text())[0]
    with composition_with_notebook(
        config,
        task,
        notebook=notebook,
        model_override=model,
        context_budget=DeclaredContextBudgetPolicy(
            default_max_input_units=100000,
            protected_recent_exchanges=2,
        ),
    ) as current:
        result = current.session(
            "Use the notebook and validate the weighted result."
        ).run()
        assert str(result.state.stop_reason) == "final", result.failure
        assert result.state.plan_version == 10
        assert any(
            "APPROVED_WEIGHT=0.8" in json.dumps(messages) for messages in model.seen
        )
        outputs = [
            item.output
            for record in result.records
            for item in record.action_results
            if item.tool_name == "weighted_summary" and item.status == "success"
        ]
        assert outputs == [{"mean": 17.0, "total_weight": 10}]
        views = [
            event.payload["request_view"]
            for record in result.records
            for event in record.phase_events
            if "request_view" in event.payload
        ]
        compacted = {
            receipt["receipt_id"]
            for view in views
            for receipt in view.get("compaction_receipts", [])
        }
        assert compacted, "declared compaction must actually occur"
    assert MemdirMemory(str(notebook)).retrieve()[0].content == "APPROVED_WEIGHT=0.8"
    return {
        "requests": model.requests,
        "plans": 10,
        "extension_mean": 17,
        "compactions": len(compacted),
        "persistent_memory": True,
    }


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="qitos-lab-composition-") as directory:
        print(json.dumps(run(Path(sys.argv[1]), Path(directory))))

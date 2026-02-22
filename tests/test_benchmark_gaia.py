from __future__ import annotations

from qitos.benchmark import GaiaAdapter


def test_gaia_adapter_converts_records_to_tasks():
    records = [
        {
            "task_id": "g1",
            "Question": "What is 2+2?",
            "Final answer": "4",
            "Level": "1",
            "file_name": "notes.txt",
        },
        {
            "id": "g2",
            "question": "Name the capital of Japan.",
            "answer": "Tokyo",
            "files": ["ctx/a.txt", "ctx/b.txt"],
        },
    ]

    adapter = GaiaAdapter(include_raw_record=False, local_dir="")
    tasks = adapter.to_tasks(records, split="validation")

    assert len(tasks) == 2
    assert tasks[0].id == "g1"
    assert tasks[0].objective == "What is 2+2?"
    assert tasks[0].inputs["benchmark"] == "GAIA"
    assert tasks[0].resources[0].path == "notes.txt"
    assert tasks[0].env_spec is not None
    assert tasks[0].env_spec.type == "host"

    assert tasks[1].id == "g2"
    assert len(tasks[1].resources) == 2
    assert tasks[1].success_criteria
    assert "Reference answer (for evaluation): Tokyo" in tasks[1].success_criteria


def test_gaia_adapter_fallback_id_and_objective():
    records = [{"misc": "x"}]
    adapter = GaiaAdapter(task_prefix="gaiax", include_raw_record=True)
    tasks = adapter.to_tasks(records, split="dev")
    task = tasks[0]

    assert task.id == "gaiax_dev_00000"
    assert task.objective.startswith("Solve this GAIA benchmark task")
    assert task.metadata["benchmark"] == "GAIA"
    assert "raw_record" in task.metadata

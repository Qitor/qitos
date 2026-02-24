from __future__ import annotations

import json
from pathlib import Path

from qitos.benchmark import CyBenchAdapter, CyBenchRuntime, score_cybench_submission


def _build_fake_cybench(root: Path) -> Path:
    bench = root / "cybench"
    task_rel = Path("benchmark/demo/task-a")
    task_dir = bench / task_rel
    (task_dir / "metadata" / "solution").mkdir(parents=True, exist_ok=True)
    (task_dir / "challenge").mkdir(parents=True, exist_ok=True)

    metadata = {
        "categories": ["crypto"],
        "difficulty": "1",
        "easy_prompt": "easy",
        "hard_prompt": "hard",
        "target_host": "",
        "tools": {"terminal": [], "gui": [], "languages": ["python3"]},
        "internet": {"useful": False, "necessary": False},
        "stateful_shell": False,
        "subtasks": [
            {
                "subtask": "s1",
                "question": "q1",
                "answer": "a1",
                "answer_format": "fmt",
                "hints": [],
                "commands": [],
                "solution_files": [],
                "context": "",
                "annotator_note": "",
                "tools": {"terminal": [], "gui": [], "languages": []},
                "internet": {"useful": False, "necessary": False},
                "stateful_shell": False,
            },
            {
                "subtask": "s2",
                "question": "q2",
                "answer": "FLAG{XYZ}",
                "answer_format": "FLAG{...}",
                "hints": [],
                "commands": [],
                "solution_files": [],
                "context": "",
                "annotator_note": "",
                "tools": {"terminal": [], "gui": [], "languages": []},
                "internet": {"useful": False, "necessary": False},
                "stateful_shell": False,
            },
        ],
    }
    (task_dir / "metadata" / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (bench / "subtask_list.txt").write_text(str(task_rel) + "\n", encoding="utf-8")
    (bench / "task_list.txt").write_text(str(task_rel) + "\n", encoding="utf-8")

    (task_dir / "challenge" / "note.txt").write_text("hello", encoding="utf-8")
    (task_dir / "init_script.sh").write_text(
        "#!/bin/bash\nTMP_DIR=\"$1\"\ncp challenge/note.txt \"$TMP_DIR\"\n", encoding="utf-8"
    )
    (task_dir / "metadata" / "requirements.sh").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (task_dir / "metadata" / "solution" / "solution.sh").write_text("#!/bin/bash\necho FLAG{XYZ}\n", encoding="utf-8")
    return bench


def test_cybench_adapter_and_runtime(tmp_path: Path):
    bench = _build_fake_cybench(tmp_path)
    adapter = CyBenchAdapter(cybench_root=str(bench), run_with_subtasks=True)

    rows = adapter.load_records(limit=10)
    assert len(rows) == 1
    task = adapter.to_task(rows[0], split="guided", idx=0)
    assert task.inputs["benchmark"] == "cybench"
    assert task.inputs["run_with_subtasks"] is True

    workspace = tmp_path / "ws"
    rt = CyBenchRuntime(task_dir=rows[0]["task_dir"], workspace=str(workspace), run_requirements=True, run_start_docker=False)
    prep = rt.prepare()
    assert prep["steps"]
    assert (workspace / "note.txt").exists()

    sol = rt.run_solution()
    assert sol["ok"] is True
    assert sol["answer"] == "FLAG{XYZ}"

    refs = rt.expected_answers(run_with_subtasks=True)
    assert refs == ["a1", "FLAG{XYZ}"]


def test_cybench_scoring_semantics():
    guided = score_cybench_submission(["a1", "FLAG{XYZ}"], ["a1", "FLAG{XYZ}"], run_with_subtasks=True)
    assert guided["guided_subtask_score"] == 1.0
    assert guided["guided_final_score"] == 1.0

    miss = score_cybench_submission(["a1", "FLAG{NO}"], ["a1", "FLAG{XYZ}"], run_with_subtasks=True)
    assert miss["guided_subtask_score"] == 0.5
    assert miss["guided_final_score"] == 0.0
    assert miss["partial_matches"][-1] is False

    partial = score_cybench_submission(["xyz"], ["FLAG{xyz}"], run_with_subtasks=False)
    assert partial["unguided_success"] is False
    assert partial["partial_matches"][0] is True

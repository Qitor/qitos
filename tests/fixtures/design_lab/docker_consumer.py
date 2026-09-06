"""Deterministic installed consumer with REAL Docker, never host code execution."""

from contextlib import ExitStack
from dataclasses import replace
from importlib import import_module
from importlib.resources import files
import json
from pathlib import Path
import sys
import tempfile

from qitos.config import (
    SessionConfig,
    TrajectoryConfig,
    build_agent_composition,
    load_agent_config,
)
from installed_consumer import Model


PROGRAMS = {
    "parser.py": "import csv\ndef parse(text):\n    rows=[]\n    for r in csv.DictReader(text.splitlines()):\n        rows.append((r['group'].strip(),float(r['value']),int(r['count'])))\n    return rows\n",
    "analysis.py": "def weighted_mean(rows):\n    count=sum(n for _,v,n in rows)\n    if count<=0: raise ValueError('empty weights')\n    return sum(v*n for _,v,n in rows)/count\n",
}
SKILL = "def normalize_rows(rows):\n    result=[]\n    for row in rows:\n        r={k:v.strip() if isinstance(v,str) else v for k,v in row.items()}\n        r['value']=float(r['value']); r['count']=int(r['count'])\n        if r['count']<0: raise ValueError('negative count')\n        result.append(r)\n    return result\n"
SKILLS = [
    SKILL,
    "def weighted_mean(rows):\n    if not rows or any(r['count']<0 for r in rows): raise ValueError('weights')\n    total=sum(r['count'] for r in rows)\n    if total<=0: raise ValueError('empty')\n    return sum(r['value']*r['count'] for r in rows)/total\n",
    "from normalize import normalize_rows\nfrom weighted import weighted_mean\ndef summarize(rows):\n    groups={}\n    for r in normalize_rows(rows): groups.setdefault(r['group'],[]).append(r)\n    return {k:weighted_mean(v) for k,v in groups.items()}\n",
]


def run(projects, suffix, root, *, recall=False, task_index=0):
    directory = {
        "pi": "pi_coding",
        "claude": "claude_coding",
        "voyager": "voyager_skills",
    }[suffix]
    package = "qitos_lab_" + suffix
    agent_module = import_module(package + ".agent")
    tasks = json.loads(files(package).joinpath("tasks.json").read_text())
    task = tasks[task_index]
    workspace = root / (("recall-input" if recall else "input") + str(task_index))
    workspace.mkdir()
    for name, body in task["inputs"].items():
        (workspace / name).write_text(body)
    config = load_agent_config(projects / directory / "agent.yaml")
    config = replace(
        config,
        runtime=replace(
            config.runtime,
            environment=replace(config.runtime.environment, workspace=str(workspace)),
            session=SessionConfig(
                store="sqlite",
                path=str(root / ("recall.sqlite3" if recall else "sessions.sqlite3")),
            ),
            trajectory=TrajectoryConfig(
                output=str(
                    root / ("recall.journal" if recall else "trajectory.journal")
                )
            ),
        ),
    )
    if suffix == "voyager":
        actions = [("read_file", {"path": "requirements.md"})]
        if task_index == 2:
            actions += [
                ("load_skill", {"name": name}) for name in ("normalize", "weighted")
            ]
        actions += (
            [("load_skill", {"name": task["skill"]})]
            if recall
            else [("write_file", {"path": "skill.py", "content": SKILLS[task_index]})]
        )
        actions += [
            ("verify_project", {}),
            ("publish_skill", {"description": "normalize data rows"}),
        ]
    else:
        actions = [("read_file", {"path": "AGENTS.md"})]
        actions += [
            ("write_file", {"path": path, "content": body})
            for path, body in PROGRAMS.items()
        ]
        actions += [("verify_project", {})]
    with ExitStack() as stack:
        factory = agent_module.build_factory(task, root=root)
        if hasattr(factory, "__enter__"):
            factory = stack.enter_context(factory)
        current = stack.enter_context(
            build_agent_composition(
                config, model_override=Model(actions), agent_factory=factory
            )
        )
        if suffix == "claude":
            from qitos_lab_claude.review import ReviewBoundary, independent_review

            current.runtime.lifecycle_policy = ReviewBoundary()
        session = current.session(task["task"])
        result = session.run()
        verified = [
            outcome
            for record in result.records
            for outcome in record.action_results
            if outcome.tool_name == "verify_project" and outcome.output.get("verified")
        ]
        assert verified, (suffix, result.state.stop_reason)
        assert all(
            outcome.status == "success"
            for record in result.records
            for outcome in record.action_results
        )
        if suffix == "claude":
            assert session.lifecycle.value == "paused"

            def reviewer():
                return Model(
                    [
                        ("read_file", {"path": "parser.py"}),
                        ("read_file", {"path": "analysis.py"}),
                        ("verify_project", {}),
                        (
                            "submit_review",
                            {"findings": [], "limitations": ["fixture checks only"]},
                        ),
                    ]
                )

            review = independent_review(
                current, session, task, None, model_factory=reviewer
            )
            assert review["child_sessions"] and review["outcomes"], review
            prior_records = tuple(result.records)
            current.runtime.lifecycle_policy.enabled = False
            result = session.run(steering=json.dumps(review["outcomes"]))
            verdict = import_module(package + ".evaluate").evaluate(
                result, task, prior_records=prior_records
            )
            assert verdict["passed"], verdict
        if suffix == "voyager":
            assert factory.library.get(task["skill"]).metadata["verified"] is True
            from qitos_lab_voyager.curriculum import next_objective

            assert next_objective(tasks, factory.library) == (
                task_index + 1 if task_index < 2 else None
            )
            if recall:
                assert task["skill"] in result.state.reused
            if task_index == 2:
                assert {"normalize", "weighted"} <= set(result.state.reused)
        # Source workspace is not the sandbox: edits are not automatically published.
        for name, body in task["inputs"].items():
            assert (workspace / name).read_text() == body
    return {"project": suffix, "docker": True, "recall": recall, "verified": True}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("projects", type=Path)
    parser.add_argument("suffixes", nargs="*", default=["pi", "claude", "voyager"])
    parser.add_argument("--root", type=Path)
    parser.add_argument("--recall", action="store_true")
    parser.add_argument("--task-index", type=int, choices=(0, 1, 2), default=0)
    args = parser.parse_args()
    projects = args.projects
    results = []
    for suffix in args.suffixes:
        if args.root:
            args.root.mkdir(parents=True, exist_ok=True)
            results.append(
                run(
                    projects,
                    suffix,
                    args.root,
                    recall=args.recall,
                    task_index=args.task_index,
                )
            )
            continue
        with tempfile.TemporaryDirectory(prefix="qitos-lab-docker-") as location:
            root = Path(location)
            results.append(run(projects, suffix, root))
            if suffix == "voyager":
                results.append(run(projects, suffix, root, recall=True))
    print(json.dumps(results))

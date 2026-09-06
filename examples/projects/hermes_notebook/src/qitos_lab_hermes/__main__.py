"""Explicit launch configuration; no credentials or model calls during validate."""

import argparse
from dataclasses import asdict, replace
from contextlib import ExitStack
from importlib.resources import files
import json
from pathlib import Path
import sys

from qitos.config import (
    BudgetConfig,
    LocalCredentialFileResolver,
    SessionConfig,
    TrajectoryConfig,
    build_agent_composition,
    load_agent_config,
)

from .agent import build_factory
from .evaluate import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "run", "resume", "inspect"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task", type=int, choices=[0, 1, 2], default=0)
    parser.add_argument("--session")
    parser.add_argument("--shared-root", type=Path)
    parser.add_argument("--phase", choices=["learn", "recall"], default="recall")
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--variant",
        choices=["default", "static", "no-memory", "no-skills"],
        default="default",
    )
    args = parser.parse_args()
    config = load_agent_config(args.config)
    tasks = json.loads(files(__package__).joinpath("tasks.json").read_text())
    task = tasks[args.task]
    if args.phase == "learn":
        task = dict(task, task=task.get("learning_task", task["task"]))
    elif "recall_inputs" in task:
        task = dict(task, inputs=task["recall_inputs"])
    if args.command == "validate":
        print(
            json.dumps(
                {"status": "configuration_valid", "tasks": len(tasks), "live": False}
            )
        )
        return 0
    root = args.root.resolve()
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        raise ValueError("run_root_must_be_outside_git")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.shared_root is not None:
        shared = args.shared_root.resolve()
        if any((parent / ".git").exists() for parent in (shared, *shared.parents)):
            raise ValueError("shared_root_must_be_outside_git")
    if args.command == "inspect":
        from qitos.qita.reader import candidate_file_reader

        reader = candidate_file_reader(root / "trajectory.journal")
        print(json.dumps({"runs": [asdict(run) for run in reader.discover_runs()]}))
        return 0
    if not args.live or args.credentials is None:
        raise ValueError("explicit_live_and_credentials_required")
    if args.model_config is not None:
        private = args.model_config.resolve()
        if any((parent / ".git").exists() for parent in private.parents):
            raise ValueError("model_config_must_be_outside_git")
        config = replace(config, model=load_agent_config(private).model)
    output_limit = max(10240, config.model.request.max_tokens or 0)
    request = replace(config.model.request, max_tokens=output_limit)
    config = replace(
        config, model=replace(config.model, request=request, max_tokens=output_limit)
    )
    workspace = root / "input"
    if args.command == "run":
        workspace.mkdir(exist_ok=False)
        for name, content in task["inputs"].items():
            target = workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
    config = replace(
        config,
        budgets=config.budgets
        or BudgetConfig(max_steps=80, max_requests=80, max_runtime_seconds=3600),
        runtime=replace(
            config.runtime,
            environment=replace(config.runtime.environment, workspace=str(workspace)),
            session=SessionConfig(store="sqlite", path=str(root / "sessions.sqlite3")),
            trajectory=TrajectoryConfig(output=str(root / "trajectory.journal")),
        ),
    )
    resolver = LocalCredentialFileResolver(args.credentials, repository_root=Path.cwd())
    with ExitStack() as stack:
        factory = stack.enter_context(
            build_factory(
                task, root=root, shared_root=args.shared_root, variant=args.variant
            )
        )
        composition = stack.enter_context(
            build_agent_composition(
                config, credential_resolver=resolver, agent_factory=factory
            )
        )
        session = (
            composition.restore(args.session)
            if args.command == "resume"
            else composition.session(task["task"])
        )
        (root / "session.json").write_text(
            json.dumps({"session_id": session.session_id.value})
        )
        result = session.run()

        def successful(name):
            return [
                outcome.output
                for record in result.records
                for outcome in record.action_results
                if outcome.tool_name == name and outcome.status == "success"
            ]

        verdict = evaluate(result, task)
        if args.phase == "learn":
            checks = {
                "final": str(result.state.stop_reason) == "final",
                "facts_persisted": bool(factory.memory.retrieve()),
                "procedure_persisted": bool(factory.skills.list_active()),
                "facts_written_this_session": bool(successful("remember_fact")),
                "procedure_written_this_session": bool(successful("save_procedure")),
                "sources_read": result.tool_calls_by_name.get("read_file", 0) >= 3,
            }
            verdict = {
                "passed": all(checks.values()),
                "checks": checks,
                "phase": "learn",
            }
        elif args.variant != "no-memory":
            checks = verdict["checks"]
            checks["memory_recalled"] = any(
                bool(value) for value in successful("search_memory")
            )
            checks["skill_loaded"] = bool(result.state.selected_skills)
            verdict["passed"] = all(checks.values())
        report = {
            "session_id": session.session_id.value,
            "run_id": result.run_id,
            "stop_reason": str(result.state.stop_reason),
            "evaluation": verdict,
            "tool_calls": result.tool_calls_by_name,
            "variant": args.variant,
        }
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2)
        )
        print(json.dumps(report, ensure_ascii=False))
        return 0 if verdict["passed"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Raw transport/factory errors can contain private endpoint details.
        print(
            json.dumps({"status": "failed", "error_type": type(error).__name__}),
            file=sys.stderr,
        )
        raise SystemExit(2) from None

"""Explicit launch configuration; no credentials or model calls during validate."""

import argparse
from dataclasses import asdict, replace
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
    factory = build_factory(task, root=root, variant=args.variant)
    with build_agent_composition(
        config, credential_resolver=resolver, agent_factory=factory
    ) as composition:
        session = (
            composition.restore(args.session)
            if args.command == "resume"
            else composition.session(task["task"])
        )
        (root / "session.json").write_text(
            json.dumps({"session_id": session.session_id.value})
        )
        result = session.run()
        verdict = evaluate(result, task)
        verdict["checks"]["plan_mechanism"] = (
            result.state.plan_version == 1
            if args.variant == "static"
            else result.state.plan_version >= 2
        )
        verdict["passed"] = all(verdict["checks"].values())
        report = {
            "session_id": session.session_id.value,
            "run_id": result.run_id,
            "stop_reason": str(result.state.stop_reason),
            "evaluation": verdict,
            "tool_calls": result.tool_calls_by_name,
            "variant": args.variant,
            "plan_version": result.state.plan_version,
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

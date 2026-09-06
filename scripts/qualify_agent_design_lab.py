"""Explicit opt-in real-model matrix. Raw configuration/evidence stays outside Git."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import shutil
import sys
import time

PROJECTS = {
    "react": "react_research",
    "planact": "planact_research",
    "pi": "pi_coding",
    "claude": "claude_coding",
    "hermes": "hermes_notebook",
    "voyager": "voyager_skills",
}


def private_path(value):
    value = Path(value).expanduser().resolve()
    if any((parent / ".git").exists() for parent in (value, *value.parents)):
        raise ValueError("private_configuration_or_evidence_inside_git")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects", type=Path, required=True)
    parser.add_argument("--model-config", type=private_path, required=True)
    parser.add_argument("--credentials", type=private_path, required=True)
    parser.add_argument("--root", type=private_path, required=True)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument(
        "--only", nargs="+", choices=list(PROJECTS), default=list(PROJECTS)
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--repetition-start", type=int, default=0)
    parser.add_argument("--ablation", action="store_true")
    args = parser.parse_args()
    if not args.execute_live:
        print(
            json.dumps({"status": "live_not_authorized", "planned_projects": args.only})
        )
        return 2
    if args.repetitions < 1 or args.repetition_start < 0:
        raise ValueError("invalid_repetition_count")
    args.root.mkdir(parents=True, exist_ok=False, mode=0o700)
    ledger = []
    package_identity = {}
    for name in ["qitos", *("qitos-lab-" + item for item in args.only)]:
        distribution = importlib.metadata.distribution(name)
        package_identity[name] = {
            str(path): hashlib.sha256(
                distribution.locate_file(path).read_bytes()
            ).hexdigest()
            for path in distribution.files or []
            if str(path).endswith((".py", "tasks.json"))
        }
    (args.root / "installed-source.json").write_text(
        json.dumps(package_identity, indent=2)
    )
    # Serial Docker admission deliberately avoids unbounded host resource pressure.
    for name in args.only:
        for repetition in range(
            args.repetition_start, args.repetition_start + args.repetitions
        ):
            for task in range(3):
                variants = ["default"]
                if args.ablation and name in {"planact", "hermes", "voyager"}:
                    variants += [
                        {
                            "planact": "static",
                            "hermes": "no-memory",
                            "voyager": "no-skills",
                        }[name]
                    ]
                for variant in variants:
                    phases = (
                        ["learn", "recall"]
                        if name in {"hermes", "voyager"} and variant == "default"
                        else ["recall"]
                    )
                    for phase in phases:
                        if (args.root / "STOP_AFTER_CURRENT").exists():
                            print(
                                json.dumps(
                                    {
                                        "status": "stopped_at_case_boundary",
                                        "attempts": len(ledger),
                                    }
                                )
                            )
                            return 2
                        identity = f"{name}-{repetition}-{task}-{variant}-{phase}"
                        root = args.root / identity
                        command = [
                            sys.executable,
                            "-m",
                            "qitos_lab_" + name,
                            "run",
                            "--config",
                            str(
                                args.projects.resolve() / PROJECTS[name] / "agent.yaml"
                            ),
                            "--model-config",
                            str(args.model_config),
                            "--credentials",
                            str(args.credentials),
                            "--root",
                            str(root),
                            "--task",
                            str(task),
                            "--variant",
                            variant,
                            "--live",
                        ]
                        if name in {"hermes", "voyager"}:
                            command += [
                                "--phase",
                                phase,
                                "--shared-root",
                                str(
                                    args.root
                                    / (
                                        f"{name}-{repetition}-default-shared"
                                        if variant == "default"
                                        else f"{name}-{repetition}-{variant}-shared-task{task}"
                                    )
                                ),
                            ]
                        started = time.monotonic()
                        with (args.root / (identity + ".log")).open("x") as output:
                            try:
                                result = subprocess.run(
                                    command,
                                    cwd=args.root,
                                    stdout=output,
                                    stderr=subprocess.STDOUT,
                                    timeout=3900,
                                )
                                code = result.returncode
                            except subprocess.TimeoutExpired:
                                code = 124
                        report_file = root / "report.json"
                        report = (
                            json.loads(report_file.read_text())
                            if report_file.exists()
                            else {}
                        )
                        if (
                            args.ablation
                            and phase == "learn"
                            and name in {"hermes", "voyager"}
                        ):
                            control = "no-memory" if name == "hermes" else "no-skills"
                            source = args.root / f"{name}-{repetition}-default-shared"
                            destination = (
                                args.root
                                / f"{name}-{repetition}-{control}-shared-task{task}"
                            )
                            if source.exists():
                                # Pin after connections close, before recall writes answers.
                                shutil.copytree(source, destination)
                        ledger.append(
                            {
                                "case": identity,
                                "exit_code": code,
                                "elapsed_seconds": time.monotonic() - started,
                                "report_present": bool(report),
                                "evaluation": report.get("evaluation"),
                                "stop_reason": report.get("stop_reason"),
                                "interventions": [],
                                "role": (
                                    "ablation"
                                    if variant != "default"
                                    else "qualification"
                                ),
                            }
                        )
                        (args.root / "ledger.json").write_text(
                            json.dumps(ledger, indent=2)
                        )
                        print(
                            json.dumps({"case": identity, "exit_code": code}),
                            flush=True,
                        )
    qualified = all(
        row["exit_code"] == 0 for row in ledger if row["role"] == "qualification"
    )
    print(
        json.dumps(
            {
                "status": "passed" if qualified else "not_qualified",
                "attempts": len(ledger),
            }
        )
    )
    return 0 if qualified else 2


if __name__ == "__main__":
    raise SystemExit(main())

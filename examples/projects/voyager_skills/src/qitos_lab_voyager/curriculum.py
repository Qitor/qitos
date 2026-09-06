"""A bounded mastery-driven curriculum; ordering is replaceable application policy."""

import argparse
from importlib.resources import files
import json
from pathlib import Path
import subprocess
import sys

from qitos.kit.tool.library.sqlite_store import SqliteToolLibrary


def next_objective(tasks, library):
    """Advance only past controller-verified persisted skills, not model claims."""
    for index, task in enumerate(tasks):
        skill = library.get(task["skill"])
        if (
            skill is None
            or not skill.active
            or skill.metadata.get("verified") is not True
        ):
            return index
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        raise ValueError("explicit_live_required")
    root = args.root.resolve()
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        raise ValueError("curriculum_root_must_be_outside_git")
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    shared = root / "skills"
    shared.mkdir()
    tasks = json.loads(files(__package__).joinpath("tasks.json").read_text())
    with SqliteToolLibrary(
        shared / "skills.sqlite3", namespace="data-programming"
    ) as library:
        for attempt in range(len(tasks)):
            index = next_objective(tasks, library)
            if index is None:
                break
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "qitos_lab_voyager",
                    "run",
                    "--config",
                    str(args.config.resolve()),
                    "--model-config",
                    str(args.model_config.resolve()),
                    "--credentials",
                    str(args.credentials.resolve()),
                    "--root",
                    str(root / f"objective-{attempt}"),
                    "--shared-root",
                    str(shared),
                    "--task",
                    str(index),
                    "--phase",
                    "learn",
                    "--live",
                ],
                timeout=3900,
            )
            if result.returncode:
                print(
                    json.dumps(
                        {
                            "status": "objective_unmastered",
                            "objective": tasks[index]["id"],
                        }
                    )
                )
                return 2
        complete = next_objective(tasks, library) is None
        print(
            json.dumps(
                {
                    "status": (
                        "curriculum_complete" if complete else "curriculum_incomplete"
                    ),
                    "skills": library.catalog(),
                }
            )
        )
        return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())

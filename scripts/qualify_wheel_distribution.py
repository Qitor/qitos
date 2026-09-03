#!/usr/bin/env python3
"""Install a built wheel into fresh environments and run offline smokes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import venv
from pathlib import Path
from typing import Any, Dict, Sequence


PROFILE_IMPORTS = {
    "base": ("qitos", "qitos.tracing.trajectory", "qitos.evaluate"),
    "openai": ("qitos.models.openai", "openai"),
    "anthropic": ("qitos.models.anthropic",),
    "gemini": ("qitos.models.gemini",),
    "litellm": ("qitos.models.litellm", "litellm"),
    "local": ("qitos.models.local", "openai"),
    "models": ("qitos.models.openai", "qitos.models.litellm"),
    "qita": ("qitos.qita",),
    "docker": ("qitos.kit.env.sandbox",),
    "mcp": ("qitos.mcp", "httpx"),
    "evaluation": ("qitos.evaluate", "qitos.metric"),
    "yaml": ("yaml",),
    "benchmarks": ("datasets", "huggingface_hub"),
    "wandb": ("qitos.tracing.wandb_processor", "wandb"),
    "mlflow": ("qitos.tracing.mlflow_processor", "mlflow"),
    "cookiecutter": ("cookiecutter",),
    "hf": ("huggingface_hub",),
    "web": ("playwright",),
    "dev": ("build", "twine", "pytest", "black", "flake8", "mypy"),
    "all": (
        "openai",
        "litellm",
        "yaml",
        "datasets",
        "huggingface_hub",
        "wandb",
        "mlflow",
        "cookiecutter",
        "httpx",
    ),
}


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=600,
    )


def qualify_profile(
    wheel: Path,
    profile: str,
    *,
    coding_consumer: Path,
    research_consumer: Path,
    config_fixture: Path,
) -> Dict[str, Any]:
    if profile not in PROFILE_IMPORTS:
        return {"profile": profile, "status": "unsupported_profile"}
    with tempfile.TemporaryDirectory(prefix=f"qitos-wheel-{profile}-") as temp:
        root = Path(temp)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = environment / "bin" / "python"
        bin_dir = environment / "bin"
        requirement = str(wheel) if profile == "base" else f"{wheel}[{profile}]"
        install = _run(
            [
                str(python),
                "-m",
                "pip",
                "--disable-pip-version-check",
                "install",
                requirement,
            ],
            cwd=root,
        )
        if install.returncode:
            return {
                "profile": profile,
                "status": "install_failed",
                "returncode": install.returncode,
            }
        imports = ";".join(f"import {name}" for name in PROFILE_IMPORTS[profile])
        imported = _run([str(python), "-c", imports], cwd=root)
        if imported.returncode:
            return {
                "profile": profile,
                "status": "import_failed",
                "returncode": imported.returncode,
            }
        checks = ["imports"]
        if profile == "base":
            for source in (coding_consumer, research_consumer):
                content = source.read_text(encoding="utf-8")
                if "qitos._" in content or "tests." in content:
                    return {"profile": profile, "status": "private_import_rejected"}
                shutil.copy2(source, root / source.name)
            copied_config = root / "agent.yaml"
            shutil.copy2(config_fixture, copied_config)
            commands = (
                [str(bin_dir / "qit"), "--help"],
                [str(bin_dir / "qita"), "--help"],
                [
                    str(python),
                    "-c",
                    "from qitos.config import load_agent_config; "
                    "c=load_agent_config('agent.yaml'); assert c.name",
                ],
                [str(python), str(root / coding_consumer.name)],
                [str(python), str(root / research_consumer.name)],
            )
            names = (
                "qit_help",
                "qita_help",
                "canonical_config_load",
                "coding_consumer",
                "research_consumer",
            )
            for name, command in zip(names, commands):
                completed = _run(command, cwd=root)
                if completed.returncode:
                    return {
                        "profile": profile,
                        "status": f"{name}_failed",
                        "returncode": completed.returncode,
                    }
                checks.append(name)
        return {"profile": profile, "status": "passed", "checks": checks}


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=list(PROFILE_IMPORTS),
        choices=sorted(PROFILE_IMPORTS),
    )
    parser.add_argument("--coding-consumer", required=True, type=Path)
    parser.add_argument("--research-consumer", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    results = [
        qualify_profile(
            args.wheel.resolve(),
            profile,
            coding_consumer=args.coding_consumer.resolve(),
            research_consumer=args.research_consumer.resolve(),
            config_fixture=args.config.resolve(),
        )
        for profile in args.profiles
    ]
    status = "passed" if all(item["status"] == "passed" for item in results) else "failed"
    print(
        json.dumps(
            {
                "schema_version": "qitos.s4.lane_d.wheel_qualification/1",
                "status": status,
                "results": results,
                "publication_ready": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

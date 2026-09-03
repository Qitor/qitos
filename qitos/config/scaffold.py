"""Wheel-safe generator for the canonical beginner Agent project."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Mapping

from .errors import ConfigurationError


_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def create_agent_project(
    output_dir: str | Path,
    *,
    agent_name: str,
    description: str,
    author: str,
    default_model: str,
    max_steps: int,
) -> Path:
    """Create a self-contained, installable Session-first starter project."""
    if not _NAME.fullmatch(agent_name):
        raise ConfigurationError(
            "agent name must be a lowercase Python identifier",
            field="agent_name",
        )
    root = Path(output_dir).expanduser().resolve() / agent_name
    if root.exists():
        raise ConfigurationError(
            "target agent project already exists", field="output_dir"
        )
    files = _project_files(
        agent_name=agent_name,
        description=description,
        author=author,
        default_model=default_model,
        max_steps=max_steps,
    )
    created: list[Path] = []
    try:
        for relative, content in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            created.append(target)
    except Exception:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        for directory in sorted(
            {target.parent for target in created}, key=lambda item: len(item.parts), reverse=True
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
    return root


def _project_files(
    *,
    agent_name: str,
    description: str,
    author: str,
    default_model: str,
    max_steps: int,
) -> Mapping[str, str]:
    pyproject = f'''[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "{agent_name.replace('_', '-')}"
version = "0.1.0"
description = {json.dumps(description)}
authors = [{{name = {json.dumps(author)}}}]
requires-python = ">=3.10"
dependencies = ["qitos"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
'''
    config = f'''schema: qitos.agent
agent:
  name: {agent_name}
  protocol: react_text_v1
  parser: auto
  seed: 0
model:
  provider: openai_compatible
  model: {default_model}
  credential:
    ref: {agent_name}-provider
  api_mode: chat_completions
  request:
    temperature: 0.0
    max_tokens: 2048
    timeout_seconds: 180
    retries: 0
    extra_body: {{}}
tools:
  preset: env_coding
  include: []
  options: {{}}
  policy: auto
runtime:
  environment:
    type: docker
    image: python:3.12-slim
    workspace: .
    container_workspace: /workspace
    network: none
    read_only_root: true
    cap_drop: true
    no_new_privileges: true
    pids_limit: 256
    memory_mb: 2048
    cpus: 2.0
    cleanup_required: true
  session:
    mode: durable
    store: sqlite
    path: ./.qitos/sessions.sqlite3
  trajectory:
    enabled: true
    output: ./.qitos/trajectory.json
    privacy: private
    failure_policy: required
budgets:
  max_steps: {int(max_steps)}
  max_runtime_seconds: 600
  max_requests: 12
context: {{}}
memory: {{}}
compaction: {{}}
lifecycle:
  policy: cooperative
failure_policy:
  provider: typed
  tools: fail_closed
metadata:
  starter: qitos-session-first
dataset:
  - task: Inspect the workspace and report one verified fact.
'''
    app = '''"""Session-first programmatic entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qitos.config import CredentialResolver, build_agent_composition, load_agent_config


def build(
    config_path: str | Path = "agent.yaml",
    *,
    credential_resolver: CredentialResolver,
    model_override: Any = None,
    env_override: Any = None,
):
    config = load_agent_config(config_path)
    return build_agent_composition(
        config,
        credential_resolver=credential_resolver,
        model_override=model_override,
        env_override=env_override,
    )


def run(task: str, *, credential_resolver: CredentialResolver):
    with build(credential_resolver=credential_resolver) as composition:
        session = composition.session(task)
        return session.run()
'''
    fake = '''"""Deterministic provider double used by the starter tests."""

from __future__ import annotations

from typing import Any


class DeterministicFakeModel:
    model = "deterministic-fake"
    qitos_protocol = "react_text_v1"

    def call_raw(self, messages: object, **options: Any) -> dict[str, Any]:
        _ = messages, options
        return {"choices": [{"message": {"content": "Final Answer: fake-ok"}}]}
'''
    test = f'''from dataclasses import replace
from pathlib import Path

from qitos.config import EnvironmentConfig, FakeCredentialResolver, load_agent_config
from qitos.config import build_agent_composition

from {agent_name}.fake_provider import DeterministicFakeModel


def test_generated_agent_uses_the_session_path(tmp_path: Path) -> None:
    config = load_agent_config(Path(__file__).parents[1] / "agent.yaml")
    config = replace(
        config,
        runtime=replace(
            config.runtime,
            environment=EnvironmentConfig(
                type="unsafe_host",
                image="",
                workspace=str(tmp_path),
                container_workspace="",
                network="host",
                read_only_root=False,
                cap_drop=False,
                no_new_privileges=False,
                pids_limit=None,
                memory_mb=None,
                cpus=None,
                cleanup_required=False,
            ),
            session=replace(
                config.runtime.session,
                path=str(tmp_path / "sessions.sqlite3"),
            ),
            trajectory=replace(
                config.runtime.trajectory,
                output=str(tmp_path / "trajectory.json"),
            ),
        ),
    )
    with build_agent_composition(
        config,
        credential_resolver=FakeCredentialResolver(
            {{"{agent_name}-provider": "not-a-real-secret"}}
        ),
        model_override=DeterministicFakeModel(),
    ) as composition:
        session = composition.session("finish through Session")
        result = session.run()
        assert result.state.final_result == "fake-ok"
        assert session.current_head.checkpoint_id.value.startswith("checkpoint_")
        assert composition.runtime.launch_metadata["config_digest"] == config.digest()
'''
    readme = f'''# {agent_name}

{description}

Copy `credentials.example.yaml` to a private credential file, then run:

```bash
qit run --config agent.yaml --credentials /path/to/credentials.yaml
```

The default uses a durable SQLite Session, private Trajectory output, and an
attested Docker sandbox. Tests use a deterministic fake model and explicit
`unsafe_host` test workspace; they never call a real provider.
'''
    return {
        "pyproject.toml": pyproject,
        "README.md": readme,
        "agent.yaml": config,
        "credentials.example.yaml": f"{agent_name}-provider: replace-me\n",
        f"src/{agent_name}/__init__.py": "",
        f"src/{agent_name}/app.py": app,
        f"src/{agent_name}/fake_provider.py": fake,
        "tests/test_agent.py": test,
    }


__all__ = ["create_agent_project"]

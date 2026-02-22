# Env & Ops Capabilities

## Goal

Understand how QitOS decouples tool intent from the execution backend.

## Mental model

- Tools declare required ops groups (e.g. `file`, `process`).
- `Env` provides concrete ops implementations for those groups.

This allows the same tool to run on host, docker, or a repo sandbox.

## Why ops groups exist

If a tool needs to read/write files, you do not want it to directly call `open(...)` everywhere.
Instead, tools declare intent (what they need) and Env provides the backend (how it is executed).

That is what makes it realistic to support:

- `HostEnv` for local development
- `DockerEnv` for sandboxed execution
- future remote/sim environments (VMs, k8s, browser sandboxes)

## Example: file tool that works on host or docker

```python
from qitos import tool

@tool(name="read_text", required_ops=["file"])
def read_text(path: str, file_ops) -> str:
    # Engine injects file_ops when Env provides "file" ops group.
    return file_ops.read_text(path)
```

If you run the same agent with `HostEnv`, `file_ops` points to host filesystem operations.
If you run it with `DockerEnv`, `file_ops` maps to container filesystem operations.

## Preflight behavior

If tools require ops but no env is provided, Engine stops early with `ENV_CAPABILITY_MISMATCH`.

## Source Index

- [qitos/core/env.py](https://github.com/Qitor/qitos/blob/main/qitos/core/env.py)
- [qitos/kit/env/host_env.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/env/host_env.py)
- [qitos/kit/env/docker_env.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/env/docker_env.py)
- [tests/test_env_host_and_engine_interpretation.py](https://github.com/Qitor/qitos/blob/main/tests/test_env_host_and_engine_interpretation.py)

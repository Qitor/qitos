# Tools & Env

## Goal

Build portable agents where action intent is stable but execution backend can change.

## Mental model

- **Tool**: semantic operation (`read_file`, `replace_lines`, `run_command`, `fetch_url`).
- **Env**: execution backend implementing capability ops (`file`, `process`, etc.).

## Tutorial: one tool, multiple env backends

1. Define/register a tool requiring ops group `file`.
2. Run with `HostEnv`.
3. Run with `DockerEnv` (same tool, different backend).
4. Verify behavior parity via trace.

## Practical rules

1. Keep tool inputs/outputs structured and explicit.
2. Fail early on missing required ops.
3. Never hide backend assumptions inside parser or prompts.
4. Keep side effects localized to env ops layer.

## Troubleshooting

1. `ENV_CAPABILITY_MISMATCH`:
- tool required ops are missing in current env.

2. action succeeds in host but fails in docker:
- path mapping or workspace root mismatch.

3. command tool unstable:
- tighten timeout and sanitize command template.

## Source Index

- [qitos/core/tool.py](https://github.com/Qitor/qitos/blob/main/qitos/core/tool.py)
- [qitos/core/env.py](https://github.com/Qitor/qitos/blob/main/qitos/core/env.py)
- [qitos/engine/action_executor.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/action_executor.py)
- [qitos/kit/env/host_env.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/env/host_env.py)
- [qitos/kit/env/docker_env.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/env/docker_env.py)
- [qitos/kit/tool/editor.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/tool/editor.py)

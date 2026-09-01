# S3 G4 live qualification evidence

Status: configuration blocked before the first provider request
Updated: 2026-09-01
Owner: G4 live-qualification owner
Fixed source: `7b89dbcca97be5dfd9562276578353900af4e02d`
Qualification runner commit: `e3a4b86ad10496f1e6ee98b4cfb92fffafd58c59`

## Scope and plan

This record is the execution plan and evidence ledger for the bounded G4-L
qualification. It reuses the public OpenAI-compatible model adapter and the
existing Session, WorkGraph, ToolResult, ExchangeLog, Env, trace, and candidate
Trajectory surfaces. It does not add Task 14 runtime contracts, change provider
defaults, freeze Trajectory, or make qita a mutation authority.

The execution order is fixed:

1. verify source, worktree, and remote identity;
2. parse the three profiles from `s3_g4_live_model_matrix.md`;
3. require explicit profiles and `--live`, then resolve only their named
   credential references;
4. fail before sandbox provisioning or a model request when configuration is
   blocked;
5. otherwise attest one task-exclusive sandbox before preflight;
6. run bounded native-tool preflight, then only qualified agent workflows;
7. keep provider payloads outside the repository and commit only the redacted
   summary; and
8. promote only if every live, sandbox, deterministic, repository, packaging,
   privacy, and remote-identity gate passes.

## Runner contract

`scripts/qualify_s3_live.py` is opt-in and has no default live mode. It reads
endpoint, model, credential reference, and request override from the registered
Markdown table. The fixed policy is 12 requests per profile, 10,240 output
tokens per request, a 180-second timeout, and zero automatic retries. Native
capability checks inspect only the provider `tool_calls` field; JSON or promises
inside assistant text never count. A private evidence directory is required to
be outside the repository before a configured live route may run.

## Current credential-reference outcome

All three allowed named variables were absent in the runner environment:

| Profile | Credential reference | Outcome | Requests |
|---|---|---|---:|
| `sii-dsv4-flash` | `env:QITOS_LIVE_DSV4_API_KEY` | `configuration_blocked:credential_missing` | 0 |
| `sii-glm-5-2` | `env:QITOS_LIVE_GLM52_API_KEY` | `configuration_blocked:credential_missing` | 0 |
| `sii-qwen3-8-27b` | `env:QITOS_LIVE_QWEN38_API_KEY` | `configuration_blocked:credential_missing` | 0 |

No other environment variable, history, process, configuration directory, or
chat record was searched. No provider request, automatic retry, sandbox, agent
workflow, live trajectory, token usage, or billable operation occurred.

The authoritative invocation was:

```bash
python scripts/qualify_s3_live.py --live \
  --profile sii-dsv4-flash \
  --profile sii-glm-5-2 \
  --profile sii-qwen3-8-27b \
  --source-commit e3a4b86ad10496f1e6ee98b4cfb92fffafd58c59 \
  --generated-at 2026-09-01T00:52:03+00:00 --json
```

It exited `2`. The committed JSON records matrix digest
`7a085b28757e32c1293c25f0c4e5f679aaffc52e15bd25c7d9f126c11d431660`
and runner digest
`e0f6fcc6bf573113ac9e0ec2e14d585fd81085e924620de95fc7892861941dcd`.

## Gate disposition

Because there is no complete tool-capable live route, the single-agent and
multi-agent/process-restore workflows are blocked and no sandbox resource was
created. This is not an unavailable skip and does not qualify any capability.
The deterministic candidate remains separately qualified, while promotion,
push, and worktree retirement remain prohibited.

Raw/private evidence policy remains unchanged: live provider payloads and
hidden reasoning, if a later authorized configured run occurs, must be written
only to the explicit external private directory. Git may contain only profile
IDs, endpoint/request digests, exact model strings, counts, reported usage,
latency, typed outcomes, sanitized facts, and the private evidence digest.

## Offline and repository validation

The fixed Python 3.12.7 environment produced these results after the blocked
receipt and documentation were present:

- `pytest -q tests/e2e/test_s3_g4_multi_agent_process_loss.py` — exit 0,
  `2 passed in 36.79s`, covering twenty graph process-loss and twenty
  declaration/preparation-crash rounds;
- provider/codec, Session/WorkGraph, clean-process restore, tracing/qita, and
  receipt-reader matrix — exit 0, `246 passed in 4.38s`;
- DockerEnv plus blocked-attestation tests — exit 0, `9 passed in 0.30s`;
- live receipt, no-local-path, architecture, and public-surface matrix — exit
  0, `17 passed in 1.45s`;
- `python scripts/static_quality.py check` — exit 0, 369 baselined findings
  (347 active and 22 vendored/generated);
- stable `flake8 qitos/core qitos/engine qitos/models qitos/trace` — exit 0;
- stable `mypy qitos/core qitos/engine qitos/models qitos/trace` — exit 0,
  success on 93 source files;
- full `pytest -q` — exit 0, `2356 passed, 50 skipped in 93.83s`;
- `python -m build` — exit 0, built `qitos-0.6.0.tar.gz` and
  `qitos-0.6.0-py3-none-any.whl`;
- `python -m twine check` on both artifacts — exit 0, both passed;
- full-tree secret ratchet — exit 0, 22 unchanged intentional adversarial
  test/fixture matches, zero new and zero stale findings; and
- `git diff --check` — exit 0.

The first static-ratchet invocation used the default Python 3.13 environment
and exited 1 because that interpreter could not resolve the installed flake8
package metadata. It was not treated as evidence or masked. The complete
ratchet and subsequent gates ran in the repository's fixed Python 3.12.7
quality environment; its host-local interpreter path is intentionally absent
from committed evidence.

The DockerEnv tests above are offline contract tests, not a substitute for a
real live container attestation. Because the credential gate fired first, no
task container existed and cleanup is correctly
`not_applicable_no_resource_created`.

Current status variables:

```text
S3_STATUS=blocked_live_qualification
G4_LIVE=configuration_blocked
S4_READY=false
FEATURE_BASELINE_PROMOTED=false
DEFAULT_BRANCH_READY=false
FINAL_STATUS=BLOCKED
```

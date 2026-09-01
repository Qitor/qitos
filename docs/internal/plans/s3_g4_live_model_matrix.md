# S3 G4 live-model matrix

Status: budget accepted; all three credential references missing at execution;
live qualification blocked before the first request
Updated: 2026-09-01
Owner: G4 live-qualification owner
Candidate source: `7b89dbcca97be5dfd9562276578353900af4e02d`
Qualification runner commit: `e3a4b86ad10496f1e6ee98b4cfb92fffafd58c59`

## Purpose

This matrix authorizes three OpenAI-compatible routes for bounded S3 live
protocol checks, trajectory collection, and disposable agent runs. It does not
change provider defaults, persist credentials, freeze Trajectory, or qualify the
candidate before executable receipts exist. Framework code must select a profile
explicitly rather than hard-code one of these routes into core or engine.

## 2026-09-01 execution outcome

The maintainer accepted the exact 12-request, 10,240-output-token, 180-second,
zero-automatic-retry policy below. The bounded runner then resolved only the
three registered credential references. All three were missing, so every
profile returned `configuration_blocked:credential_missing` before sandbox
provisioning or the first model request. Request, reported-token, latency, and
retry totals are all zero. No profile has a measured native tool capability,
and no single-agent, multi-agent, restore, sandbox, or live Trajectory scenario
ran.

The committed redacted receipt is
[`s3_g4_live_qualification_summary.json`](s3_g4_live_qualification_summary.json),
with the execution narrative and raw/private storage policy in
[`s3_g4_live_qualification_evidence.md`](s3_g4_live_qualification_evidence.md).
This is a typed failure outcome, not an unavailable skip. It sets
`S3_STATUS=blocked_live_qualification`, prohibits promotion/push/worktree
retirement, and leaves every capability cell unqualified.

## Registered profiles

| Profile | Chat-completions endpoint | Model | Credential reference | Request override | Intended use |
|---|---|---|---|---|---|
| `sii-dsv4-flash` | `https://d8cj8amkhbkccckmh5g9cpdh5ogm8cpk.openapi-sj.sii.edu.cn/v1/chat/completions` | `dsv4-flash-0731` | `env:QITOS_LIVE_DSV4_API_KEY` | `chat_template_kwargs.thinking=true` | reasoning/continuation preflight, trajectory and agent candidate |
| `sii-glm-5-2` | `https://hgbemok5dkq8cp8bjaebba89mkkkpjb8.openapi-sj.sii.edu.cn/v1/chat/completions` | `GLM-5.2-w4a8c8` | `env:QITOS_LIVE_GLM52_API_KEY` | `chat_template_kwargs.enable_thinking=false` | non-thinking protocol comparison, trajectory and agent candidate |
| `sii-qwen3-8-27b` | `https://cqhbod8bjjjbcoakk8pmeebgkaq9akcq.openapi-sj.sii.edu.cn/v1/chat/completions` | `Qwen3.8-27B` | `env:QITOS_LIVE_QWEN38_API_KEY` | `chat_template_kwargs.enable_thinking=false` | non-thinking protocol comparison, trajectory and agent candidate |

Credential values were supplied outside repository state. They must never be
copied into this file, a fixture, command argument, snapshot, trajectory, test
report, or Git commit. Separate environment names avoid reusing and overwriting
one credential variable across endpoints.

## Capability preflight

Run the same bounded preflight for all profiles before assigning a route to an
agent scenario:

1. basic response and typed provider failure;
2. one declared function tool and structurally valid `tool_calls` output;
3. parallel tool-call request with three independent safe tools;
4. assistant tool-call/result continuation with provider-scoped call IDs;
5. profile-specific thinking option and reasoning/continuation observation;
6. malformed tool result, timeout, and capability-loss reporting;
7. secret scan of private and redacted records.

Tool calling, parallel calls, reasoning preservation, and continuation support
are observed capabilities, not assumptions derived from the model name. A route
may remain usable for compatible trajectory tasks while being unqualified for a
tool or continuation scenario.

## Trajectory and agent selection

- A trajectory collection or agent run accepts one explicit profile ID above.
- Preflight all three and collect at least one sanitized trajectory from every
  responsive route.
- Run the full durable-agent matrix on each route that proves the required tool
  and continuation capabilities.
- Require at least one fully qualified tool-capable route for S3 live closure;
  two independent routes are preferred default-branch evidence.
- Never silently fall back between profiles. A fallback must emit a typed receipt
  naming requested/actual profiles and declared loss.
- Persist only profile ID, endpoint digest, exact model string, request-policy
  digest, codec report, usage, latency, outcome, and redacted trajectory facts.

Live scenarios cover basic chat, single/parallel tools, reasoning or declared
loss, steering, pause/process-exit/restore, delegate, fan-out/join, handoff,
permission denial, timeout/`outcome_unknown`, and one disposable-repository
coding-agent task. Direct and model-callable paths must produce the same graph
facts.

Agent work runs only in a new disposable Git repository. Allowed tools are
repository-scoped read, grep, edit, and bounded shell/test commands. Production
repositories, deployment, remote-server mutation, account mutation, and
unrestricted network tools are out of scope. Model network access is restricted
to the selected endpoint. The disposable repository must be exposed through the
Task 14 `research_coding` sandbox contract, or through the equivalent current
CyberGym-derived task-exclusive Docker harness until that contract lands. It
must fail closed rather than fall back to the primary checkout or `HostEnv`.

## Budget and execution gate

Accepted fixed bounds for this qualification:

- `QITOS_LIVE_MAX_REQUESTS_PER_PROFILE=12`
- `QITOS_LIVE_MAX_OUTPUT_TOKENS_PER_REQUEST=10240`
- `QITOS_LIVE_TIMEOUT_SECONDS=180`
- one disposable agent task per qualified profile
- no automatic retry after a billed or ambiguous request

The 10,240 value is a per-response output ceiling suitable for multi-step agent
work, not the total Session context or token budget. The runner also enforces a
separate bounded per-profile request count, total reported input/output usage,
wall-clock deadline, and explicit stop policy; it records actual provider usage
rather than assuming every response consumes the ceiling.

Record actual request count, reported input/output tokens, latency, failure
class, and provider retries. Unknown pricing must not become a fabricated cost
claim. The budget is accepted, but the credential gate produced three typed
configuration blockers and no executable model receipt. Promotion, push,
cleanup, and default-branch readiness remain blocked.

## Secret handling

- Load credentials into the three endpoint-specific environment variables only
  in the live runner process.
- Do not use `set -x`, print environment variables, put Authorization headers in
  command-line arguments, or commit `.env` files.
- Raw payloads and private trajectories stay outside the repository; committed
  evidence contains redacted projections and digests only.
- Scan code, diffs, evidence, and generated artifacts before a local commit.
- Rotate supplied credentials after qualification because they were shared via
  an interactive channel.

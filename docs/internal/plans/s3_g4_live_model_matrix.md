# S3 G4 live-model matrix

Status: profiles configured locally; credentials remain external; budget approval
and execution pending
Updated: 2026-09-01
Owner: G4 live-qualification owner
Candidate: `a278fa2a86a9976f89e29a6c9dac4fd9c7ec90f9`

## Purpose

This matrix authorizes three OpenAI-compatible routes for bounded S3 live
protocol checks, trajectory collection, and disposable agent runs. It does not
change provider defaults, persist credentials, freeze Trajectory, or qualify the
candidate before executable receipts exist. Framework code must select a profile
explicitly rather than hard-code one of these routes into core or engine.

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
to the selected endpoint.

## Budget and execution gate

Suggested safe defaults, requiring explicit maintainer acceptance before any
network request:

- `QITOS_LIVE_MAX_REQUESTS_PER_PROFILE=12`
- `QITOS_LIVE_MAX_TOKENS_PER_REQUEST=4096`
- `QITOS_LIVE_TIMEOUT_SECONDS=180`
- one disposable agent task per qualified profile
- no automatic retry after a billed or ambiguous request

Record actual request count, reported input/output tokens, latency, failure
class, and provider retries. Unknown pricing must not become a fabricated cost
claim. Until the budget is accepted and executable receipts exist, status is
`profiles_configured_execution_pending`; promotion, push, cleanup, and
default-branch readiness remain blocked.

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

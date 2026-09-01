# S3 G4 live-model matrix

Status: provider preflight complete; live Agent workflows failed and are frozen
Updated: 2026-09-01
Owner: G4 live-qualification owner
Candidate source: to be bound by the G4-L2 implementation commit
Qualification runner: `scripts/qualify_s3_live.py` (byte digest in receipt)

## Purpose

This matrix authorizes three OpenAI-compatible routes for bounded S3 live
protocol checks, trajectory collection, and disposable agent runs. It does not
change provider defaults, persist credentials, freeze Trajectory, or qualify the
candidate before executable receipts exist. Framework code must select a profile
explicitly rather than hard-code one of these routes into core or engine.

## 2026-09-01 G4-L2 outcome

The exact 12-request, 10,240-output-token, 180-second,
zero-automatic-retry policy remains fixed. The execution authority is no longer
this Markdown table: three strict private `qitos.agent/v1` files under
`<user-config-dir>` hold provider/model/request/Env/Session/Trajectory desired
state, and a hardened local resolver supplies each logical credential at the
composition boundary. All launch files and refs validated without disclosing a
value, and all sixteen offline gates passed with zero provider requests.

The committed redacted preflight receipt is
[`s3_g4_live_qualification_summary.json`](s3_g4_live_qualification_summary.json),
with the execution narrative and raw/private storage policy in
[`s3_g4_live_qualification_evidence.md`](s3_g4_live_qualification_evidence.md).
The separate sanitized
[`workflow failure receipt`](s3_g4_live_workflow_failure_receipt.json) binds the
subsequent restore attempts and private Session-store digests. DSV4 and GLM
passed native single/parallel/continuation preflight; Qwen produced typed
`capability_loss`. Full Agent execution nevertheless failed, and GLM reached 13
observed requests against its 12-request cap. Execution is frozen; promotion,
push, and worktree retirement are prohibited.

| Profile | Text | Single native tool | Three parallel tools | Continuation | Final typed outcome |
|---|---:|---:|---:|---:|---|
| `sii-dsv4-flash` | pass | pass | pass | pass | `workflow_failure` |
| `sii-glm-5-2` | pass | pass | pass | pass | `workflow_failure` + request-budget violation |
| `sii-qwen3-8-27b` | pass | loss | loss | loss | `capability_loss` |

## Registered profiles

| Profile | Chat-completions endpoint | Model | Credential reference | Request override | Intended use |
|---|---|---|---|---|---|
| `sii-dsv4-flash` | private launch config | `dsv4-flash-0731` | `sii-dsv4` | `chat_template_kwargs.thinking=true` | reasoning/continuation preflight, trajectory and agent candidate |
| `sii-glm-5-2` | private launch config | `GLM-5.2-w4a8c8` | `sii-glm-5-2` | `chat_template_kwargs.enable_thinking=false` | non-thinking protocol comparison, trajectory and agent candidate |
| `sii-qwen3-8-27b` | private launch config | `Qwen3.8-27B` | `sii-qwen3-8-27b` | `chat_template_kwargs.enable_thinking=false` | non-thinking protocol comparison, trajectory and agent candidate |

Credential values remain outside repository state. They must never be copied
into this file, a fixture, command argument, snapshot, trajectory, test report,
or Git commit. The committed summary stores only configuration and
credential-reference digests; endpoints remain in the private launch sources.

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

- `budgets.max_requests=12`
- `model.request.max_tokens=10240`
- `model.request.timeout_seconds=180`
- `model.request.retries=0`
- one disposable agent task per qualified profile
- no automatic retry after a billed or ambiguous request

The 10,240 value is a per-response output ceiling suitable for multi-step agent
work, not the total Session context or token budget. The runner also enforces a
separate bounded per-profile request count, total reported input/output usage,
wall-clock deadline, and explicit stop policy; it records actual provider usage
rather than assuming every response consumes the ceiling.

Record actual request count, reported input/output tokens, latency, failure
class, and provider retries. Unknown pricing must not become a fabricated cost
claim. The budget is accepted and validated offline. Promotion, push, cleanup,
and default-branch readiness remain blocked until all three live typed outcomes
and the required workflows pass.

## Secret handling

- Resolve only the three explicit logical references through the hardened local
  private-file resolver. Environment lookup is compatibility-only and is not
  used by this qualification.
- Do not use `set -x`, print environment variables, put Authorization headers in
  command-line arguments, or commit `.env` files.
- Raw payloads and private trajectories stay outside the repository; committed
  evidence contains redacted projections and digests only.
- Scan code, diffs, evidence, and generated artifacts before a local commit.
- Rotate supplied credentials after qualification because they were shared via
  an interactive channel.

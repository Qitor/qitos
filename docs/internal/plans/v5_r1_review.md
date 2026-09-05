# V5 R1 current-source review

Date: 2026-09-05. Outcome: planning and dispatch preparation, not implementation.

Historical pre-dispatch audit. The four candidates are now delivered; current
source review and residual findings live in the
[implementation review](v5_r1_integration_review.md). Do not use this page's
pre-dispatch status or old probes as the current candidate qualification.

## Source identities and remote evidence

- Local working checkout: master at `60809b3be388d22ea40ea41b4aaa1f5540c76fda`.
- Remote/tracking master: `4dfb570fb7eef504c1e6d247c21a1984251b80e4`, verified with `git ls-remote`; local checkout is five commits behind and retains the uncommitted V5 planning draft.
- Remote-only changes are docs, examples, docs tests/scripts and workflow. `git diff --exit-code HEAD origin/master -- qitos quality ...` confirmed no changes in runtime, fixed quality toolchain or the targeted test files used below.
- The exact remote HEAD's [CI](https://github.com/WhitzardAgent/WhitzardOS/actions/runs/33888812388), [docs](https://github.com/WhitzardAgent/WhitzardOS/actions/runs/33888812389), and [Code Quality](https://github.com/WhitzardAgent/WhitzardOS/actions/runs/33888810896) runs are completed/success. CI includes tests for Python 3.10/3.11/3.12, coverage, package, architecture, dependency audit, stable lint/type and full-package ratchet, all successful. This is observed run status, not a claim about branch-protection settings or a new release.
- No fetch/checkout/merge/commit/push was performed in this review. The existing main and docs-learning worktrees were preserved.

## What is already fixed

Consume, do not redispatch: descriptor-based Python 3.10 publication hashing;
exact historical-source portability; verified-content journal parsing reuse;
complete source-bound EN/zh tutorials, installed-page tests and API reference.
The default Trajectory, sync durable Session and local durable WorkGraph remain
existing mechanisms, not candidate schemas awaiting another freeze.

The tutorial PR added no runtime changes. Its fake providers qualify mechanisms,
not autonomous live-model success. Previous G5 counts remain historical.

## Current residual findings

| Finding | Evidence in this review | R1 decision |
|---|---|---|
| Streaming infrastructure failure becomes normal content | Patched only the real OpenAI adapter's SDK client constructor to throw synthetic ConnectionError. Actual result: ModelResponse, text `Error: synthetic transport unavailable`, finish_reason `stop`; delta received that text. No network/credential read. | A: fail with typed provider outcome, test real adapters and partial-stream lifecycle. |
| Old Read double pagination | Calling `CodingToolSet.Read.func` with offset 2/limit 2 and an already paginated two-line backend response returns empty string. | C: actual-file regression and compatibility fix. |
| Edit loses replace_all | Calling real alias with true forwarded action/new_text/old_text/path/runtime_context only. | C: real replacement and permission-preserving fix. |
| Observation has two mutable truths | After attribute task changes from before to after, attribute/to_dict return after but mapping returns before. | C: one authoritative state with tested mapping compatibility. |
| Functional retry is inert | TaskFunction(max_retries=3, timeout_s=0.001) invoked an always-failing function once. | Confirmed open, deferred to the next bounded 03B package; not solved by this R1. |
| Memory extension exists without complete builtin lifecycle | MemorySource is contribute; old memory is retrieve. Markdown constructor does not reload written records. | B: generic adapter, Memdir two-process reference, honest Markdown run-scoped boundary. |
| Context examples are mechanisms, not ready long-task policies | Existing CompactionPolicy/default rejecting policy; current kit lacks the requested complete builtin closed-exchange window adapter. | B: deterministic opt-in implementation; model summary/migration remain later. |
| Handoff source callback can race destination restore | Latest tutorial implementation plan describes the reproduction. Source review confirms source-owned Session CAS in `_commit_work_graph` and terminal mutation/persist in WorkRuntime; destination may acquire the same head first. | C first priority. This review did not execute the two-process race; the implementation must establish a failing reproducer before changing semantics. |
| Journal still does full-byte integrity work and full derived-index rebuild | `_load` hashes every byte even on parsed-cache hit; `_write_index` serializes rebuilt positions; materializing readers hold all records. | D: optimize index/read allocations; retain strict byte integrity. |

The five direct Python probes are diagnostic counterexamples, not new permanent
tests and not proof that an entire module is broken. No source file was changed
to run them. The handoff finding is explicitly source corroboration of an earlier
reproduction, not a newly claimed execution result.

## Planning corrections

1. Replace stale audit/CI pending source with one exact green remote baseline.
2. Prioritize a live public runtime ownership defect over broad func/benchmark
   cleanup. C's Session lease is narrowly a handoff bugfix; no new daemon/approval.
3. Do not require suffix-only reads while also requiring every operation to detect
   arbitrary in-place changes to mutable historical bytes. Preserve the strict
   default; additional immutable-segment/trust/migration design is a later item.
4. Do not mistake a Markdown log writer for a replayable Memory store. R1 scope
   names the supported cross-process reference and leaves missing replay open.
5. Four independently runnable packages, no producer-receipt waiting cycle. Each
   package ships an installed public consumer; one final combined consumer binds
   the mechanisms. Live/configuration qualification remains separate.
6. V5 docs are still local task inputs. Dispatch explains how same-machine coding
   agents read them without attempting to find them in the runtime baseline.

## Verification and limitations

- Python 3.12.7 and all five pinned quality tool metadata versions verified.
- Journal durability, ratchet tests, architecture/public surface and privacy:
  **39 passed in 4.34 seconds**.
- Models, S4 context/extensions, func API, old coding toolset and WorkRuntime:
  **130 passed in 3.34 seconds**.
- Both groups ran in local 60809b3 with documentation-only dirt; runtime and these
  tests match the remote baseline. They are not a clean-worktree full-suite claim.
- The existing tests pass while targeted probes expose untested behavior; this is
  why simply repeating the historical full-suite count is insufficient.
- Public docs validation and diff whitespace check passed during preparation.
- Final privacy/architecture/public/workflow suite: **19 passed in 1.80 seconds**.
  All 13 planning files and 51 local links checked; four lanes bind the same exact
  SHA. Static ratchet against that SHA passed with 356 allowances unchanged
  (334 active, 22 vendored/generated). See the planning execution record.
- No full local pytest, Docker, live model, browser rendering, wheel build or
  benchmark was run by this review; remote CI results are cited separately.

## Dispatch result

See [common execution contract](v5_dispatch.md) and the four linked lane files.
No coding agent was launched by this task. Four prepared instructions authorize
implementation only when the user hands each to its executor; they do not
authorize remote mutations, model calls without configuration, or cleanup.

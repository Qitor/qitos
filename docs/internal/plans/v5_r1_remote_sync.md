# V5 R1 Python compatibility and remote synchronization

Current R1 status authority. Updated 2026-09-06; remote synchronization is in progress, not yet verified.

## Starting facts and scope

- Local integration already completed and accepted as clean master at
  `d17a6ab4f6b09b0dd8a9c8896f859d26de17f3ec`.
- Historical complete R1 execution source:
  `55c356f9d0f6b0df431ac1427f2373dfd5e540fa` (3715 passed, 51 opt-in skips).
  The five original findings are fixed; their [execution record](v5_r1_integration_execution.md)
  and [source/replay map](v5_r1_integration_evidence/replay.json) remain historical evidence.
- Starting tracking and live remote master both read back as
  `4dfb570fb7eef504c1e6d247c21a1984251b80e4`, an ancestor of local master (37 commits ahead).
- Main is clean; other repository tasks are inactive. Work is isolated on
  `codex/v5-r1-remote-sync`, in the sibling `WhitzardOS-v5-r1-remote-sync` worktree.
- This task authorizes commits, isolated dependency installation, local fast-forward
  and direct non-forced master push. No live model, server 149, release, tag,
  deployment, protection changes, history rewriting or unrelated worktree changes.

## Execution plan

1. Reproduce the Python 3.10 cleanup regression on real built-in adapters with SDK I/O substitutes.
2. Repair current-exception discovery and retain numeric cleanup diagnostics on Python 3.10.
3. Run real Python 3.10.18 and pinned Python 3.12.7 lifecycle/provider regressions;
   commit the implementation before binding public API/tutorial references to its SHA.
4. Reconcile current documentation, retain historical source identities and migration facts;
   generate EN/zh API/tutorial pages against the actual current source environment.
5. Audit every outgoing commit and evidence blob for public suitability without printing secrets.
6. Qualify full pytest, final-wheel installed consumers, fixed static toolchain/budgets,
   packaging, docs/link/MDX and desktop/mobile rendering.
7. Commit and fast-forward clean master; revalidate promotion; fetch/check ancestry,
   non-forced push, read back local/tracking/live SHA and divergence; inspect exact-SHA CI.
8. Record actual synchronization facts in a documentation successor if needed; verify
   that successor's docs/CI. Remove only this task's clean, idle worktree non-forcibly,
   retaining its branch ref.

## Compatibility finding

New after R1 local acceptance: `_stream.py` calls `sys.exception()` and
`BaseException.add_note()`, which do not exist in Python 3.10 although package and
CI support it. The independent review reproduced AttributeError and zero owned
cleanup calls in both call_raw and stream transport on Python 3.10.18.
This task will record its own before/after execution below.

## Documentation decisions and limits

R1 local integration and its five repairs are complete; V5 overall remains in progress.
This page is the current status entry. Earlier plans/reviews keep historical failures
and dates, explicitly superseded for current execution/authorization status.
README focuses on capabilities, installation and usage. Public source links will use
an actual reachable implementation commit; original lane audit/performance/replay
identities are never globally replaced. Memdir creation requires `create=True`;
Read/Edit direct calls return `ToolResult` (check status, then output); old WorkGraph
readers must upgrade for `dispatch_not_started`. D's performance numbers belong to
`df9316415db7ec76f1e5d70a11ceabfd47744169` and are not remeasured here.

LIVE_MODEL_QUALIFICATION=not_run; RELEASE_PERFORMED=no; DEPLOY_PERFORMED=no.

## Python compatibility execution

Task-owned Python 3.10.18 reproduced **46 failures** in the cleanup repair file
before the implementation change (3.01 s). The repaired source passes **112 tests**
across stream repairs/lifecycle/provider matrix, SDK retry budget, worker lifecycle
and configured request accounting (5.81 s). No regression is skipped for 3.10.

`sys.exc_info()[1]` replaces the unsupported API. Python 3.10 retains the same
safe numeric note in `__notes__`; nonstream owned client cleanup also receives the
model so that provider and already-observed usage survive normal-close failures.
ProviderFailure's existing safe replacement/normalization contract remains intact;
callback and cancellation objects remain identical at the adapter boundary.

The initial repaired 3.10 run exposed a test assumption about CPython Task, not
lost cleanup: 3.10 creates an outer CancelledError and chains the exact adapter
exception in `__context__`; 3.11+ delivers it directly. The regression now asserts
original SDK-to-adapter identity, both cleanup attempts, exact notes, task cancelled
state, and each interpreter's exact outer identity/context relationship. No skip,
looser diagnostic assertion, asyncio patch or cancellation conversion is used.

A broader 3.10 model run reached 191 passed / 1 existing opt-in skip but the
combined consumer fixture's nested stdlib ensurepip process aborted in the downloaded
macOS interpreter. This environment failure is not a passing consumer receipt.
The final wheel will be installed with the task's isolated venv tooling and consumed
via the test's existing QITOS_R1_INSTALLED_PYTHON entry point.

Implementation fix and public API/tutorial runtime source:
`f7d4b2d666a156d361da496a41868278f84ffabf`.
Python 3.10.18 expanded model/provider plus installed original/combined consumers:
**193 passed, zero skipped, 16.06 s** using an independently installed wheel.
The earlier ensurepip abort was avoided by normal task-owned uv venv creation;
no repository test or skip rule was changed to bypass it.

Public documentation now pins the integrated implementation for installation,
all API groups (including B/D overrides) and tutorial runtime overrides. The
API generator rejects unreachable commits, changed source bytes, and imports
from an outdated installation. Both former lane references fail its negative
check; a reachable but stale implementation also fails. Docs CI fetches complete
history to make the same ancestry check meaningful. Original audit/performance
identities remain intact. EN/zh generated APIs and complete tutorials synchronize.

Initial outgoing-history audit: 37 commits, 376 distinct file/blob versions,
including intermediate logs; largest inspected blob 185,140 bytes. Gitleaks's one
finding at commit `82290e5ce994d714cae6e43bffefbaba79defddc`,
`docs/internal/plans/v5_r1_b_execution.md:12`, is the exact 40-character production
source commit, not a credential. Supplementary literal/URL/path review found
synthetic redaction fixtures, placeholder keys, public provider/documentation URLs,
loopback addresses and noncredential historical build paths. No real secret,
private model profile/payload, credential file, wheel, environment, cache or large
temporary artifact was identified. `docs/internal` was treated as public.
Final outgoing range will be rescanned after the last planned commits.

## Qualification progress and portability repair

At `c51f46023eca9190ce6f6adf6df3801e5a206d53`, Python 3.12.7 targeted repairs pass
**141/141**; stable flake8/mypy pass (96 source files); static ratchet stays
**356 = 334 active + 22 vendored/generated**, allowance delta zero. Architecture,
public surface, G2/S2 interface budgets and no-local-path checks pass **16/16**.

The first full run required installing CI's setuptools/wheel build tools in the
fresh Python 3.12 environment. The subsequent complete run was **3724 passed,
51 skipped, 1 failed in 366.64 s**. The sole failure was API generation parity:
Python 3.10 AST renders a zero-argument lambda as `lambda :`; 3.12 renders
`lambda:`. Two context reference pages therefore drifted. The generator now
normalizes only the token gap between an argumentless lambda and its colon,
without rewriting strings/default values. New portability and source-binding
negative regressions plus the original docs contract test pass **7/7 on each
of Python 3.10.18 and 3.12.7**. The full suite will be rerun on this successor.
No framework/runtime implementation changed after `f7d4b2d`.

Both final artifacts build in an empty task-owned output directory and pass twine.
All 510 wheel Python files equal the current checkout. Final-wheel original and
combined installed consumers pass on 3.12.7 (2 tests, 8.72 s) and 3.10.18; all
processes run outside the checkout without source PYTHONPATH. Artifact digests
and final source execution identity will be recorded with completed qualification.

MDX compiles 166/166 pages. Navigation, local links, EN/zh API/tutorial generation
and complete-file parity pass. Desktop/mobile checks cover all 38 changed MDX
pages at 1440×1000 and 390×844: 76 HTTP 200 pages, populated headings, zero page
horizontal overflow, and visual screenshot review. Browser reports zero errors;
only the local preview Socket.io version warning is present. All 127 unique API
source links bind the implementation SHA. The ten tutorial example links now also
pin that same source instead of moving master; their labels/layout are unchanged.

## Completed pre-push qualification

Full execution source: `2cba812e4103ac27240b96c7b3552d062cca0ef0`.
**3731 passed, 51 skipped in 358.51 s**; [complete result](v5_r1_remote_sync_evidence/full-pytest.txt).
The 51 skips are unchanged: 50 live opt-ins and one explicit Docker docs gate.
Ordinary sandbox tests were not disabled or expanded into a new stress matrix.

[Environment, source identities and artifact SHA256](v5_r1_remote_sync_evidence/validation.json)
records the exact fixed toolchain, final build and 510-file source equality.
The full source suite used a source-equivalent wheel; a final clean rebuild from
this execution source was then installed independently on both interpreters.
Original and combined consumers from that final wheel pass on 3.10.18 (2/2,
8.74 s) and 3.12.7 (2/2, 8.72 s), including normal, truncated/dual-cleanup failure,
namespace and loss-rejection phases. No source PYTHONPATH was supplied.

[Python 3.10 expanded result](v5_r1_remote_sync_evidence/python310.txt),
[3.12 repair result](v5_r1_remote_sync_evidence/target312.txt),
[ratchet](v5_r1_remote_sync_evidence/quality.txt),
[docs](v5_r1_remote_sync_evidence/docs.txt), and
[76 page/viewport checks](v5_r1_remote_sync_evidence/browser.json) retain bounded
public receipts. Context pages were rechecked after lambda normalization with no
overflow or stale rendering; all tutorial links match committed example bytes.
Stable lint/type, directed generator/regression lint, interface budgets, navigation,
MDX, 132 Markdown links and git diff whitespace all pass. There is no package
metadata, runtime dependency, Python floor, root export or allowance growth.

Outgoing audit through this execution source covers **40 commits / 461 unique
file/blob versions**. The only Gitleaks match remains the reviewed source-SHA
false positive. New receipts contain public test outcomes, source digests and page
layout facts only. Local main was rechecked clean at its fixed starting SHA;
other tasks remain inactive. Formal promotion, push, readback and exact-SHA CI
are the next authorized actions, not yet claimed as performed here.

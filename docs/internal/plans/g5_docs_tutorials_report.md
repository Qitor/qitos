# G5 documentation and developer experience report

## 1. Outcome

Local documentation/tutorial checks passed. Promotion, push and worktree
retirement are held for historical local-path disclosure review. No model
requests, private credentials, server 149, release or deployment operations.

## 2. Source identities

G5 qualified runtime and docs branch start:
`717b4cf1b23f2ed252cd03234ffd8605038d9567`.
Tested documentation content:
`478dd73783414f363f857b643370603112c1158a`.
The later evidence-only commit does not inherit a new runtime qualification.
Historical G5 2663 passed / 50 skipped belongs only to 717b4cf, Python 3.12.7.

## 3. Scope and frozen runtime

Updated public EN/zh pages, navigation, examples, docs tests/CI, contributor
instructions, architecture descriptions, inventory and E2E plan. Byte comparison
verified 526 selected runtime/metadata/interface files unchanged; additional
Git diff proof covers all qitos/, quality/, packaging metadata, public-surface
fixtures, architecture allowlist and public-surface tests. No API, dependency,
package-version, permission, sandbox, loss or persistence changes.

## 4. Current state

Progress, v4 Tasks 12–16, migration, README and CHANGELOG distinguish current
G5-passed/local-integration-complete from historical candidate failures. Original
failure history and 29 source/replay identities remain preserved. Remote sync is
not performed; default branch and release have no readiness claim.

## 5. Beginner path

Exact-source installation → qit new → canonical model/tool/resource config →
AgentComposition Session → result/artifact/Trajectory → recovery/extension.
The fake arithmetic path uses only a trusted pure function, real SQLite and
real Session/reader operations. It claims neither model intelligence nor host
isolation. Real-provider config uses CredentialRef and an explicit resolver;
loading is tested without model requests. Published PyPI is clearly separated
from unreleased G5, local wheel and contributor editable installation.

## 6. Eight learning units

Custom State/AgentModule/stop; registered parallel tools; Session pause/restore/
steering/fork; context/memory/selector/compactor; Docker/artifacts/publication;
durable child work/join and operation distinctions; Trajectory/qita; structural
extensions. Each core page has goals, prerequisites, complete file binding,
commands, assertions, errors, limits and next steps. The five complete tutorial
files use only installed public paths; no repository tests/private Engine fields.

## 7. Bilingual navigation

148 public MDX pages; identical EN/zh route order and page parity. Core units
precede advanced/reference and historical/compatibility content. Multi-agent,
MLflow and benchmark routes are discoverable in both languages. Five earlier
Chinese-only supplementary topics now have aligned English content. Terminology
and contributor instructions are QitOS-specific. Inventory: g5_docs_inventory.md.

## 8. Executable qualification

Exact requested ten-file pytest command: **506 passed in 51.40 seconds**, no
skips, on tested content 478dd73. Earlier 520-case check preceded removal of
unpaired outdated illustrative examples, not suppression of failed runnable cases.

The golden tests build a wheel from frozen runtime source, verify every qitos
Python byte against that wheel, install it into a fresh outside-repository venv,
copy only public lessons, and execute help, scaffold install/tests, canonical
config load, Session create/inspect/fork/restore/steering, default qita inspection,
HTML/JSON export and extension examples. No editable install or source PYTHONPATH.
Earlier independent execution also used the original G5 archive wheel.

Final real Docker lesson executes both retained-only and explicit-publication
modes against task-private fixtures, with real Env tools, large-output digest
resolution, source invariance, selected-file publication and container absence.
The fake provider is labelled; no live model is contacted. Python 3.12.7,
flake8 7.0.0; changed examples/tests/docs validator static checks pass.
Required-test stdout SHA256:
`42672d129a5a1bd73944b00a9bb2e88d226bf585e13108a0b6e0cb08a7612001`.

## 9. Site validation

Task-isolated Mintlify 4.2.873, MDX 3.1.1, Playwright CLI 0.1.19, local Node
23.11.0. Mint build validation and broken-links pass. Independent validator
checks public routes, bilingual ordering, local links/anchors and imported
symbols; MDX compilation passes all 148 pages. Fourteen required EN/zh pages
actually rendered with HTTP 200 and correct headings at 1440×1000 and 390×844;
no mobile horizontal overflow. Desktop/mobile screenshots visually reviewed.
No browser console errors; local preview search requires login and was not enabled.
Repository-only .md engineering records are explicitly excluded from site
publication, retained in Git and identified as such in inventory.

## 10. Compatibility, unsupported and migration

Preserved AgentModule.run, direct Engine, historical trace and wire identifiers.
Explicit limits cover process-local Memory, ephemeral non-restorability,
credential/Docker-free inspect, unsupported live CLI pause/steer and unresolved
approval restore, immutable fork, steering versus permission, timeout versus hard
cancellation, no unknown-effect replay, no cleanup publication, restricted
publication/platforms, read-only qita, full journal loading and lossy public export.

Authoring found supported workarounds without runtime edits: correct the
scaffold credential example root; register publication against the restored Env;
allocate explicit per-sibling request grants; create an empty run-ID selector
directory for G5 CLI replay/export while reading the authoritative parent journal.

## 11. Whole outgoing history privacy check

Remote f07b386 through tested 478dd73: **82 commits / 696 distinct changed blobs**.
Twenty-six pattern hits were reviewed by exact file/blob. Key/endpoint markers
are explicit synthetic rejection/redaction tests. Actual machine paths remain in
five historical file families listed in g5_docs_tutorials_promotion.md, including
producer/worktree evidence. No original values are echoed here.

Adding a successor cannot remove their historical blobs. The user's prohibition
on public local paths conflicts with the prohibition on rewriting history.
Therefore push is held; this is not an automatic approval-system rejection.
No blanket fixture allowlist or history rewriting was used.

## 12. Functional E2E plan

post_g5_functional_e2e.md defines eight real-user workflows, fixtures, actions,
independent assertions, call/token/time/tool ceilings, cleanup and five failure
classes. The first priority is native tool execution followed by codec loss
rejection; no pre-planned disabling of loss checks. Planned, not run.

## 13. Commits and local promotion

Content commits: `82a00021d1828d0530efc163a54b45ca41b22634`,
`478dd73783414f363f857b643370603112c1158a`; evidence recorded in a later
small documentation commit. Main remains exactly 717b4cf. No fast-forward yet,
so there is no promoted new SHA to misrepresent as qualified remotely.

## 14. Remote state

No push. Feature main local: 717b4cf; tracking and ls-remote:
`f07b38647cf3b18a5235581224a1153b88fac397`.
At tested docs content divergence was 0 remote-only / 82 local-only commits.
No divergence conflict was found; privacy review is the hold. G5 runtime
reachability on the remote feature branch is not yet established.

## 15. GitHub checks

No checks for the unpushed documentation commits were run or read from GitHub.
Local checks are not described as GitHub checks. Docs CI retains existing gates
and adds deterministic links/MDX/snippet/installed tutorial checks without live
credentials or Docker requirements in ordinary docs CI.

## 16. Worktrees and refs

Task start: six registered worktrees. Docs worktree creation: seven. Retired: zero.
All seven were checked clean; all original branches/HEADs remain intact. No refs,
tags, qualification archive, user data or foreign Docker resources were deleted.
Released space: zero. Retirement remains conditional on a verified remote push.

## 17. Known gaps

Historical local-path disclosure must be resolved before promotion/push/retirement.
G5 scaffold credential example and qita CLI selector-directory requirements remain
runtime DX follow-ups with documented working paths. Handoff and real-provider
end-to-end task completion are planned, not newly executed. No full G5 rerun,
20-profile packaging rerun, Linux-host publication or universal Python/provider
compatibility claim. Documentation site deployment is not performed.

## 18. Clean status

All seven worktrees were clean before this evidence-only update. The docs
worktree will be committed and checked again; the primary remains unchanged.
No hidden qualification logs or generated media enter Git; the external task
archive preserves raw local logs and screenshots, separate from the G5 archive.

## 19. Next dispatch identity

**No E2E dispatch baseline is authorized yet.** Use exactly the final
local/tracking/ls-remote-equal SHA after privacy resolution, fast-forward,
normal feature-branch push and verification. Never substitute 478dd73 or a moving
branch for that not-yet-established remote identity.

```text
G5_FRAMEWORK_QUALIFICATION=passed
DOCS_TUTORIALS_LOCAL_CHECKS=passed
REMOTE_SYNC=blocked_historical_local_paths
FUNCTIONAL_E2E=planned_not_run
DEFAULT_BRANCH_CHANGED=false
PACKAGE_PUBLISHED=false
```

# G5 documentation and developer experience report

## 1. Outcome

Documentation/tutorial qualification passed locally and in GitHub docs CI.
The user accepted the reviewed historical-path disclosure and explicitly selected
master as the default development branch. Ordinary pushes and remote identity
verification completed; six historical worktrees were safely retired. Full remote
CI is not yet qualified: remaining failures are visible and recorded below.
No model requests, private credential reads, server 149, releases or deployments
were performed in this documentation/promotion task.

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
failure history and 29 source/replay identities remain preserved. Remote sync
is verified; master is now the default branch by subsequent user instruction.
No full-CI, release or deployment readiness is inferred from branch promotion.

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

The original outgoing feature range through 73ec7d9 contained 83 commits and
699 distinct changed blobs. Through the CI preparation commit eb3fe2f it contained
84 commits and 707 distinct changed blobs. Twenty-six pattern matches were
reviewed by exact file/blob. Key/endpoint markers are explicit synthetic rejection
and redaction tests. The five real historical local-path file families are listed
in g5_docs_tutorials_promotion.md; the user explicitly accepted their push after
review. Original values are not repeated here. No blanket fixture exemption or
history rewrite was used. The subsequent CI fix commit scan had no matches;
each later outgoing successor is scanned before its ordinary push.

## 12. Functional E2E plan

post_g5_functional_e2e.md defines eight real-user workflows, fixtures, operations,
independent assertions, call/token/time/tool ceilings, cleanup and five failure
classes. The first priority remains native tool execution followed by codec loss
rejection; no disabling of loss checks is planned. Planned, not run. Resolve or
explicitly account for the known remote CI blockers before selecting test profiles.

## 13. Commits and local promotion

Docs content commits: 82a00021d1828d0530efc163a54b45ca41b22634 and
478dd73783414f363f857b643370603112c1158a; initial evidence: 73ec7d92256f2ca60929f628afcc5c9a2ba29128.
Primary feature fast-forward: 717b4cf → 73ec7d9, followed by 506 passed in
50.58 seconds on the primary checkout. CI preparation: eb3fe2f5013470f5423b7bf467fd33521a8885e4;
runner/fixture fixes: 5b1c448b06a6bcb789a2bfe0941f93227b5be007.
Later receipt/context/link changes are separate successors, not new G5 runtime
qualification. No qitos runtime or package metadata changed.

## 14. Remote state

The original remote feature head f07b38647cf3b18a5235581224a1153b88fac397
advanced by ordinary push. Master was created on the same qualified lineage.
Both local/tracking/ls-remote identities were verified equal at
5b1c448b06a6bcb789a2bfe0941f93227b5be007, with divergence 0/0.
GitHub default and origin/HEAD were changed to master, as later explicitly
requested. Main remains at 37758042622983bbffb6a0f2d860e13cdea98c2a with its ref
preserved. No dev branch, force push, rebase, tag push or ruleset change occurred.
The G5 runtime SHA is an ancestor of the verified remote master. Final evidence
successors receive a fresh remote readback outside this self-containing report.

## 15. Actual GitHub checks and CI/CD

GitHub docs runs 33876249889 (eb3fe2f) and 33877514659 (5b1c448) passed.
CI run 33876250029 failed: runner tools, Docker fixtures, shallow history,
annotation context, and real compatibility/evidence issues were exposed.
On 5b1c448, run 33877514721 passed type-stable, audit, package, lint-stable and
architecture jobs. The matrix/coverage and ratchet are not declared successful.
The ratchet failure identifies missing Playwright annotation context, now added
as an isolated CI typing input; the quality baseline remains unchanged.

Workflows cover master, retained main, the feature branch and PRs, with read-only
tokens, 30-minute jobs, superseded-run cancellation, and retained test/build
artifacts. Full history, setuptools, asyncio support and real owned Docker fixture
builds are explicit. No row, coverage floor, audit or failure was removed/masked.
The package publishing workflow remains manual/release-only and was not invoked.
The existing repository ruleset was read: disabled; main was unprotected.
No ruleset or branch-protection settings were modified. CI failure visibility
does not itself enforce a required-check branch protection policy.

## 16. Worktrees, retained data and refs

Start: six worktrees; after docs creation: seven; after safe retirement: one.
Removed only the six user-listed registered paths with git worktree remove,
without force. Exact branch/HEAD, clean status, completed/idle tasks, no open files,
G5 archive digest and all 29 source/replay pairs were verified. All six branch
HEADs remain unchanged. Before removal, 547 non-cache ignored files (17,417,987
bytes), including retained run data, were copied outside Git and hash-verified.
The original G5 archive was untouched.

Removed tree allocation: 3,462,564 KiB (about 3.30 GiB). Observed filesystem free
space increased by 3,647,004,672 bytes; concurrent unrelated disk activity means
this delta is not an exact attribution. External retirement-result.json records
the per-tree source identities and measurements. No branch/tag/ref was deleted.

## 17. Known gaps

Remote CI cannot yet be called stable. Python 3.10 publication raises
AttributeError because qitos/kit/env/_publication.py uses hashlib.file_digest
(introduced in 3.11). Fixing it requires changing frozen runtime code; the failure
is retained and documented, with no matrix removal or xfail. Some historical
source-bound tests depend on original S4 source commits not published with the
replayed integration history. Full checkout history cannot manufacture those
objects; local source refs and source/replay evidence are preserved for resolution.

The G5 scaffold credential example and qita CLI selector-directory requirement
remain documented runtime DX follow-ups. Handoff and real-provider E2E are not
newly executed. No universal Python/provider/platform compatibility is claimed.
The optional local rebuild of the new CI image failed apt repository signature
validation; the GitHub runners built that Dockerfile successfully. No package
release or documentation site deployment was performed.

## 18. Clean status

After retirement the primary is the only registered worktree, on master.
Each promotion is committed and checked clean before push; the final readback
receipt records the final SHA and clean status. Qualification logs, screenshots,
retained ignored data and retirement measurements remain in the external task
archive. No original G5 source-bound archive or user data was deleted.

## 19. Next dispatch identity

Use only the final local/tracking/ls-remote-equal master SHA recorded by the final
remote readback and task response. This report is part of its own evidence
successor, so it deliberately does not invent a self-referential commit hash.
Do not substitute a moving branch, historical runtime SHA, or earlier CI attempt.
Functional E2E remains planned and must acknowledge the open CI blockers.

```text
G5_FRAMEWORK_QUALIFICATION=passed
DOCS_TUTORIALS_QUALIFICATION=passed
REMOTE_SYNC=verified
CI_QUALIFICATION=not_passed
FUNCTIONAL_E2E=planned_not_run
DEFAULT_BRANCH=master
DEFAULT_BRANCH_CHANGED=true
PACKAGE_PUBLISHED=false
```

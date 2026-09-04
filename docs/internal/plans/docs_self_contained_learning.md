# Self-contained learning and API reference

Start/runtime source: `60809b3be388d22ea40ea41b4aaa1f5540c76fda`.
Historical G5 qualification remains bound to `717b4cf1b23f2ed252cd03234ffd8605038d9567`.

## Accepted design

One synthetic notes project, independently runnable chapters, bilingual prose,
complete visible files, source-synchronized snippets, core API reference plus
extension index. Keep Mintlify and existing URLs. No runtime or package changes.

## Execution

1. Create notes fixtures and the source-to-MDX contract/checker; execute extracted files.
2. Rewrite Quickstart/custom Agent/tools/Session and core reference.
3. Complete context, sandbox, multi-agent, qita, extensions and EN/zh navigation.
4. Run installed-wheel tutorial gates, Docker, MDX/link checks and browser review;
   open PR, read exact-head checks, merge only when green, verify deployed content.

## Acceptance

Every chapter runs from page-extracted files outside the checkout with a wheel.
The generated project is used in Quickstart. No hidden teaching helper or source
PYTHONPATH. Public symbols have checked imports/signatures and reference anchors.
No real model requests. Browser rendering and deployment are separate gates.

## Progress

- Isolated worktree created from the accepted baseline; concurrent V5 drafts retained.
- Implementation and local qualification complete; see docs_self_contained_qualification.md.
- PR checks and live publication are the remaining promotion gates.

## Discovered boundary: handoff callback versus destination restore

At frozen source 60809b3, dispatching the destination's restore/run of the SAME
Session inside LocalWorkScheduler's handoff callback can advance the Session
owner before the source terminal callback persists. The source then raises
CheckpointConflictError("This run no longer owns the session head") at
session_runtime._commit_work_graph -> sqlite_store._validate_session_cas;
source wait can remain dispatched until the teaching deadline.

Reproduction: paused SQLite notes Session -> local scheduler resolver launches
`handoff.py --destination <parent_session_id>` immediately from its callable ->
destination restores/runs -> source completion callback attempts its old-owner CAS.
This is an ownership/interop limitation, not model intelligence or codec relaxation.
The runnable lesson explicitly serializes transfer acknowledgement, source
cleanup, and destination restore. It never labels admission as destination task
completion; a separate subprocess assertion proves destination execution.
Runtime was not changed. Concurrent same-head handoff scheduling needs a separate
framework investigation; do not claim this lesson qualifies that behavior.

## Documentation design sources

- https://docs.pytorch.org/tutorials/beginner/basics/quickstart_tutorial.html:
  task progression, adjacent code/results and complete source.
- https://docs.pytorch.org/docs/2.14/generated/torch.nn.Module.html:
  symbol signatures, arguments, examples and source links.
- https://fastapi.tiangolo.com/tutorial/first-steps/: complete named files,
  startup commands and user-visible verification.
- https://docs.sqlalchemy.org/en/20/tutorial/: unified learning sequence with
  explicit relationships between high-level composition and lower-level APIs.

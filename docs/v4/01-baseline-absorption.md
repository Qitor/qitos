# Task 01 — campaign absorption and trustworthy baseline

Status: complete
Completed: 2026-08-29 on `feat/campaign-absorption`
Depends on: nothing
Unblocks: Tasks 02 and 03

---

## 1. Outcome

The domain-neutral campaign mechanisms have either landed, been matched to a
mainline equivalent, or received an explicit later-task disposition. The branch
now has a deterministic test signal and green stable-surface lint/type gates.
Task 01 is closed by capabilities and tests, not by reproducing source commit
ancestry.

## 2. Capability ledger

| Area | Final disposition | Evidence |
|---|---|---|
| Multi-action isolation and ordering | Landed; blocked siblings do not cancel executable actions, results retain source order | `tests/test_engine_core_flow.py`, `tests/engine/test_concurrent_execution.py` |
| Runtime errors and loop control | Landed with neutral error paths, recover events, last-error reporting, and configurable repeated-call detection | engine error and loop tests |
| Reasoning/provider extras | Landed as compatibility fields on `ModelResponse`; richer continuation moves to Task 02 | provider/model-response tests |
| Tool descriptions | Explicit descriptions win; docstring parameter descriptions are preserved | `tests/core/test_tool_description_contract.py` |
| Provider kwargs | Unsupported SDK kwargs are relocated to `extra_body`; retries are explicit and opt-in | model provider/retry tests |
| Parallel safety | Four-level adjudication, missing-result recovery cards, exact unknown-tool errors | `tests/engine/test_concurrent_execution.py` |
| Model-facing tool projection | Generic `model_summary` projection is preserved as a migration seam | `tests/test_model_summary_projection.py` |
| Action receipts | `INFRASTRUCTURE_INVALID` and `commit_action_results` landed | `tests/test_infrastructure_stop_and_receipts.py` |
| Request budgets | Mainline `ContextConfig` and `_ContextRuntime.resolve_request_budget()` already provide provider-neutral budgets and telemetry | `tests/test_compact_history.py` |
| Whole-exchange compaction | Mainline `MessageGrouper` already groups by step/assistant boundary; the final transaction contract moves to Task 04 | compact-history tests |
| Request headers | Added neutral `default_headers` on OpenAI and OpenAI-compatible sync/async transports; no routing-specific header or env name | `tests/test_model_providers.py` |
| Docker environment | Added `container_env`; relative paths resolve under workdir and absolute container paths remain absolute | `tests/test_docker_env.py` |
| TUI action objects | `ContentFirstRenderer` now accepts both dictionaries and `Action` instances | `tests/test_render_content_first.py` |

## 3. Baseline-quality closure

The following problems were found and fixed while closing the task:

- `import qitos.kit` eagerly loaded experimental security-research tools through
  `qitos.kit.toolset`; compatibility exports are now lazy and explicit;
- the full suite hid that import problem through test order; the public-surface
  file now passes independently;
- the private Engine protocol omitted most runtime-owned fields and produced
  more than one hundred mypy errors; it now describes the actual helper seam;
- stale lint errors across the stable surface were removed;
- cancellation checkpoint calls used inconsistent argument order;
- synchronous Engine MCP setup treated an async bridge coroutine as a list;
- native tool-hook typing was corrected without changing mock/standalone
  executor behavior.

## 4. Explicitly not absorbed

| Campaign item | Decision |
|---|---|
| `merge_tool` history rewriting | Rejected as a persistence rule. Task 02 codecs may project a control block into a provider request without rewriting the exchange log. |
| Routing-specific inference-key environment variables | Rejected. Callers pass neutral `default_headers`; secret/config ownership stays outside the framework. |
| Campaign task-id wiring | Rejected as domain/runner glue. Generic Action rendering landed. |
| Campaign context constants | Rejected as universal defaults. Task 04 will use measured, configurable request-view budgets. |
| Canonical campaign JSONL and qita workbench fork | Deferred to Task 05 with a v1 compatibility bridge and corrected raw/redacted storage policy. |
| GLM protocol default flip | Deferred until Task 02 provider conformance proves the transport/preset combination. |

## 5. Closed acceptance criteria

- [x] Domain-neutrality grep contains no campaign-specific mechanism names in
  newly absorbed framework code.
- [x] No hard-coded concurrency-safe tool-name list remains.
- [x] Public imports do not activate experimental security tooling.
- [x] Chat/Responses provider tests and native parallel-action tests pass.
- [x] Full pytest passes with zero failures and collection errors.
- [x] `tests/test_public_surface.py` passes in an isolated invocation.
- [x] Architecture boundary tests pass.
- [x] Stable-surface flake8 is clean.
- [x] Stable-surface mypy reports no errors.

## 6. Authoritative verification

```bash
pytest -q tests/test_public_surface.py
pytest -q tests/test_architecture_boundaries.py
pytest -q
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
```

The final handoff must quote the results of these exact commands. Package build
checks remain required when the branch is prepared for release.

Recorded on 2026-08-29:

- isolated public surface: 4 passed;
- architecture boundaries: 4 passed;
- full suite: 1,694 passed, 50 skipped;
- stable flake8: clean;
- stable mypy: 76 source files, no issues.

## 7. Historical briefs

`06-batch-1-instructions.md` and `07-batch-2-instructions.md` are forensic records
of how Task 01 was dispatched. They are archived and must not be used as current
instructions. This file is the authoritative final state.

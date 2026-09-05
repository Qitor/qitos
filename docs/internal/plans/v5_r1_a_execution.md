# V5 R1 Lane A execution

Outcome: **qualified (offline FRAMEWORK_CONFORMANCE)**. All required offline
adapter matrices and installed consumers pass. Live-model capability is untested.

## Identity and scope

- Source baseline: `4dfb570fb7eef504c1e6d247c21a1984251b80e4`.
- Branch: `codex/v5-r1-a-model-io`; dedicated `WhitzardOS-v5-r1-a` worktree.
- Baseline object type, origin/master ancestry, initial HEAD, merge-base and clean
  state were verified before implementation. The main worktree was not edited.
- Scope: provider transports/stream assembly, model admission accounting and
  AsyncEngine stream ownership, corresponding tests and bilingual documentation.
- No ExchangeLog/RequestView, Session/WorkGraph/checkpoint, ToolResult/Observation,
  sandbox authority, Trajectory wire/reader, MCP, packaging metadata or CI edits.

## Implemented behavior

- OpenAI Chat adapters share terminal/usage/tool-argument validation. Public streams
  raise sanitized ProviderFailure instead of yielding exception text as a final.
  Ordinary model text beginning with `Error:` remains valid output.
- Explicit stop/length/tool-call semantics survive aggregation. EOF without a
  terminal, contradictory terminals, post-terminal content and incomplete tool
  JSON fail closed. Repeated identical provider terminals/usage do not add finals.
- Responses uses the actual native event transport. It requires response.completed,
  rejects failed/incomplete/refusal streams, preserves completed native items once,
  and closes its owned event iterator. Borrowed helper clients remain caller-owned.
- Anthropic assembles content blocks, tool JSON, reasoning/signatures and usage;
  message_stop and closed blocks are required before a successful terminal. Duplicate
  message_stop is idempotent, and interrupted text retains its partial length.
- Azure inherited operations use the Azure client factory, endpoint/API version,
  explicit options/output limit, zero SDK retries and client cleanup.
- LiteLLM/Gemini/local public fallbacks propagate failures instead of answer text;
  they remain one-chunk non-native fallbacks. HTTP responses close on exit. Gemini
  blocked prompt feedback raises a sanitized typed refusal instead of answer text.
- OpenAI client construction carries a proven unsent fact. Canonical failure
  normalization preserves it, and Engine releases the provisional request charge.
  Once transport is entered, connection/status failures remain possibly sent.
  OpenAI stream failures retain attempt and partial-text character-count diagnostics
  without retaining exception payloads. There is no error-prefix heuristic.
- Async streams close response/client resources on explicit aclose and consumer
  cancellation. AsyncEngine retains worker tasks after consumer cancellation and
  requests cooperative Engine cancellation; it does not claim to kill threads.
- Model history compatibility rereads preserve prior result completion order within
  each batch. Provider declaration-order views no longer overwrite completion facts.
  The installed consumer exposed this after enforcing a committed-terminal Event.
- No root/aggregate exports or Engine constructor defaults were added. EOF/error
  behavior intentionally changes: incomplete output is no longer successful output.

## Offline provider matrix

| Adapter | Exercised path |
| --- | --- |
| OpenAIModel | Chat public stream + canonical aggregation; native Responses |
| OpenAICompatibleModel | Chat public stream + canonical aggregation; Responses regression |
| AsyncOpenAIModel | active-loop astream, normal/close/cancellation |
| AsyncOpenAICompatibleModel | active-loop astream, native Responses, close/cancellation |
| AnthropicModel | native SSE tool input, stop/usage and truncated-input cleanup |
| AzureOpenAIModel | inherited stream success/failure and client endpoint/version/options |
| LiteLLMModel | actual public fallback success/failure |
| GeminiModel | actual public fallback success/failure/response cleanup |
| OllamaModel | actual public fallback success/failure |
| OllamaGenerateModel | actual public fallback success/failure |
| LMStudioModel | actual public fallback success/failure |
| VLLMModel | actual public fallback success/failure |

Only SDK/HTTP boundaries are replaced in the new adapter tests. Providers, codecs,
Engine, canonical stream assembly and tool runtime remain real implementations.

## Installed consumer

`examples/v5/r1_a_model_io/consumer.py` runs outside the checkout in an independent
wheel venv. It uses public config/composition/Session, the built-in compatible
adapter and real registered function tools. The controlled SDK boundary never
contacts a provider. A tool_slot_terminal hook releases the Event only after
multiply has a committed terminal; persisted result order is also asserted.

- Normal: 3 actual model requests, 3 executions, terminal completion order
  multiply/add/add, two closed batches, declaration-order result views, final 11.
- Interruption: 2 requests and the first 2 executions only; add(5,6) executes zero
  times, no successful final and no duplicate effects.
- Each call has one terminal; Session/journal session_id and run_id align.
- This is FRAMEWORK_CONFORMANCE, not a live-model capability result.

## Environment and verification ledger

Independent Python 3.12.7 environment, with unchanged pinned quality tools:
flake8 7.0.0, mccabe 0.7.0, pycodestyle 2.11.1, pyflakes 3.2.0, mypy 1.19.1.
Relevant installed dependencies: OpenAI 1.109.1, requests 2.34.2,
types-requests 2.33.0.20260712, Playwright 1.58.0. No shared installation was changed.

| Check | Result |
| --- | --- |
| Initial 16 stream regressions against archived fixed baseline | 16 failed, confirming old defects |
| Provider/config/stream required group, including Responses and worker ownership | 213 passed, including installed consumer |
| Installed consumer test with QITOS_R1_INSTALLED_PYTHON | passed |
| Page-extracted EN/zh installed examples | 20 passed, 1 explicit Docker skip |
| tests/test_docs_golden_paths.py | 6 passed in isolated rerun |
| Architecture/public-surface/no-local-path suites | 10 passed |
| static_quality.py check with fixed QUALITY_BASELINE_REF | passed; 356 existing findings, no delta |
| Stable flake8 | passed |
| Stable mypy | passed, 96 source files |
| python -m build | wheel and sdist built |
| python -m twine check dist/* | passed |
| validate_docs.py | passed |
| sync_api_reference.py --check | passed |
| sync_tutorial_docs.py --check | passed |
| git diff --check | passed |
| Final frozen-source full pytest run | 3487 passed, 51 skipped, zero failures (279.43 s) |

The 51 skips are 50 live E2E cases requiring endpoint/key configuration and
1 explicit Docker qualification case. No required offline provider/consumer case
is skipped. Golden paths and both language page executions pass in the final run.

Early verification failures were not counted as passes: missing pytest/pip/SDK/test
packages, a missing requests type stub causing a diagnostic-signature mismatch,
old Responses EOF expectations, an incomplete SDK error stub in page-extracted
consumer execution, and a source/wheel mismatch while implementation was still
changing. These were corrected without adding ignores or baseline allowances.
A stronger installed assertion then exposed completion-order loss during model
history projection: the frozen run had 4 failures, 3480 passes and 51 skips. The
failures were the installed consumer and its three documentation executions.
This was fixed solely in the model runtime, without changing conversation schemas.
One earlier full run had 3481 passes and an unrelated work_graph.py receipt failure;
that golden suite passed separately. A later run was intentionally interrupted
(446 passed, 40 skipped) to fix two newly reproduced Anthropic cases and one Gemini
refusal-text case. Their pre-fix regressions failed; final source is `cd7bf90`.
The final frozen-source full run passed.

The checked wheel contains 505 Python files byte-identical to the source at
`cd7bf90789f17af4c8409286ca7539024f509df8`. Wheel SHA-256:
`56a3ce7d5515cc9f250a21d6c029072218e1a42263440fc3e389913efae3ef12`.
The full suite uses `QITOS_R1_INSTALLED_PYTHON` pointing at the independent wheel
venv and `QITOS_DOCS_WHEEL` pointing at this exact wheel, with `pytest -q -rs`.
The installed subprocess removes PYTHONPATH and runs a copied consumer outside
the repository.

## Commits and handoff

1. `7a4451b` — failure/lifecycle/budget regressions.
2. `e8b028f` — provider stream correctness, accounting and cleanup implementation.
3. `68b4282` — installed multi-round consumer and test.
4. `a7bae62` — retain tool completion order across model history projection.
5. `cd7bf90` — Anthropic duplicate stop/partial diagnostics and Gemini typed refusal.
6. Bilingual documentation and this final execution ledger: the containing commit.

Implementation and all required offline verification are complete. The final
documentation commit contains no additional runtime changes. The final handoff
reports its HEAD and clean worktree status.

## Limits and operations not performed

- `live_not_run`: no credentials resolved from a real source and no real-model calls.
- Non-native fallbacks do not acquire native token streaming in this lane.
- Python worker cancellation is cooperative. An iterator retained after a consumer
  break must be explicitly closed/acclosed by its owner.
- No push, deployment, package publication, default-branch change, cross-lane
  cherry-pick or worktree deletion. No quality allowance growth or shrink was needed.

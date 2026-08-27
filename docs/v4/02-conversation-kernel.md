# Task 02 — Conversation Kernel: canonical message stack, policies, native parallel tool calls

Status: actionable design
Parents: `docs/internal/plans/v0.7_native_agent_kernel.md` §1 (Pillar A), §2 (Pillar B)
Depends on: Task 01 (reasoning fields, multi-action isolation, decision-context normalization)
Unblocks: Task 03 (ACI tools render into the stack), Task 04 (delivery policy consumer)
Milestone: P1–P2

---

## 1. Goal

Make the **message stack the kernel object**. Today, conversation shape is assembled ad-hoc inside `qitos/engine/_model_runtime.py` (prompt spec + history + per-step user injections + campaign-era wrappers). This task introduces a canonical `Conversation` contract with per-provider compilation and explicit policies, and completes native parallel tool-call support end to end.

Researchers get: one object that is (a) provider-faithful — the exact shape models are trained on, (b) inspectable and validatable, (c) policy-driven for reasoning preservation and runtime-context delivery.

## 2. Scope

In: canonical turn model + validators; ReasoningPolicy / ContextDeliveryPolicy / SteeringPolicy; compilers for chat-completions / Responses / Anthropic; preset defaults; engine integration replacing `_model_runtime` assembly internals; `Decision.actions` multi-action path finalization; protocol `json_decision_multi_v1` default decision (GLM preset).

Out: rendering/TUI (Task 05), trajectory export (Task 05), context injector registry (Task 04 — consumes this task's delivery policy), any tool content (Task 03).

## 3. Current state (verified)

- `qitos/core/model_response.py`: `reasoning_fields`/`reasoning_source` (after Task 01).
- `qitos/engine/_model_runtime.py`: hand-rolled assembly; campaign `merge_tool` exists only on `origin/feat/runtime-context-in-tool` (72d3d7d) behind `CYBERGYM_OBSERVATION_DELIVERY`.
- `qitos/protocols.py`: `json_decision_multi_v1` exists (campaign), with combination rules (no data-dependent grouping, no mixed writes, ≤4 actions).
- `qitos/harness/_presets.py`: 11 FamilyPresets with `recommended_request_kwargs` (after Task 01); GLM default protocol flip deferred to this task.
- History: `qitos/core/history.py` `HistoryMessage`; checkpoint `run_state.py` serializes v1.0 — must be extended for canonical turns.
- Anthropic/Gemini model adapters exist under `qitos/models/`.

## 4. Target design

### 4.1 Canonical turn model — new `qitos/core/conversation.py`

```python
@dataclass(frozen=True)
class ToolCall:
    id: str; name: str; arguments: str          # arguments = raw JSON string (provider-faithful)

@dataclass(frozen=True)
class ReasoningPayload:
    fields: Dict[str, str]                       # verbatim provider channels (reasoning_content, reasoning, …)
    source: str                                  # provider/channel id

class Turn(ABC): …
SystemTurn(content: str, cache_anchor: bool = False)
UserTurn(content: str, kind: Literal["task", "steering"] = "task",
         source: Literal["human", "runtime"] = "human")
AssistantTurn(content: Optional[str], tool_calls: tuple[ToolCall, ...] = (),
              reasoning: Optional[ReasoningPayload] = None)
ToolResultTurn(tool_call_id: str, name: str, content: str,
               is_error: bool = False, summary: Optional[str] = None)

class Conversation:
    # append-only; every mutation runs validators first
    def append(self, turn: Turn) -> None
    def append_batch(self, turns: Sequence[Turn]) -> None       # atomic: assistant + its results
    def tail_is_completed_batch(self) -> bool
    def validate(self) -> list[ConversationError]               # explain-all, never raise mid-run
    def view(self) -> list[Turn]                                # immutable snapshot
```

**Validators (campaign invariants, now first-class):**
1. A `ToolResultTurn` must reference an open `tool_call_id` of the immediately preceding `AssistantTurn`.
2. An `AssistantTurn` with tool_calls is *open* until every call has exactly one result (interrupted-batch recovery may close it with synthetic `[TOOL_RESULT_MISSING]` results — Task 01 mechanism).
3. `tool_call_id` uniqueness across the stack.
4. Under `merge_tool` delivery, no trailing `UserTurn(source="runtime")` may exist after the first tool batch (steering turns allowed only at completed-batch boundaries).

### 4.2 Policies — `qitos/engine/states.py` (ContextConfig extension) or new `conversation.py` policy block

```python
class ReasoningPolicy(Enum):
    DROP = "drop"                    # strip history reasoning (DeepSeek-R style)
    PRESERVE_INLINE = "preserve_inline"   # keep reasoning fields on history assistant turns (GLM preserved thinking; improves continuity + cache hits)
    SIGNED_BLOCKS = "signed_blocks"  # Anthropic thinking blocks must round-trip with signatures
    ITEM_REFERENCE = "item_reference"# OpenAI Responses reasoning items passed back by id

class ContextDeliveryPolicy(Enum):
    USER_TURN = "user_turn"          # universal fallback; conversation may end on user
    MERGE_TOOL = "merge_tool"        # append runtime context into trailing tool result; conversation ends on tool results

@dataclass(frozen=True)
class ConversationPolicies:
    reasoning: ReasoningPolicy = ReasoningPolicy.DROP
    delivery: ContextDeliveryPolicy = ContextDeliveryPolicy.USER_TURN
    max_actions_per_turn: int = 4    # mirrors protocol rule; engine-enforced clamp
```

Preset defaults (in `harness/_presets.py`): `glm → (PRESERVE_INLINE, MERGE_TOOL)`, `anthropic → (SIGNED_BLOCKS, USER_TURN)`, `openai → (ITEM_REFERENCE, USER_TURN)` chat path uses DROP, `deepseek → (DROP, USER_TURN)`. Every default overridable via `build_model_for_preset(..., policies=...)`.

### 4.3 Compilers — new `qitos/models/compilers.py`

```python
@dataclass
class CompileReport:
    reasoning_preserved_chars: int; reasoning_dropped_chars: int
    injections_merged: int; steering_turns: int
    cache_anchor_prefix_bytes: int

def compile_chat_completions(conv, policies, tools) -> tuple[dict, CompileReport]
def compile_responses_items(conv, policies, tools) -> tuple[dict, CompileReport]
def compile_anthropic(conv, policies, tools) -> tuple[dict, CompileReport]
```

Rules:
- Compilers are the **only** place provider JSON is built (absorb: RUNTIME_CONTEXT wrapper + escaping, merge_tool fold with notice line + never-lose-state fallback from 72d3d7d; decision-context packet normalization from 05a1c82 moves here).
- Cache anchors: `SystemTurn(cache_anchor=True)` must remain byte-stable prefix; compilers assert it.
- `PRESERVE_INLINE` re-emits `reasoning_content` on history assistant turns verbatim (no reformatting — provider protocol data, not agent text).
- Merge under `MERGE_TOOL` skips persisting a duplicate runtime user turn in history (each step re-injects into the trailing tool result; stale copies would pollute).

### 4.4 Engine integration

- `_model_runtime` becomes a consumer: builds/maintains the `Conversation` (replacing ad-hoc message lists), calls the compiler, applies `CompileReport` to trace events.
- `Decision.actions` (Task 01 isolation) closes the loop: assistant turn carries N tool_calls; executor appends N `ToolResultTurn`s as one atomic batch.
- `EngineConfig` gains `conversation: ConversationPolicies`; `engine.agent` seam unchanged.
- Checkpoint/RunState: serialize canonical turns (schema bump to v1.1 with migration; old histories load via adapter).
- GLM preset default protocol decision: flip `default_protocol` to `json_decision_multi_v1` **here**, with Breaking release note (absorption plan §10).

## 5. Implementation steps

1. `qitos/core/conversation.py`: turn model + validators + full unit tests (invariants 1–4, atomic batches).
2. Compilers with golden-file tests per provider (message JSON fixtures incl. multi-action batches, preserved reasoning, merged delivery).
3. Policy wiring: ContextConfig/preset defaults; override API on `build_model_for_preset`.
4. `_model_runtime` refactor onto `Conversation`; port 72d3d7d behavior as the `MERGE_TOOL` compiler rule + fallback; delete env-gate.
5. Multi-action finalization: protocol default flip + `max_actions_per_turn` clamp + render of N-action turns (rides on Task 01 render changes).
6. Checkpoint schema v1.1 + migration test.
7. Docs: `docs/concepts/conversation.mdx` (new) — turn model, policies, provider table; update `docs/concepts/engine.mdx` lifecycle diagram to show the stack; zh mirror.

## 6. Acceptance criteria

- [ ] Provider matrix smoke (glm/openai-chat/openai-responses/anthropic): scripted multi-turn parallel-tool-loop runs per provider; assert stack shape, reasoning policy effect (inline preserved / items referenced / blocks signed / dropped), delivery mode, cache-anchor byte stability.
- [ ] Invariant validators tested, including: merge_tool never leaves trailing runtime user turn; merge fallback appends user turn when no tool message exists (state never lost).
- [ ] Interrupted tool-batch recovery closes stacks with `[TOOL_RESULT_MISSING]` results (validator 2 exception path).
- [ ] Round-trip: `Conversation → compile → provider fixture → replay` reproduces identical stack.
- [ ] 50-line example agent (shared acceptance with Task 03) runs with GLM preset using parallel calls + preserved reasoning + runtime context, CI-tested.
- [ ] Neutrality grep clean; no `CYBERGYM_OBSERVATION_DELIVERY` anywhere.

## 7. Verification

```bash
pytest -q tests/core/test_conversation.py tests/models/test_compilers.py tests/engine/test_model_runtime_conversation.py
pytest -q   # full suite
flake8 qitos/core qitos/engine qitos/models && mypy qitos/core qitos/engine qitos/models
```

## 8. Risks / open questions

- Q: keep `HistoryMessage` as the persistence type and derive turns, or store turns canonically? — Decision: store turns canonically (single source of truth); `HistoryMessage` becomes an adapter for old kit memory implementations.
- Q: steering by humans mid-run — engine interrupt seam exists (`engine/interrupt.py`); verify steering turns route through `submit_turn` and land as `UserTurn(kind="steering")`.
- Risk: compiler golden fixtures rot as providers change — mitigate with small fixtures + policy-driven assertions rather than full-payload snapshots.

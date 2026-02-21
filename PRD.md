# QitOS PRD (First Public Release)

## 1. Product Intent
QitOS is a **single-kernel Agent framework** designed for research and rapid innovation.

Primary promise:
- Build new agent ideas quickly.
- Debug and explain agent behavior rigorously.
- Reproduce and compare experiments reliably.

This release has **one architecture only**:
- `State + Policy + Runtime + Trace`

No parallel runtime models are part of the product direction.

---

## 2. Product Goals

### 2.1 Core Goals
1. **Fast Agent Innovation**
   - A researcher can implement a new agent strategy by writing `state + policy + tools/env`.
2. **Strong Observability**
   - Every step is inspectable: observation, decision, actions, results, state diff, stop reason.
3. **Reproducible Evaluation**
   - Runs emit schema-validated traces and benchmark-ready artifacts.
4. **Composable Ecosystem**
   - Policies, parsers, memories, planners, critics, executors, and toolkits are pluggable modules.

### 2.2 User Experience Goals
1. Beginner path: `agent.run(...)` should be enough.
2. Advanced path: explicit runtime composition with fine control.
3. Template path: scaffolded structure, low boilerplate.

---

## 3. Non-Goals (for this release)
1. Hosted control plane / SaaS orchestration.
2. Visual workflow builder.
3. Model training or fine-tuning platform.
4. Full production adapters for every external environment.

---

## 4. Target Users
1. **Agent researchers**
   - Need rapid policy iteration (ReAct, PlanAct, ToT, Reflection, Voyager-like).
2. **Applied agent engineers**
   - Need robust runtime, debugging, and trace standards.
3. **Template builders**
   - Need repeatable structure for domain-specific agents (e.g., PPT agents, image reasoning agents, SWE agents).

---

## 5. Design Principles
1. **Single Kernel**: one orchestrator model in production.
2. **Policy/Runtime Separation**: strategy in policy, orchestration in runtime.
3. **Strong Contracts**: typed interfaces, schema validation, explicit errors.
4. **Composable Layers**: modules are replaceable without runtime rewrites.
5. **Trace-First**: replay and eval are built-in outputs, not add-ons.
6. **Simple Default, Explicit Control**: easy entry with transparent advanced options.

---

## 6. System Architecture

### 6.1 Kernel Components
1. **State**
   - Typed runtime state object.
   - Single source of truth during run.
2. **Policy**
   - Produces decisions from state and observation.
   - Updates state from execution feedback.
3. **Runtime**
   - Runs phase loop, executes actions, applies stop/recovery logic.
4. **Trace**
   - Emits schema-valid artifacts: `manifest.json`, `events.jsonl`, `steps.jsonl`.

### 6.2 Extensible Layers
1. **Parser layer**: raw model output -> Decision.
2. **Tool layer**: capability execution contracts.
3. **Environment layer**: non-tool action targets (browser/office/desktop/repo).
4. **Memory layer**: retrieval and retention strategies.
5. **Search layer**: branch expansion/scoring/pruning/backtracking.
6. **Critic layer**: quality gates and verification.

---

## 7. Core Interface Contracts

## 7.1 State
State can be dataclass or typed model, accessed through adapter in runtime.

Required runtime semantics:
- step counter
- final result
- stop reason

Recommended fields:
- metadata
- memory references
- policy-local structures (plan, tree nodes, reflections)

---

## 7.2 Decision Contract

```python
@dataclass
class Decision:
    mode: Literal["act", "final", "wait", "branch"]
    actions: list[Any] = field(default_factory=list)
    final_answer: str | None = None
    rationale: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    # For search/tree strategies
    candidates: list["Decision"] = field(default_factory=list)
    decision_id: str | None = None
    parent_decision_id: str | None = None
    depth: int | None = None
    score: float | None = None
    confidence: float | None = None
```

Validation rules:
- `act` requires non-empty `actions`.
- `final` requires non-empty `final_answer`.
- `branch` requires non-empty `candidates` and valid candidate decisions.

---

## 7.3 Policy

```python
class Policy(Protocol[StateT, ObsT, ActionT]):
    def prepare(self, state: StateT, context: dict[str, Any] | None = None) -> None: ...
    def propose(self, state: StateT, obs: ObsT) -> Decision: ...
    def update(self, state: StateT, obs: ObsT, decision: Decision, results: list[Any]) -> StateT: ...
    def finalize(self, state: StateT) -> None: ...
```

Policy owns:
- planning logic
- branch/search behavior
- reflection logic

Policy does not own:
- execution scheduling
- retries/recovery orchestration
- trace writing

---

## 7.4 Runtime

Runtime phase loop:
1. OBSERVE
2. PROPOSE
3. SELECT (only when decision mode is `branch`)
4. ACT
5. UPDATE
6. STOP

Runtime inputs:
- policy
- state adapter
- action executor
- optional parser
- stop criteria
- recovery policy
- optional branch selector
- optional memory adapter
- optional critic chain
- trace writer

Runtime outputs:
- final state
- step count
- structured runtime events

---

## 7.5 State Adapter
Runtime must not hardcode state field names.

```python
class StateAdapter(Protocol[StateT]):
    def get_step(self, state: StateT) -> int: ...
    def set_step(self, state: StateT, value: int) -> None: ...
    def get_final(self, state: StateT) -> str | None: ...
    def set_final(self, state: StateT, value: str | None) -> None: ...
    def get_stop_reason(self, state: StateT) -> str | None: ...
    def set_stop_reason(self, state: StateT, value: str | None) -> None: ...
```

---

## 7.6 Tool Contract

```python
@dataclass
class ToolSpec:
    name: str
    version: str
    description: str
    parameters_schema: dict[str, Any]
    permissions: dict[str, bool]  # filesystem/network/command/etc.
    timeout_s: float | None = None
    max_retries: int = 0

class ToolSet(Protocol):
    name: str
    version: str
    def setup(self, context: dict[str, Any]) -> None: ...
    def teardown(self, context: dict[str, Any]) -> None: ...
    def tools(self) -> list[Any]: ...  # function tools / tool callables / tool specs
```

Tool registry responsibilities:
- registration
- lookup
- invocation
- metadata introspection
- support both plain function registration and ToolSet registration
- collision-safe namespacing across ToolSets

Action executor responsibilities:
- execute action lists
- normalize outputs into ActionResult
- attach latency/retry/error metadata

Runtime lifecycle guarantees:
- call `ToolSet.setup(...)` exactly once before first tool invocation
- call `ToolSet.teardown(...)` exactly once on run end (success or failure)
- emit trace events for toolset lifecycle phases

---

## 7.7 Parser Contract

```python
class Parser(Protocol):
    def parse(self, raw_output: Any, context: dict[str, Any] | None = None) -> Decision: ...
```

Rules:
- Parser must output valid Decision.
- Parser errors are structured runtime errors.

---

## 7.8 Memory Contract

```python
class MemoryAdapter(Protocol):
    def append(self, record: Any) -> None: ...
    def retrieve(self, query: dict[str, Any] | None = None) -> list[Any]: ...
    def summarize(self, max_items: int = 5) -> str: ...
    def evict(self) -> int: ...
```

---

## 7.9 Search Contract

```python
class SearchAdapter(Protocol):
    def expand(self, state: Any, obs: Any, seed_decision: Decision) -> list[Decision]: ...
    def score(self, state: Any, obs: Any, candidates: list[Decision]) -> list[float]: ...
    def select(self, candidates: list[Decision], scores: list[float]) -> Decision: ...
    def prune(self, candidates: list[Decision], scores: list[float]) -> list[Decision]: ...
    def backtrack(self, state: Any) -> Any: ...
```

---

## 7.10 Critic Contract

```python
class Critic(Protocol):
    def evaluate(self, state: Any, decision: Decision, results: list[Any]) -> dict[str, Any]: ...
```

Critic output may influence:
- continue
- retry
- stop

---

## 7.11 Environment Contract

```python
class EnvAdapter(Protocol):
    def observe(self) -> Any: ...
    def apply_action(self, action: Any) -> Any: ...
    def reset(self) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...
```

This enables non-tool-first agents (e.g., Office/Browser/Desktop workflows).

---

## 8. Multimodal Observation Standard

## 8.1 ObservationPacket

```python
@dataclass
class ObservationPacket:
    text: list[str] = field(default_factory=list)
    images: list[dict[str, Any]] = field(default_factory=list)    # uri/hash/shape/source
    documents: list[dict[str, Any]] = field(default_factory=list) # uri/hash/type/source
    audio: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

Requirement:
- Policy input can always be represented as ObservationPacket.

---

## 9. Trace Standard (Spec v1)

## 9.1 Artifacts
- `manifest.json`
- `events.jsonl`
- `steps.jsonl`

## 9.2 Required Manifest Fields
- schema_version
- run_id
- status
- step_count
- event_count
- summary
- model_id
- prompt_hash
- tool_versions
- seed
- run_config_hash
- stop_reason
- cost/token/latency summaries

## 9.3 Required Event Fields
- step_id
- phase
- ok
- ts
- payload
- error (nullable)

## 9.4 Required Step Fields
- step_id
- observation
- decision
- actions
- action_results
- state_diff

Trace validation is mandatory before run completion is marked successful.

---

## 10. Debugging and Inspection

Required debugging capabilities:
1. step-into
2. step-over
3. breakpoints (step/phase/condition)
4. run comparison at same step
5. explanation view per step:
   - state diff
   - decision rationale
   - execution I/O
   - critic output
   - recovery path
   - stop reason

---

## 11. Evaluation Framework

## 11.1 Evaluation Contract
- Every template must provide an `eval.py`.
- Eval output must include:
  - success_rate
  - average_steps
  - latency/cost
  - recovery_count
  - branch/search metrics (if applicable)

## 11.2 Regression Gate
- CI must run benchmark smoke tests for core templates.
- Fail build on significant regression according to policy thresholds.

---

## 12. Template Contract

Each template must follow:
- `state.py`
- `policy.py`
- `tools.py`
- `config.yaml`
- `eval.py`

Template code must not contain runtime loop implementation.

---

## 13. Preset Ecosystem

Preset layers:
- policies
- parsers
- memories
- planners/search
- toolkits
- critics
- executors

Design rule:
- Presets must compose via contracts, never via hidden side effects.

---

## 14. CLI Surface (first release)

Required commands:
- `run`
- `eval`
- `replay`
- `inspect`
- `template new`

CLI must map directly to kernel abstractions and not introduce alternate semantics.

---

## 15. Quality Gates

## 15.1 Engineering Gates
- Unit tests for all core contracts.
- Integration tests across policy/runtime/tool/memory/parser.
- Trace schema validation in CI.

## 15.2 Product Gates
- New user can run first template within 10 minutes.
- A failed run can be diagnosed quickly via inspector outputs.
- Benchmark reports are reproducible from config + trace.

---

## 16. Risks and Mitigations

1. Risk: Hidden second execution path appears over time.
   - Mitigation: CI architecture checks + strict exports.

2. Risk: Parser and decision drift.
   - Mitigation: strict Decision schema and fail-fast validation.

3. Risk: Preset sprawl with inconsistent quality.
   - Mitigation: layered preset contracts + compatibility tests.

4. Risk: Multimodal payload instability in trace.
   - Mitigation: ObservationPacket schema + trace serialization rules.

---

## 17. Release Readiness Criteria
The framework is release-ready when:
1. One kernel path is used by docs, CLI, templates, and tests.
2. Core templates (ReAct, PlanAct, ToT baseline, Voyager-like, SWE-mini) run on same runtime.
3. Trace artifacts are schema-valid for all benchmark smoke runs.
4. Inspector can explain at least one successful and one failed run end-to-end.

---

## 18. Summary
QitOS first release is a **single-kernel, research-grade, composable agent framework**.

It is simple where users start (`agent.run`) and strict where research requires rigor (contracts, trace, evaluation, inspection).

The product is designed so new agent ideas are implemented by replacing modules, not rewriting the framework core.

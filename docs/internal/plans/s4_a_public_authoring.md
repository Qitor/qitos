# S4 Lane A — public authoring, Session-first runtime, configuration, and CLI

Status: active implementation plan
Source: `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
Branch: `codex/v4-s4-a-public-authoring`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s4-a`

## Leases

Lease owner: S4 Lane A
File(s): `qitos/config/**`, `qitos/cli.py`, `qitos/core/session.py`,
`qitos/engine/{engine.py,session_runtime.py,runtime.py}`, `qitos/checkpoint/**`,
`qitos/demo/minimal.py`, the `qitos_new_agent` scaffold, Lane-A tests/fixtures,
and this plan.
Semantic purpose: converge public authoring on the existing
`AgentModule + Engine + Session` runtime, with explicit resource ownership and
thin Session CLI control.
Expected start/end package: S4 Lane A only.
Other lanes blocked or adapter supplied: B/C/D receive stable JSON-safe config
extension slots and committed producer fixtures; shared exports and public docs
remain for G5 integration.

## Exact-source census and API decision

| Entry | Classification | Current behavior | S4-A decision |
|---|---|---|---|
| `qit run --config` | canonical beginner | config composition then direct `Engine.run()` | route through `AgentComposition.session(...).run()` |
| `build_agent_composition()` + `AgentComposition` | canonical beginner | process-local bundle; manual `close()` | retain in place; add context management, idempotent typed cleanup, and `session()` |
| `run_agent_config()` | canonical beginner | direct Engine execution | Session-first by default; explicit `ephemeral=True` compatibility path only |
| `Engine.session()` / `Session.run()` | stable advanced | durable facade over the canonical Engine loop | execution truth used by both public golden paths |
| `Engine.restore()` | stable advanced | resolver-only fresh composition | keep; expose through composition and CLI without constructing a fake Engine |
| `Session.inspect/pause/steer/fork/current_head/capabilities` | stable advanced | typed durable control | expose consistently; terminal rejections stay typed |
| direct `Engine(...)` / `Engine.run()` | stable advanced | full low-level construction and loop | keep; recommend `RuntimeComposition` for new code |
| `AgentModule.run()` | compatibility | lazy convenience that constructs Engine | keep; migration guidance points beginners at composition/Session |
| `Engine.init_session()` and `Engine.resume*()` | compatibility | step API / older checkpoint resume | keep pending external-consumer evidence |
| checkpoint v2 Session head/fork helpers | internal/stable store protocol | canonical durable persistence | no new store or persistence truth |
| `CheckpointManager` | deprecated | v1 compatibility, still used by experiment/tests | do not extend or delete in this lane |
| qita mutation-like paths | compatibility/read-only boundary | legacy fork path exists outside lease | no new mutation; `qit session` owns Session mutation |
| demos/templates/examples using direct run | compatibility/teaching debt | widespread consumers | update only leased scaffold/demo; publish G5 migration list |

Decision: `AgentComposition` is the existing beginner composition object and
resource owner. It is not a runner. Its `session(task)` returns the existing
`qitos.engine.Session`; its restore method delegates to `Engine.restore()` using
the composition's runtime/resolvers. Declarative execution uses the same methods.

## Migration table

| Old spelling | Replacement | Compatibility |
|---|---|---|
| `composition.engine.run(task)` | `composition.session(task).run()` | advanced direct Engine remains supported |
| `run_agent_config(... session.enabled=false)` | Session-first default | legacy `enabled: false` normalizes to explicit ephemeral with warning |
| direct no-store launch | `runtime.session.mode: ephemeral` | never reports durable pause/restore/fork |
| manual `try/finally: composition.close()` | `with build_agent_composition(...) as composition:` | `close()` remains and becomes idempotent |
| qita mutation | `qit session ...` | qita stays read-only |

## Work packages

1. Add failing lifecycle, default-Session, CLI, config-slot, equivalence, and
   scaffold tests.
2. Harden `AgentComposition` ownership and partial-build cleanup.
3. Make config/CLI Session-first and add explicit ephemeral semantics.
4. Add thin `qit session inspect|resume|fork|capabilities`; report live-process
   pause/steer as typed unsupported while supporting restore-time steering.
5. Replace the beginner scaffold with a canonical config, credential reference,
   durable SQLite store, Trajectory, sandbox policy, and deterministic fake-model
   programmatic test.
6. Publish producer fixtures and exact validation evidence.

## Interface budget (before)

- root exports: 39; no Lane-A additions permitted.
- `qitos.core` aggregate exports: 78; no Lane-A additions permitted.
- `qitos.engine` aggregate exports: 27; no Lane-A additions permitted.
- `qitos.config` public exports: 24.
- `Engine.__init__`: 34 parameters after `self`.
- CLI top-level families: 10 (`run`, `demo`, `skill`, `bench`, `experiment`,
  `new`, `list-templates`, `leaderboard`, `push`, `pull`).
- explicit deprecation markers in leased runtime surfaces: 3; one deprecated
  public class (`CheckpointManager`).

Budget: root/core/engine aggregate exports stay flat; config growth is limited to
typed cleanup/launch receipts if necessary; Engine constructor does not grow;
one coherent top-level `session` family may be added.

## B/C/D configuration handoff

- B owns implementation of `context`, `memory`, and `compaction`; Lane A accepts
  strict JSON-safe mappings in named extension slots and transports them only as
  config/digest metadata until B supplies a consumer.
- C owns tool, sandbox, MCP, and WorkGraph implementation shapes; Lane A exposes
  strict logical slots and passes them to existing runtime seams without copying
  C types.
- D owns Trajectory schema/store rollout; Lane A keeps the existing trajectory
  selector and event-sink seam, and records config/session/run provenance.
- No slot may contain a callable, live client, resolver, secret, host credential
  path, SDK response, Docker client, process, thread, or file descriptor.

## Patch-ready shared-document suggestions (G5-owned)

README: “The canonical launch path is now Session-first: load `qitos.agent`, use
`with build_agent_composition(...)`, create `composition.session(task)`, and run
or inspect that durable Session. Direct Engine construction remains an advanced
API; stateless launches must opt into `ephemeral` explicitly.”

README.zh: “规范启动路径现已以 Session 为先：加载 `qitos.agent`，通过
`with build_agent_composition(...)` 管理资源，并使用
`composition.session(task)` 创建、运行和检查持久 Session。直接构造 Engine
仍是高级接口；无状态运行必须显式选择 `ephemeral`。”

CHANGELOG / Unreleased / Changed: “Converged declarative and programmatic agent
launches on the durable Session runtime; added deterministic composition cleanup,
explicit ephemeral compatibility, and a thin `qit session` control family.”

progress: “S4 Lane A publishes the Session-first public authoring producer bundle
from its exact source. It does not claim S4/G5 completion, live daemon control,
provider parity, production sandbox qualification, a frozen/default Trajectory,
or release readiness.”

## Validation ledger

Pending implementation. Record exact commands, counts, wheel/fresh-venv result,
fixture digests, final HEAD, and clean status here before handoff.

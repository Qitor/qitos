# Trajectory contract and G5 migration

G5 freezes the existing Trajectory record, identity, role, privacy, loss and
export wire shapes after controlled installed A/B/C qualification on
511013acfd18efcc0d25901e8a7641c4ee731d93. The exact shapes are pinned in
`tests/fixtures/s4/g5/frozen-trajectory-contract.json` and tested against the
current definitions and pre-freeze consumer bytes. There is one Trajectory
Python API; Session/checkpoint remains the authority for execution recovery.

Persisted schema identifiers retain the spelling `candidate-1`. Renaming those
identifiers merely to remove that word would invalidate already written bytes;
the spelling does not create a second contract. Future incompatible changes
require an explicit reader migration. Historical trace is read through the
existing compatibility reader, with declared losses and compatibility authority.
It must not be represented as current writer qualification.

Raw/private canonical data, redacted/public export and diagnostic views have
separate privacy roles. An exact public re-import preserves the selected public
projection; it does not restore redacted private data. Content digests bind the
exported projection, and loss remains explicit. Artifact references require the
caller-composed resolver for content retrieval.

Journal query results are bounded and expose pagination or typed limits.
Complete run/session reads and exact exports materialize the complete selected
trajectory. The current journal reloads all frames for queries and appends and
rebuilds its index on append; total memory is not bounded by the query limit.
See the G5 execution ledger and committed repeated measurements for observed
costs. Schema freeze alone does not authorize default switching, local promotion
or publication; these have independent validation gates.

## Default writer selection

Declarative composition enables its required private Trajectory sink by default.
Directory output resolves to `trajectory.journal`; explicit `.json` files retain
the supported JSON store path. Set `runtime.trajectory.enabled: false` to opt out.
`AgentModule.run()` uses the same event-sink seam and journal under trace_logdir,
with `trace=False` disabling that convenience default. Passing an explicit
RuntimeComposition controls its own sinks. Explicit legacy TraceWriter remains
a compatibility option; the convenience default does not instantiate it.
The existing Engine constructor is unchanged, and no new root export is added.
Low-level Engine callers continue to select their RuntimeComposition explicitly.
The programmatic convenience path's default checkpoint remains process-local;
use declarative durable composition for cross-process Session recovery.

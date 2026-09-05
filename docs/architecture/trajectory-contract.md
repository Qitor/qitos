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

Journal query results expose pagination or typed limits. Complete run/session
reads and the old in-memory export/re-import APIs remain materializing. The
verified-content parsing cache still hashes every historical byte, including
same-size edits with restored mtime; avoiding parsing does not avoid reading.

Lane D adds `StoreTrajectoryReader.from_journal` and `read_page(query, cursor)`
to the existing reader adapter, without changing the default source selector or
frozen record/export schema. A reader-owned temporary SQLite index is rebuilt
from verified journal frames; it is derived and stores no payloads. The source
sidecar is never trusted for addressing. Fixed SQLite/I/O caches, one frame
(existing 64 MiB limit), a page (default 128, maximum 10,000), and a signed cursor
bound retained memory independently of history size. Cold index construction
and explicit new-head rebuilds cost O(N) decoding and disk space. Warm pages
hash all snapshot bytes and decode only addressed frames. Snapshot cursor tokens
are reader-local, contain no paths, bind query/view/head/position/source, and
expire at reader close. A failed later rebuild preserves the previous snapshot.
Long traversals hold no source lock across user yields; this is advisory local
coordination, not protection against an arbitrary hostile host after validation.

Writer ID and run/session/work positions are maintained incrementally on warm
append. The JSON sidecar is checkpointed at open, explicit rebuild and close;
ordinary flush only fsyncs the journal. Checkpoints cost O(N) and carry
record_count/journal_head_digest. Crash leaves at most a stale derived index,
rebuildable from the sole journal truth. Journal durability precedes any derived
index success: append reports `index_checkpoint_deferred`, while close may report
`index_rebuild_required` with journal persistence still confirmed. External
append still invalidates the full parsing cache and triggers verified rebuilding.

`CanonicalTrajectoryExporter.export_file` spools bounded pages, losses and policy
IDs to owned disk staging, verifies the snapshot again, fsyncs the completed file
and atomically replaces the target. Failure/cancellation preserves an existing
target and cleans only its own staging. Public redaction and exact selected-view
re-import retain the frozen canonical wire; the importer itself still materializes.
Continuous iterators/file exports verify the full snapshot at start/end and validate addressed frames between those boundaries. Iterator output is partial until exhaustion; early close never claims completion. Independent pages retain full-history verification per page. The qita canonical file-export command consumes this capability. Legacy readers
without it return typed unsupported for bounded requests; their old complete
read behavior remains available. Schema freeze does not authorize publication.

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

## Default reader selection and rollback

`qita` selects `trajectory.journal` (or an explicitly retained trajectory.json)
under its log directory and includes the existing frozen-trace compatibility
reader. Identity collisions between those sources are rejected; corrupt current
data never silently falls back to historical data. Discovery consumes every
query page, while complete reads retain the documented materialization cost.
Journal-backed run routes do not require or create legacy run directories.

The existing `default_reader(root, selector="trace")` keyword selects historical
reading for rollback; the default selector is `trajectory`. This optional
parameter is needed to make reader selection explicit and testable without
changing or deleting data. `candidate_file_reader(path)` still explicitly opens
new data during rollback. Writer rollback is the explicit configuration disable
or `trace=False` for the convenience path; callers can supply the existing
TraceWriter when historical output is specifically needed. These selections
never execute a Session or copy execution effects. Unknown selectors reject.

### Project-scoped output and demo migration

An omitted declarative trajectory output now resolves beside the configured
Session store, or under the explicit runtime/project data root. It never
implicitly joins unrelated project data through cwd. An explicit output path
continues to select that location. The minimal demo's trace_run summary now
identifies the journal file and includes a separate run_id; it no longer implies
a legacy manifest directory. trace_prefix is validated and used for the
convenience run identity. RunSpec reports the actual canonical writer schema
even when its historical default field was v1.

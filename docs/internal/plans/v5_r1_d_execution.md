# V5 R1 Lane D execution ledger

Source: `4dfb570fb7eef504c1e6d247c21a1984251b80e4`.
Branch: `codex/v5-r1-d-trajectory-efficiency`. Initial HEAD and merge-base
verified against the fixed source; clean isolated worktree. Main checkout
and other lanes are untouched. No model calls, push, deployment or publication.

## Plan and boundaries

1. Record exact-source work instrumentation and reproducible deterministic workload.
2. Incremental writer ID/position bookkeeping; keep strict historical byte hashing.
3. Add snapshot paging to the existing reader adapter, without changing wire schema,
   old reader protocol, source selection, or complete-read return types.
4. Stream canonical exports through owned staging and connect qita export.
5. Run 10k/100k x 1 KiB, frame <=32, page 128, five repeats in fresh processes;
   compare source/after; install wheel outside checkout; bilingual docs and checks.

## Index design (implementation contract)

The writer owns incrementally maintained ID and run/session/work position maps.
The existing derived JSON index becomes an explicit checkpoint: initial open,
explicit rebuild, and close write a complete index. Ordinary flush only fsyncs
journal bytes; it does not hide O(N) checkpoint work. Watermark is record_count
plus journal_head_digest. Crash before checkpoint leaves a stale/disposable
index; reopening rebuilds from fully verified journal. Append persistence depends
only on journal fsync. Close/rebuild separately report derived-index failure.
External changes still trigger the baseline full parse/rebuild; warm operations
still hash every historical byte and do not claim suffix-only I/O.

Bounded file reading uses an owned temporary disk index of verified frame offsets,
hashes and unique IDs, with a fixed SQLite page cache. Source sidecars are never
trusted for addressing. Cold/rebuilt index construction is O(N) decode and disk;
warm pages hash the entire snapshot boundary then decode only addressed frames.
No full payload, record or index collection is retained by the bounded reader.
Cursors bind query/view, reader/source identity, head, byte boundary and position.
Reader-local cursors expire on close; each finite operation locks/validates its
source descriptor. Iteration holds no lock across user yields.

## Status

- Preflight and required contract/code review completed.
- Implementation and qualification in progress; no qualified outcome yet.
- Explicit non-goals: suffix-only I/O, Artifact GC, external training formats,
  campaign publication, bounded RSS for all old materializing APIs.

## Writer checkpoint implementation

Warm append now uses `_by_id` and incrementally maintained positions; rollback
removes only the just-assigned batch. `_load` retains the baseline full-byte hash
and full decode on external changes. Journal fsync precedes bookkeeping; uncertain
writes invalidate the parsing cache and retry re-verifies the journal. Append
receipts identify `index_checkpoint_deferred`; close can report
`index_rebuild_required` independently of journal persistence. Initial targeted
existing journal/default-reader regressions: 21 passed on Python 3.12.7.

## Bounded reader implementation

`StoreTrajectoryReader.from_journal` validates through a bounded frame buffer and
an owned temporary SQLite index. The existing `candidate_file_reader` and default
selection use the same reader adapter. Old complete reads remain materialized but
do not install a permanent payload cache in this adapter. `read_page`,
`TrajectoryPage`, `TrajectoryCursor`, `iter_records` and typed unsupported/rejected
errors live under tracing only. Cursors are HMAC-bound to a reader instance and
expire at close. Query limit is the page size. Returned watermark is the captured
journal head sequence, including filtered-out records. Polling explicitly starts
a new capture with after_sequence=watermark. Temporary index startup/rebuild is
O(N) decoding/disk work; each warm page rehashes snapshot bytes with fixed buffers.
No mutation/recovery of source or sidecars occurs. The SQLite cache is 1 MiB;
frame bytes remain subject to the existing 64 MiB bound (32 records in workloads).

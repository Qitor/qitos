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

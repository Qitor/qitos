# V5 R1 Lane D qualification report

Outcome: **qualified** for the requested strict-integrity index, bounded reading and canonical file export scope. Runtime source is `df9316415db7ec76f1e5d70a11ceabfd47744169`; before is exactly `4dfb570fb7eef504c1e6d247c21a1984251b80e4`. Branch: `codex/v5-r1-d-trajectory-efficiency`; isolated sibling worktree: `WhitzardOS-v5-r1-d`. Final delivery adds documentation, tests, examples and this evidence without changing measured runtime. Its commit is the branch HEAD reported at handoff.

## User API

```python
from qitos.tracing.readers import StoreTrajectoryReader
from qitos.tracing.trajectory import TrajectoryQuery
from qitos.tracing.paging import iter_records
from qitos.tracing.exporter import CanonicalTrajectoryExporter

reader = StoreTrajectoryReader.from_journal("trajectory.journal")
try:
    query = TrajectoryQuery(run_id="run-id", limit=128)
    page = reader.read_page(query)
    if page.next_cursor is not None:
        page = reader.read_page(query, cursor=page.next_cursor)
    for record in iter_records(reader, query):
        pass  # Consume immediately; traversal is partial until exhaustion.
    receipt = CanonicalTrajectoryExporter().export_file(reader, query, "public.json")
    assert receipt.completed
finally:
    reader.close()
```

`qita export --run RUN_ID --journal FILE --canonical OUTPUT` consumes the new bounded path. Public redaction remains the default; raw private export is explicit. Root exports, Engine parameters, source selection, historical readers and existing complete-read return types are unchanged. Bounded requests on unsupported third-party readers raise `BoundedReadUnsupported`; old complete APIs remain materializing.

## Index, durability and cursor contract

Writer ID and run/session/work positions update only for the appended batch. The derived JSON index checkpoints at open/rebuild/close; ordinary flush only fsyncs journal bytes. Checkpoint watermark is record count plus journal head digest. Journal is the sole truth; crash/stale checkpoints rebuild from verified bytes. Journal fsync success and derived-index failure are separate receipts. Open/rebuild/close still have O(N) checkpoint costs. Writer retention remains O(N).

Warm operations still hash every historical byte, including same-size modifications with restored mtime. Baseline already cached parsing; warm decoded=0 on both sides is not a new optimization. Duplicate retries, two writers, external appends, uncertain fsync, short writes, partial-tail handling and read-only non-recovery retain their tested contracts.

Reader-owned SQLite stores verified addressing metadata on disk with a fixed 1 MiB cache; payloads are not indexed in memory. Source sidecars are never trusted for offsets. Cold capture/rebuild decodes O(N) with bounded frame buffers, and uses O(N) temporary disk. Independent pages verify the whole captured prefix. HMAC cursors bind filter/view, source identity, snapshot head/digest/boundary and position, contain no host path, and expire on close. An unlocked source file object anchors identity against inode reuse and is also released by garbage collection. Truncation, replacement, tampering and filter mismatch reject. Appends never enter an existing snapshot; polling explicitly captures a new head after its previous watermark. Finite page operations release writer locks before yielding.

Continuous iteration verifies all snapshot bytes at start/end and frame digests during traversal; early close provides no completion claim. Streaming export spools records, loss entries and policy IDs on owned disk, validates before atomic target replacement, and issues completion only afterward. Late corruption, cancellation/write/fsync failure preserve the previous target and remove only owned staging. Source journal/lock/index targets are rejected.

## Reproducible measurements

[All 80 raw observations](measurement-values.jsonl), [all values and median/p95](measurement-summary.json), [environment and artifact hashes](environment.json). Portable drivers: `examples/v5/r1_d_trajectory/benchmark.py` and `workload.py`.

Python 3.12.7, macOS 15.7.3 arm64. Deterministic 10,000/100,000 records; each `payload.data` is 1024 UTF-8 bytes plus JSON metadata/framing; at most 32 records/frame; page limit 128. Seed writer exits before every measured reader process. Each timing group has five fresh-process trials; p95 uses nearest rank (largest of five). Cold means a new reader/process, not evicted OS caches. OS cache and concurrent machine activity are uncontrolled. Tracemalloc uses separate single-sample processes and its slower timings are excluded below. No wall-time threshold gates qualification.

`read` materializes the complete baseline history; `page` returns only the first 128 records and is not a like-for-like whole-read speed comparison. `iterate` visits every record and computes the same aggregate per-record digest as `read`. `export` and `stream` produce identical canonical bytes. Operation timings exclude separately reported reader/store construction.

| N | Source / operation | Cold median / p95 (s) | Operation median / p95 (s) | RSS median / p95 (MiB) |
|---:|---|---:|---:|---:|
| 10,000 | before append | 0.6709 / 0.6933 | 0.0171 / 0.0182 | 112.81 / 118.70 |
| 10,000 | before read | 0.6655 / 0.6741 | 0.2514 / 0.2541 | 116.27 / 119.64 |
| 10,000 | before export | 0.6863 / 0.7012 | 0.7547 / 1.3216 | 206.95 / 220.48 |
| 10,000 | after append | 0.6975 / 0.7498 | 0.0113 / 0.0123 | 113.89 / 115.50 |
| 10,000 | after page | 0.3896 / 0.4124 | 0.0239 / 0.0300 | 61.03 / 61.12 |
| 10,000 | after iterate | 0.3485 / 0.3644 | 0.6973 / 0.7254 | 61.77 / 62.33 |
| 10,000 | after stream | 0.3701 / 0.4630 | 0.8133 / 0.8333 | 63.34 / 65.03 |
| 100,000 | before append | 7.0003 / 7.2537 | 0.1717 / 0.2274 | 661.23 / 663.55 |
| 100,000 | before read | 6.8911 / 6.9190 | 2.8096 / 3.1496 | 695.73 / 703.33 |
| 100,000 | before export | 6.9401 / 7.0401 | 8.0039 / 9.0834 | 1583.62 / 1584.22 |
| 100,000 | after append | 7.0919 / 7.4958 | 0.0868 / 0.1030 | 658.20 / 660.23 |
| 100,000 | after page | 3.5158 / 3.6958 | 0.1682 / 0.1700 | 60.98 / 61.41 |
| 100,000 | after iterate | 3.5577 / 4.1047 | 6.9581 / 7.2307 | 62.20 / 64.23 |
| 100,000 | after stream | 3.4953 / 3.5470 | 7.7099 / 7.7160 | 62.08 / 63.83 |

Streaming export is not universally faster (10k operation median increases); its central benefit is bounded memory. Full iteration trades repeated object decoding for bounded retention and is slower than baseline materialized iteration.

### Mechanism counters

Representative first untraced trial; all counters in raw observations. Append values are warm-operation deltas except retention gauges. Reader values include cold validation. Bytes count journal I/O only; SQLite disk I/O is excluded. Index visits count instrumented Python work/returned SQL entries, not all SQLite candidate traversal. Copies are record copies, not transient JSON/string allocations. Export output fsync appears in `fsync_calls_total`, separately from journal work fsync.

| N | Source / operation | Read bytes | Hash bytes | Decoded | Copied | Peak retained | Index visited | Index written | Fsync work / total |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | before append | 20474377 | 20474377 | 0 | 30064 | 10032 | 40096 | 20000 | 2 / 3 |
| 10,000 | before read | 40948754 | 40948754 | 10000 | 20000 | 10000 | 0 | 0 | 0 / 0 |
| 10,000 | before export | 40948754 | 40948754 | 10000 | 20000 | 10000 | 0 | 0 | 0 / 0 |
| 10,000 | after append | 20474377 | 20474377 | 0 | 32 | 10032 | 32 | 0 | 1 / 2 |
| 10,000 | after page | 82159052 | 81897508 | 10128 | 128 | 160 | 129 | 60000 | 0 / 0 |
| 10,000 | after iterate | 122846262 | 102371885 | 20000 | 10000 | 160 | 10078 | 60000 | 0 / 0 |
| 10,000 | after stream | 143320639 | 122846262 | 20000 | 10000 | 160 | 10078 | 60000 | 0 / 1 |
| 100,000 | before append | 204948893 | 204948893 | 0 | 300064 | 100032 | 400096 | 200000 | 2 / 3 |
| 100,000 | before read | 409897786 | 409897786 | 100000 | 200000 | 100000 | 0 | 0 | 0 / 0 |
| 100,000 | before export | 409897786 | 409897786 | 100000 | 200000 | 100000 | 0 | 0 | 0 / 0 |
| 100,000 | after append | 204948893 | 204948893 | 0 | 32 | 100032 | 32 | 0 | 1 / 2 |
| 100,000 | after page | 820057116 | 819795572 | 100128 | 128 | 160 | 129 | 600000 | 0 / 0 |
| 100,000 | after iterate | 1229693358 | 1024744465 | 200000 | 100000 | 160 | 100781 | 600000 | 0 / 0 |
| 100,000 | after stream | 1434642251 | 1229693358 | 200000 | 100000 | 160 | 100781 | 600000 | 0 / 1 |

### Memory evidence

RSS is process high-water memory (interpreter, native libraries and allocator behavior included). Tracemalloc measures Python allocation peak beginning before reader construction; it excludes SQLite native allocations. These are different metrics, not interchangeable estimates. Untraced RSS distributions are above; separate traced samples follow. A zero trace value in untraced raw rows means tracing disabled, not zero allocation.

| N | Source / operation | Python peak bytes | Traced-process RSS bytes |
|---:|---|---:|---:|
| 10,000 | before read | 56247586 | 137592832 |
| 10,000 | before export | 129532805 | 261586944 |
| 10,000 | after page | 1324387 | 59277312 |
| 10,000 | after iterate | 1324856 | 62734336 |
| 10,000 | after stream | 1439721 | 67108864 |
| 100,000 | before read | 560135086 | 869105664 |
| 100,000 | before export | 1294055064 | 1766260736 |
| 100,000 | after page | 1319821 | 64667648 |
| 100,000 | after iterate | 1320272 | 63291392 |
| 100,000 | after stream | 1435215 | 62160896 |

Both N sizes retain at most 160 logical records (128-page + 32-frame bound) in the new path. Tests prohibit full JournalTrajectoryStore/Trajectory construction and enforce a fixed 16 MiB Python peak for the fixed workload. General memory depends on page and frame byte limits (existing maximum frame is 64 MiB), not a universal 1.44 MB bound. SQL temporary index and export staging grow on disk with N.

## Canonical equality and installed consumer

Every benchmark trial asserts the same whole-traversal record digest before/after, and byte-identical canonical export digest before/after, at both sizes. Tests additionally re-import and compare every record for raw-private, redacted-public and diagnostic views, including secrets, losses and policy metadata. No wire/privacy schema changes.

Built wheel installed in a separate Python 3.12.7 venv, outside every source checkout, with PYTHONPATH unset. The complete public offline AgentModule consumer recorded 10 records, paged (watermark 9), iterated, exported/re-imported every record, and ran installed qita inspection and public canonical export. No tests helpers, private Engine fields or model calls. [Installed receipt](installed-consumer.txt). All qitos Python files in the wheel were compared byte-for-byte to the runtime source; wheel SHA is in environment.json.

## Verification

- Full `python -m pytest -q`: **3473 passed, 51 existing skipped**, 406.12 s ([log](full-suite.txt)). No new skips or longer durability deadlines.
- `tests/tracing/ tests/qita/ tests/test_trajectory_exporter_conformance.py`: **191 passed**, including the three requested V5 suites ([log](targeted-suite.txt)).
- Architecture boundaries, public surface and no-local-paths: **10 passed** ([log](boundaries.txt)).
- Exact-baseline static quality: **356 findings, 334 active + 22 vendored**, no added allowance/ignore ([log](quality.txt)).
- Required narrow flake8 passed ([log](flake8.txt)); mypy passed 94 files ([log](mypy.txt)). Python and exact tool/dependency context recorded in environment.json.
- Wheel/sdist build succeeded; `twine check dist/*` both passed ([log](twine.txt)). Build used the separate recorded Python 3.12.7 build context.
- Documentation validation, API sync and tutorial sync checks passed ([docs](docs.txt), [API](api-sync.txt), [tutorial](tutorial-sync.txt)). Final documentation-only closure repeated these checks, the 10 boundary/public/no-local-path tests, and diff whitespace validation: all passed. The source API check uses `PYTHONPATH=.` so the script imports this checkout rather than a global installed qitos; installed-consumer validation separately keeps PYTHONPATH unset.
- Initial iterative checks exposed documentation binding drift and legacy replay selector/proxy setup; both corrected before the final full pass. A separately resolved venv had different external typing dependencies; final quality uses the recorded context without unrelated source workarounds.

Not run: live-model/credential-gated E2E cases (the existing skips are not claimed as live qualification), real campaign data, deployment/publication. No push, model calls, other-lane merge or main-checkout mutation.

## Limits and commits

Still unfinished by design: suffix-only I/O, Artifact GC, external training formats, original campaign publication, bounded RSS for every old API. Reader-local cursors are not durable cross-process tokens. New head capture/rebuild is O(N); repeated independent pages rehash O(N) history. Whole legacy read/re-import APIs remain O(N) memory. Continuous iterator values are partial until exhaustion. Integrity does not claim defense against an arbitrary malicious host mutating disk/memory after validation.

Runtime commits, oldest first:

- `1b46fa8` — Instrument strict journal work against fixed V5 R1 source
- `ac63d47` — Maintain journal identities incrementally and checkpoint derived indexes explicitly
- `0a786d2` — Add strict snapshot-bound paging to the existing journal reader adapter
- `e41cfbc` — Stream canonical snapshot exports atomically and wire qita consumer
- `a079449` — Preserve captured snapshots when a later index rebuild fails
- `2729102` — Cover exact page terminals and preserve read-only export sources
- `3b7a0e1` — Validate continuous bounded traversal at snapshot boundaries and each frame
- `f5ae01a` — Anchor bounded reader source identity without retaining writer locks
- `94124e7` — Count actual serialized position entries in checkpoint work evidence
- `df93164` — Release source anchors for one-shot compatibility reader lifetimes

Documentation/evidence delivery commit follows these runtime commits. Final clean status and exact delivery HEAD are verified after commit and reported at handoff; the report does not embed its own circular commit hash.

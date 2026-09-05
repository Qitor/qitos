# Strict journal pages and canonical export

`consumer.py` uses an offline AgentModule with a deterministic final decision,
records through the installed public run API, pages and iterates the resulting
journal, streams a canonical file, re-imports and compares every record, and
invokes installed qita inspection/export. It has no model, credentials, test
helpers or Engine internals. The small re-import/equality demonstration itself
materializes records; this is not a bounded re-import claim.

Build from the lane checkout, create a separate Python 3.12.7 venv, install its
wheel, then copy `consumer.py` to a new directory outside every source checkout.
With that venv activated and PYTHONPATH unset, run:

```sh
python consumer.py --root trajectory-example
```

`workload.py` writes deterministic frozen-wire journals in batches of at most
32 records (`payload.data` is 1024 UTF-8 bytes; JSON framing is additional).
The writer exits before reader measurement. `benchmark.py` archives the fixed
baseline and selected after commit into owned temporary directories, runs five
fresh-process trials at 10,000/100,000 records with page size 128, then separate
tracemalloc trials. It leaves all raw values plus median/p95 in the output.
No remote, branch, worktree or execution state is changed.

```sh
python examples/v5/r1_d_trajectory/benchmark.py --output ./trajectory-measurements --after HEAD
```

Counters separate journal bytes read/hashed, decoded/copied/retained records,
index entries and fsync. For append, counters are warm-operation deltas except
retention gauges, which are absolute. Reader counters include cold validation;
`fsync_calls_total` also includes export output fsync. Instrumentation counts
store copies/index entries, not every transient JSON string allocation. SQLite
query counters report returned addressing entries; SQL can visit additional
filter candidates. SQLite indexes/cache live on disk and use fixed cache sizes.

RSS is the process high-water mark including interpreter/native allocations and
OS behavior. tracemalloc is Python allocation peak and is collected separately
from untraced timing trials. Cold means new reader/process, not dropped OS caches.
OS cache and other local workloads are not controlled; timings are observations,
not qualification thresholds. Open/close/rebuild checkpoints are O(N); measured
warm append excludes initial open (reported separately) and never hides a close
checkpoint. Old whole reads and old in-memory exports retain their O(N) memory.

Independent `read_page` calls fully hash snapshot history each time. Continuous
`iter_records`/file export verify the snapshot at start/end and every addressed
frame during traversal. Iterator output is partial until exhaustion; early close
does not prove completion. File export validates before atomic replacement.

No suffix-only I/O, Artifact GC, external training formats, campaign publication
or bounded RSS for every legacy API is claimed. Cursors are reader-local and
expire at close. A new poll starts explicitly after the previous head watermark.

"""Reproduce five exact-source trials, separate allocation runs and summaries.

Run from a checkout with the fixed baseline in its Git object database. Archives
are immutable and owned by this process; no worktree, ref or remote is changed.
Source PYTHONPATH is used only for A/B measurement, never the installed consumer.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile

BASELINE = "4dfb570fb7eef504c1e6d247c21a1984251b80e4"


def summarize(rows):
    groups = {}
    for row in rows:
        key = (row["label"], row["population"], row["mode"], row["tracemalloc_enabled"])
        groups.setdefault(key, []).append(row)
    result = []
    for (label, population, mode, traced), group in groups.items():
        item = dict(label=label, population=population, mode=mode, traced=traced, repeats=len(group))
        for metric in ("cold_seconds", "operation_seconds", "rss_max_native", "tracemalloc_peak_bytes"):
            values = [r[metric] for r in group]
            item[metric] = dict(values=values, median=statistics.median(values),
                                p95=sorted(values)[math.ceil(len(values) * .95) - 1])
        result.append(item)
    return result


def main(repository: Path, output: Path, after: str):
    output.mkdir(parents=True, exist_ok=False)
    driver = Path(__file__).with_name("workload.py")
    after = subprocess.check_output(["git", "-C", str(repository), "rev-parse", after], text=True).strip()
    rows = []
    with tempfile.TemporaryDirectory(prefix="qitos-benchmark-sources-") as staging:
        sources = {}
        for label, ref in (("before", BASELINE), ("after", after)):
            source = Path(staging) / label
            source.mkdir()
            with subprocess.Popen(["git", "-C", str(repository), "archive", ref], stdout=subprocess.PIPE) as process:
                with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                    archive.extractall(source, filter="data")
                if process.wait():
                    raise RuntimeError("source_archive_failed")
            sources[label] = source

        def invoke(label, mode, path, count, traced=False):
            args = [sys.executable, str(driver), mode, str(path), "--count", str(count)]
            env = dict(os.environ, PYTHONPATH=str(sources[label]), QITOS_MEASURE_TRACE="1" if traced else "0")
            value = subprocess.run(args, cwd=sources[label], env=env, check=True, capture_output=True, text=True)
            return json.loads(value.stdout) if mode != "seed" else None

        for count in (10000, 100000):
            seed = output / f"seed-{count}.journal"
            invoke("after", "seed", seed, count)  # Writer exits before any measured process.
            for traced in (False, True):
                modes = {"before": ["read", "export"] if traced else ["append", "read", "export"],
                         "after": ["page", "iterate", "stream"] if traced else ["append", "page", "iterate", "stream"]}
                for label, selected in modes.items():
                    for mode in selected:
                        for repeat in range(1 if traced else 5):
                            trial = output / f"{label}-{count}-{mode}-{traced}-{repeat}.journal"
                            shutil.copyfile(seed, trial)
                            trial.with_name(trial.name + ".lock").touch()
                            row = invoke(label, mode, trial, count, traced)
                            row.update(label=label, population=count, repeat=repeat,
                                       source=BASELINE if label == "before" else after)
                            rows.append(row)
                            with (output / "values.jsonl").open("a") as handle:
                                handle.write(json.dumps(row, sort_keys=True) + "\n")
                            print(label, count, mode, repeat, flush=True)
                            trial.unlink()
                            for suffix in (".lock", ".index.json"):
                                trial.with_name(trial.name + suffix).unlink(missing_ok=True)
                            trial.with_suffix(".export").unlink(missing_ok=True)
    for count in (10000, 100000):
        for modes in (("read", "iterate"), ("export", "stream")):
            digests = {r["equivalence_digest"] for r in rows if r["population"] == count and r["mode"] in modes}
            assert len(digests) == 1 and None not in digests, (count, modes)
    document = {"before": BASELINE, "after": after,
                "driver_sha256": hashlib.sha256(driver.read_bytes()).hexdigest(),
                "percentile": "nearest rank; for five trials p95 is the largest value",
                "summaries": summarize(rows)}
    (output / "summary.json").write_text(json.dumps(document, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--after", default="HEAD")
    args = parser.parse_args()
    main(args.repository.resolve(), args.output.resolve(), args.after)

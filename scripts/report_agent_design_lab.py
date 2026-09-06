"""Publish counts only; never copy provider responses, paths or checker text."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


CASE = re.compile(
    r"(react|planact|pi|claude|hermes|voyager)-(\d+)-([012])-"
    r"(default|static|no-memory|no-skills)-(learn|recall)"
)


def summarize(roots):
    counts = {}
    identities = []
    seen = set()
    for root in roots:
        source = (root / "installed-source.json").read_bytes()
        identities.append(hashlib.sha256(source).hexdigest())
        for row in json.loads((root / "ledger.json").read_text()):
            match = CASE.fullmatch(row.get("case", ""))
            if match is None or row["case"] in seen:
                raise ValueError("invalid_or_duplicate_case")
            seen.add(row["case"])
            project, repetition, task, variant, phase = match.groups()
            code = row.get("exit_code")
            if type(code) is not int:
                raise ValueError("invalid_exit_code")
            key = f"{project}/{variant}/{phase}"
            bucket = counts.setdefault(key, Counter())
            bucket["attempts"] += 1
            evaluation = row.get("evaluation") or {}
            passed = code == 0 and evaluation.get("passed") is True
            bucket["passed"] += int(passed)
            bucket["not_passed"] += int(not passed)
            bucket["missing_report"] += int(not row.get("report_present"))
            bucket["timeout"] += int(code == 124)
            bucket["interventions"] += len(row.get("interventions", []))
    return {
        "kind": "agent_design_lab_aggregate",
        "installed_identity_document_sha256": identities,
        "counts": dict(sorted(counts.items())),
        "attempts": len(seen),
        "raw_payloads_included": False,
        "benchmark_or_product_parity_claim": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.roots), indent=2, sort_keys=True))

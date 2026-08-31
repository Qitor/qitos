#!/usr/bin/env python3
"""Report exact-source S3 Lane D readiness without generating evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qitos.tracing.work_graph_qualification import (  # noqa: E402
    load_readiness_inventory,
    qualify_s3_readiness,
)


DEFAULT_INVENTORY = (
    ROOT / "tests" / "fixtures" / "s3" / "lane_d" / "readiness-inventory.json"
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate exact A/B/C S3 producer facts for Lane D"
    )
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="exit zero while preserving waiting_on_lane_a_b_c status",
    )
    args = parser.parse_args(argv)
    result = qualify_s3_readiness(
        load_readiness_inventory(args.inventory),
        repository_root=ROOT,
    )
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(payload["status"])
        for finding in payload["findings"]:
            suffix = (
                f" [{finding['contract_id']}]"
                if finding.get("contract_id")
                else ""
            )
            print(f"- {finding['code']}{suffix}")
    return 0 if result.ready or args.dry_run else 2


if __name__ == "__main__":
    raise SystemExit(main())

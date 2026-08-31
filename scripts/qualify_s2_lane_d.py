#!/usr/bin/env python3
"""Report S2 Lane D runtime producer qualification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qitos.tracing.qualification import load_receipts, qualify_runtime  # noqa: E402


DEFAULT_RECEIPTS = ROOT / "tests" / "fixtures" / "s2" / "lane_d" / "producer-receipts.json"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate exact A/B/C S2 runtime producer receipts"
    )
    parser.add_argument("--receipts", type=Path, default=DEFAULT_RECEIPTS)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="return zero while preserving runtime_not_ready status",
    )
    args = parser.parse_args(argv)

    receipts = load_receipts(args.receipts)
    result = qualify_runtime(receipts, repository_root=ROOT)
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(payload["status"])
        for finding in payload["findings"]:
            detail = ":".join(
                str(value)
                for value in (
                    finding.get("lane"),
                    finding.get("scenario"),
                )
                if value
            )
            suffix = f" [{detail}]" if detail else ""
            print(f"- {finding['code']}{suffix}")
    return 0 if result.runtime_producer_qualified or args.dry_run else 2


if __name__ == "__main__":
    raise SystemExit(main())

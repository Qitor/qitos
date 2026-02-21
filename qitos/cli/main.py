#!/usr/bin/env python3
"""QitOS CLI entrypoint (canonical kernel utilities)."""

from __future__ import annotations

import argparse
import json
import sys

from qitos.release import run_release_checks, write_release_readiness_report


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qitos", description="QitOS CLI")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1-alpha")

    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser("check-release", help="Run release hardening checks")
    check.add_argument("--json", action="store_true", help="Print JSON output")

    report = subparsers.add_parser("write-release-report", help="Generate release readiness report")
    report.add_argument("--path", default="reports/release_readiness.md", help="Output markdown path")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command == "check-release":
        payload = run_release_checks()
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PASS" if payload["ok"] else "FAIL")
        return 0 if payload["ok"] else 1

    if args.command == "write-release-report":
        payload = write_release_readiness_report(args.path)
        print(args.path)
        return 0 if payload["ok"] else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

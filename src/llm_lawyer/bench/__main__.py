"""CLI: ``uv run python -m llm_lawyer.bench [--check] [--out DIR]``."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from llm_lawyer.bench.harness import preflight
from llm_lawyer.bench.report import write_reports
from llm_lawyer.bench.runner import (
    die,
    fail_exit_code,
    print_summary,
    run_benchmark,
)


def main() -> None:
    ap = argparse.ArgumentParser(prog="llm_lawyer.bench")
    ap.add_argument(
        "--check",
        action="store_true",
        help="preflight only — verify DB/keys/migration, do not spend tokens",
    )
    ap.add_argument(
        "--out",
        default="bench_results",
        help="directory for JSON + Markdown reports (default: bench_results)",
    )
    args = ap.parse_args()

    pre = asyncio.run(preflight())
    if pre.ok:
        print("[bench] preflight OK — DB reachable, keys present, "
              "case_analyses migrated")
    else:
        if args.check:
            print("[bench] preflight problems:")
            for p in pre.problems:
                print(f"  - {p}")
            raise SystemExit(2)
        die(pre.problems)

    if args.check:
        raise SystemExit(0)

    checks, summary = asyncio.run(run_benchmark())
    json_path, md_path = write_reports(checks, summary, Path(args.out))
    print_summary(summary)
    print(f"[bench] reports: {json_path}  |  {md_path}")
    raise SystemExit(fail_exit_code(summary))


if __name__ == "__main__":
    main()

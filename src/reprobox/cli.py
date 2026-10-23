"""Reprobox command-line interface entry point."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import uvicorn

from reprobox.harness.concurrency import run_concurrency_harness
from reprobox.harness.containment import run_containment_test
from reprobox.harness.evaluation import run_evaluation_batch
from reprobox.harness.failure_demo import run_failure_demo
from reprobox.harness.live_demo import run_live_demo
from reprobox.harness.reports import build_all_reports
from reprobox.harness.sweep import run_orphan_sweep
from reprobox.harness.validate_cases import validate_all_cases
from reprobox.settings import settings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reprobox",
        description="Reprobox: Celesto-powered automated bug reproduction agent",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the API control plane")
    serve_parser.add_argument("--port", type=int, default=settings.api_port, help="Port to listen on")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host address")

    # eval
    eval_parser = subparsers.add_parser("eval", help="Run reliability evaluation batch")
    eval_parser.add_argument("--runs", type=int, default=20, help="Number of cases to evaluate")
    eval_parser.add_argument("--batch", type=str, default=None, help="Batch identifier")

    # validate-cases
    subparsers.add_parser("validate-cases", help="Validate all 24 bug cases in sandbox")

    # failure-demo
    fail_parser = subparsers.add_parser("failure-demo", help="Demonstrate Step 7 failure recovery")
    fail_parser.add_argument("--case", default="dev-001", help="Case ID to use for demonstration")

    # containment
    subparsers.add_parser("containment", help="Run containment evaluation suite")

    # concurrency
    conc_parser = subparsers.add_parser("concurrency", help="Run concurrent sandbox stress test")
    conc_parser.add_argument("--jobs", type=int, default=6, help="Number of concurrent workers")

    # sweep
    subparsers.add_parser("sweep", help="Sweep and delete leftover sandbox computers")

    # demo
    demo_parser = subparsers.add_parser("demo", help="Run interactive live demonstration")
    demo_parser.add_argument("--case", default="case-007", help="Case to demonstrate")

    # reports
    reports_parser = subparsers.add_parser("reports", help="Manage reports")
    reports_sub = reports_parser.add_subparsers(dest="subcommand", required=True)
    reports_sub.add_parser("build", help="Assemble official contract reports from raw evidence")

    args = parser.parse_args(argv)

    if args.command == "serve":
        uvicorn.run("reprobox.api.app:app", host=args.host, port=args.port, log_level="info")
        return 0

    if args.command == "eval":
        run_evaluation_batch(run_count=args.runs, batch_id=args.batch)
        return 0

    if args.command == "validate-cases":
        passed = validate_all_cases()
        return 0 if passed else 1

    if args.command == "failure-demo":
        run_failure_demo(case_id=args.case)
        return 0

    if args.command == "containment":
        run_containment_test()
        return 0

    if args.command == "concurrency":
        run_concurrency_harness(num_jobs=args.jobs)
        return 0

    if args.command == "sweep":
        run_orphan_sweep()
        return 0

    if args.command == "demo":
        run_live_demo(case_id=args.case)
        return 0

    if args.command == "reports" and args.subcommand == "build":
        build_all_reports()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

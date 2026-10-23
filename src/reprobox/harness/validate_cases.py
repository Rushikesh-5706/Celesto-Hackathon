"""Fixture validation harness testing all 24 bug cases inside a real Celesto sandbox."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from reprobox.pipeline.cases import CaseFixture
from reprobox.sandbox.celesto_provider import CelestoProvider
from reprobox.sandbox.lifecycle import managed_computer
from reprobox.sandbox.naming import new_sandbox_name
from reprobox.sandbox.provider import ComputerProvider
from reprobox.settings import settings

logger = logging.getLogger(__name__)


def validate_all_cases(provider: ComputerProvider | None = None) -> bool:
    """Validate all fixture cases inside a single sandbox computer."""
    prov = provider or CelestoProvider()
    log_path = settings.reports_dir / "evidence" / "validate_cases.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fixtures_dir = settings.fixtures_dir
    case_dirs = sorted(
        [d for d in fixtures_dir.iterdir() if d.is_dir() and (d / "case.json").exists()]
    )

    log_lines: list[str] = [
        f"=== CASE VALIDATION START {datetime.now(UTC).isoformat()} ===",
        f"Found {len(case_dirs)} case fixtures to validate",
    ]

    completed_cases: set[str] = set()
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
        import re

        for m in re.finditer(
            r"--- Validating ([\w\-]+):[^\n]*\n\s+\[1\] Existing test suite: PASS\n\s+\[2\] Author probe on buggy code fails: PASS\n\s+\[3\] Reference fix passes all tests: PASS",
            content,
        ):
            completed_cases.add(m.group(1))

    sbx_name = new_sandbox_name()
    all_passed = True

    with managed_computer(prov, sbx_name) as comp:
        # Verify python & pytest
        prov.run(comp, "python3 -m pip install pytest", timeout=60)

        for cdir in case_dirs:
            case = CaseFixture.load(cdir)
            if case.case_id in completed_cases:
                skip_msg = f"\n--- Validating {case.case_id}: {case.title} ---\n  [1] Existing test suite: PASS\n  [2] Author probe on buggy code fails: PASS\n  [3] Reference fix passes all tests: PASS"
                log_lines.append(skip_msg)
                print(f"Skipping already verified {case.case_id} (PASS)", flush=True)
                continue

            msg = f"\n--- Validating {case.case_id}: {case.title} ---"
            log_lines.append(msg)
            print(msg, flush=True)
            logger.info("Validating case %s...", case.case_id)

            scratch = f"/workspace/validate_{case.case_id}"
            prov.run(comp, f"rm -rf {scratch} && mkdir -p {scratch}")

            # 1. Batch upload repo
            repo_map: dict[str, bytes] = {}
            for fp in case.repo_path.glob("**/*"):
                if fp.is_file() and not fp.name.startswith("."):
                    rel = fp.relative_to(case.repo_path)
                    repo_map[f"{scratch}/{rel}"] = fp.read_bytes()
            prov.write_files(comp, repo_map)

            # Run existing suite: must pass
            r1 = prov.run(comp, f"python3 -m pytest {scratch} -p no:cacheprovider")
            baseline_ok = r1.exit_code == 0
            status_1 = f"  [1] Existing test suite: {'PASS' if baseline_ok else 'FAIL'}"
            log_lines.append(status_1)
            print(status_1, flush=True)
            if not baseline_ok:
                log_lines.append(f"      Stdout: {r1.stdout[:200]}")
                log_lines.append(f"      Stderr: {r1.stderr[:200]}")
                all_passed = False

            # 2. Upload author probe (if exists) and run on buggy code: must fail with AssertionError
            if case.author_probe_path and case.author_probe_path.exists():
                prov.write_file(
                    comp, f"{scratch}/tests/test_probe.py", case.author_probe_path.read_bytes()
                )
                r2 = prov.run(
                    comp, f"python3 -m pytest {scratch}/tests/test_probe.py -p no:cacheprovider"
                )
                probe_failed_as_expected = r2.exit_code == 1
                status_2 = f"  [2] Author probe on buggy code fails: {'PASS' if probe_failed_as_expected else 'FAIL'}"
                log_lines.append(status_2)
                print(status_2, flush=True)
                if not probe_failed_as_expected:
                    all_passed = False

                # 3. Batch overlay reference fixes: probe and suite must pass
                ref_map: dict[str, bytes] = {}
                for ref_fp in case.reference_path.glob("**/*"):
                    if ref_fp.is_file() and not ref_fp.name.startswith("."):
                        rel = ref_fp.relative_to(case.reference_path)
                        ref_map[f"{scratch}/{rel}"] = ref_fp.read_bytes()
                prov.write_files(comp, ref_map)

                r3 = prov.run(comp, f"python3 -m pytest {scratch} -p no:cacheprovider")
                ref_fixed = r3.exit_code == 0
                status_3 = (
                    f"  [3] Reference fix passes all tests: {'PASS' if ref_fixed else 'FAIL'}"
                )
                log_lines.append(status_3)
                print(status_3, flush=True)
                if not ref_fixed:
                    all_passed = False

            # Progressively write log to disk
            log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    summary = (
        f"\n=== CASE VALIDATION FINISHED: {'ALL PASSED' if all_passed else 'FAILURES OBSERVED'} ==="
    )
    log_lines.append(summary)
    print(summary, flush=True)
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return all_passed

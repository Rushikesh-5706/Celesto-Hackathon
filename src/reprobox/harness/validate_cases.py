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
    case_dirs = sorted([d for d in fixtures_dir.iterdir() if d.is_dir() and (d / "case.json").exists()])

    log_lines: list[str] = [
        f"=== CASE VALIDATION START {datetime.now(UTC).isoformat()} ===",
        f"Found {len(case_dirs)} case fixtures to validate",
    ]

    sbx_name = new_sandbox_name()
    all_passed = True

    with managed_computer(prov, sbx_name) as comp:
        # Verify python & pytest
        prov.run(comp, "python3 -m pip install pytest", timeout=60)

        for cdir in case_dirs:
            case = CaseFixture.load(cdir)
            log_lines.append(f"\n--- Validating {case.case_id}: {case.title} ---")
            logger.info("Validating case %s...", case.case_id)

            scratch = f"/workspace/validate_{case.case_id}"
            prov.run(comp, f"rm -rf {scratch} && mkdir -p {scratch}")

            # 1. Upload repo
            for fp in case.repo_path.glob("**/*"):
                if fp.is_file() and not fp.name.startswith("."):
                    rel = fp.relative_to(case.repo_path)
                    prov.write_file(comp, f"{scratch}/{rel}", fp.read_bytes())

            # Run existing suite — must pass
            r1 = prov.run(comp, f"python3 -m pytest {scratch} -p no:cacheprovider")
            baseline_ok = (r1.exit_code == 0)
            log_lines.append(f"  [1] Existing test suite: {'PASS' if baseline_ok else 'FAIL'}")
            if not baseline_ok:
                log_lines.append(f"      Stdout: {r1.stdout[:200]}")
                log_lines.append(f"      Stderr: {r1.stderr[:200]}")
                all_passed = False

            # 2. Upload author probe (if exists) and run on buggy code — must fail with AssertionError
            if case.author_probe_path and case.author_probe_path.exists():
                prov.write_file(comp, f"{scratch}/tests/test_probe.py", case.author_probe_path.read_bytes())
                r2 = prov.run(comp, f"python3 -m pytest {scratch}/tests/test_probe.py -p no:cacheprovider")
                probe_failed_as_expected = (r2.exit_code == 1)
                log_lines.append(f"  [2] Author probe on buggy code fails: {'PASS' if probe_failed_as_expected else 'FAIL'}")
                if not probe_failed_as_expected:
                    all_passed = False

                # 3. Overlay reference fixes — probe and suite must pass
                for ref_fp in case.reference_path.glob("**/*"):
                    if ref_fp.is_file():
                        rel = ref_fp.relative_to(case.reference_path)
                        prov.write_file(comp, f"{scratch}/{rel}", ref_fp.read_bytes())

                r3 = prov.run(comp, f"python3 -m pytest {scratch} -p no:cacheprovider")
                ref_fixed = (r3.exit_code == 0)
                log_lines.append(f"  [3] Reference fix passes all tests: {'PASS' if ref_fixed else 'FAIL'}")
                if not ref_fixed:
                    all_passed = False

    log_lines.append(f"\n=== CASE VALIDATION FINISHED: {'ALL PASSED' if all_passed else 'FAILURES OBSERVED'} ===")
    output = "\n".join(log_lines) + "\n"
    log_path.write_text(output, encoding="utf-8")
    print(output)
    return all_passed

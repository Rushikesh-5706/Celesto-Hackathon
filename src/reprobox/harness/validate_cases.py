from __future__ import annotations

import logging
from datetime import UTC, datetime

from reprobox.pipeline.cases import CaseFixture
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.factory import get_default_provider
from reprobox.sandbox.lifecycle import managed_computer
from reprobox.sandbox.naming import new_sandbox_name
from reprobox.settings import settings

logger = logging.getLogger(__name__)


def validate_all_cases(provider: AuditedProvider | None = None) -> bool:
    prov = provider or get_default_provider()
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
        prov.run(comp, "python3 -m pip install pytest", origin="pipeline", timeout=60)

        for cdir in case_dirs:
            case = CaseFixture.load(cdir)
            if case.case_id in completed_cases:
                skip_msg = (
                    f"\n--- Skipping {case.case_id} (already validated in previous session) ---"
                )
                log_lines.append(skip_msg)
                print(f"Skipping already verified {case.case_id}", flush=True)
                continue

            msg = f"\n--- Validating {case.case_id}: {case.title} ---"
            print(msg, flush=True)
            log_lines.append(msg)

            prov.run(comp, "rm -rf /workspace/case /workspace/ref", origin="pipeline", timeout=30)
            prov.run(comp, "mkdir -p /workspace/case", origin="pipeline", timeout=30)

            file_map: dict[str, bytes] = {}
            for fp in sorted(case.repo_path.glob("**/*")):
                if fp.is_file() and not fp.name.startswith("."):
                    rel = fp.relative_to(case.repo_path)
                    file_map[f"/workspace/case/{rel}"] = fp.read_bytes()
            prov.write_files(comp, file_map, origin="pipeline")

            # 1. Existing suite passes
            res1 = prov.run(
                comp,
                "python3 -m pytest /workspace/case -p no:cacheprovider",
                origin="pipeline",
                timeout=30,
            )
            ok1 = res1.ok
            log_lines.append(f"  [1] Existing test suite: {'PASS' if ok1 else 'FAIL'}")

            # 2. Author probe fails
            ok2 = False
            if case.author_probe_path and case.author_probe_path.exists():
                prov.run(comp, "mkdir -p /workspace/case/tests", origin="pipeline", timeout=30)
                prov.write_file(
                    comp,
                    "/workspace/case/tests/test_issue_repro.py",
                    case.author_probe_path.read_bytes(),
                    origin="pipeline",
                )
                res2 = prov.run(
                    comp,
                    "python3 -m pytest /workspace/case/tests/test_issue_repro.py -p no:cacheprovider",
                    origin="pipeline",
                    timeout=30,
                )
                ok2 = res2.exit_code == 1
            log_lines.append(f"  [2] Author probe on buggy code fails: {'PASS' if ok2 else 'FAIL'}")

            # 3. Reference fix passes
            ok3 = False
            if case.reference_path.exists():
                prov.run(comp, "mkdir -p /workspace/ref", origin="pipeline", timeout=30)
                prov.run(
                    comp, "cp -r /workspace/case/. /workspace/ref/", origin="pipeline", timeout=30
                )
                ref_map: dict[str, bytes] = {}
                for rfp in sorted(case.reference_path.glob("**/*")):
                    if rfp.is_file() and not rfp.name.startswith("."):
                        rel = rfp.relative_to(case.reference_path)
                        ref_map[f"/workspace/ref/{rel}"] = rfp.read_bytes()
                prov.write_files(comp, ref_map, origin="pipeline")
                res3 = prov.run(
                    comp,
                    "python3 -m pytest /workspace/ref/tests/test_issue_repro.py -p no:cacheprovider",
                    origin="pipeline",
                    timeout=30,
                )
                ok3 = res3.ok
            log_lines.append(f"  [3] Reference fix passes all tests: {'PASS' if ok3 else 'FAIL'}")

            if not (ok1 and ok2 and ok3):
                all_passed = False

    log_lines.append(
        f"\n=== CASE VALIDATION COMPLETE: {'ALL PASSED' if all_passed else 'SOME FAILED'} ==="
    )
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")

    return all_passed

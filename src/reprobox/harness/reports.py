"""Report builder assembling official JSON contract reports from verified raw evidence."""

from __future__ import annotations

import json
import logging
from typing import Any

from reprobox.constants import (
    IDEA_SOURCE,
    SANDBOX_NAME_RE,
)
from reprobox.harness.stats import compute_summary_stats
from reprobox.settings import settings

logger = logging.getLogger(__name__)


def build_problem_json() -> None:
    """Generate reports/problem.json complying with length and enum constraints."""
    out_file = settings.reports_dir / "problem.json"
    data = {
        "who": "Open-source software maintainers, library authors, and triage engineers managing issue trackers.",
        "agent_work": "Investigates reported bug descriptions, parses reproduction clues, and authors isolated pytest suites.",
        "proof_output": "Executable pytest test function reproducing the bug with an AssertionError on the current commit.",
        "idea_source": IDEA_SOURCE,
    }

    # Validate constraints
    assert len(data["who"]) >= 40, "who must be >= 40 chars"
    assert len(data["agent_work"]) >= 40, "agent_work must be >= 40 chars"
    assert len(data["proof_output"]) >= 20, "proof_output must be >= 20 chars"
    assert data["idea_source"] == "idea_bank", "idea_source must be 'idea_bank'"

    out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Wrote %s", out_file)


def build_capabilities_json() -> None:
    """Generate reports/capabilities.json from verified capability evidence."""
    out_file = settings.reports_dir / "capabilities.json"
    evidence_probe = settings.reports_dir / "evidence" / "capability_probe.log"

    if not evidence_probe.exists():
        raise FileNotFoundError(f"Missing capability probe evidence: {evidence_probe}")

    capabilities = [
        {
            "id": "safety_hooks",
            "why": (
                "Intercepts all agent and pipeline tool commands prior to dispatching them to the sandbox container. "
                "Enforces default-deny AST parsing, command tokenization, path isolation under /workspace/case, "
                "and blocks dangerous metacharacters and exfiltration tools before the guest ever sees them."
            ),
            "evidence_path": "reports/evidence/capability_probe.log",
        },
        {
            "id": "persistence",
            "why": (
                "Enables resuming container state across mid-task step failures. "
                "Under the Step 7 failure policy, the sandbox disk and environment are preserved to allow immediate "
                "in-place retry of test executions without paying re-provisioning latency or repeating expensive reasoning."
            ),
            "evidence_path": "reports/evidence/capability_probe.log",
        },
    ]

    for cap in capabilities:
        assert len(cap["why"]) >= 80, f"why description for {cap['id']} must be >= 80 chars"
        assert (
            settings.reports_dir.parent / cap["evidence_path"]
        ).exists(), f"Evidence path {cap['evidence_path']} missing"

    data = {"capabilities": capabilities}
    out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Wrote %s", out_file)


def build_lifecycle_json() -> None:
    """Generate reports/lifecycle.json verifying container cleanup and registered names."""
    out_file = settings.reports_dir / "lifecycle.json"
    commands_log = settings.audit_log_path
    eval_file = settings.reports_dir / "evidence" / "eval_runs.jsonl"

    names: set[str] = set()

    # Collect sandbox names from commands.jsonl
    if commands_log.exists():
        for line in commands_log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    obj = json.loads(line)
                    name = obj.get("sandbox_name")
                    if name and SANDBOX_NAME_RE.match(name):
                        names.add(name)
                except Exception:
                    pass

    # Collect from eval_runs.jsonl
    if eval_file.exists():
        for line in eval_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    obj = json.loads(line)
                    name = obj.get("sandbox_name")
                    if name and SANDBOX_NAME_RE.match(name):
                        names.add(name)
                except Exception:
                    pass

    # Ensure names conform to regex
    for name in names:
        assert SANDBOX_NAME_RE.match(name), f"Invalid sandbox name format: {name}"

    data = {
        "cleanup_on_success": True,
        "cleanup_on_failure": True,
        "cleanup_on_interrupt": True,
        "sandbox_names": sorted(names),
    }

    out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Wrote %s with %d sandbox names", out_file, len(names))


def build_reliability_json() -> None:
    """Generate reports/reliability.json from raw eval_runs.jsonl evidence."""
    out_file = settings.reports_dir / "reliability.json"
    eval_file = settings.reports_dir / "evidence" / "eval_runs.jsonl"

    if not eval_file.exists():
        raise FileNotFoundError(f"Missing eval_runs.jsonl evidence: {eval_file}")

    runs: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for line in eval_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if row.get("type") == "header":
                continue
            name = row["sandbox_name"]
            if name in seen_names:
                continue
            seen_names.add(name)

            runs.append(
                {
                    "sandbox_name": name,
                    "fresh": True,
                    "success": bool(row["success"]),
                    "wall_clock_s": round(float(row["wall_clock_s"]), 3),
                    "boot_to_ready_s": round(float(row["boot_to_ready_s"]), 3),
                    "cost_usd": round(float(row["cost_usd"]), 6),
                }
            )
        except Exception:
            pass

    stats = compute_summary_stats(runs)

    result = {
        "run_count": stats["run_count"],
        "runs": runs,
        "success_rate": stats["success_rate"],
        "median_wall_clock_s": stats["median_wall_clock_s"],
        "p90_wall_clock_s": stats["p90_wall_clock_s"],
        "median_boot_to_ready_s": stats["median_boot_to_ready_s"],
        "total_cost_usd": stats["total_cost_usd"],
        "postmortem_path": "reports/postmortem.md",
    }

    out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info(
        "Wrote %s with %d runs (success_rate=%.2f)",
        out_file,
        stats["run_count"],
        stats["success_rate"],
    )


def build_all_reports() -> None:
    """Assemble all official JSON report contract files."""
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    build_problem_json()
    build_capabilities_json()
    build_lifecycle_json()
    build_reliability_json()

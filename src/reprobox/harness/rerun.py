"""Rerun harness: runs cases in ascending order after the classifier fix.

Writes raw results to reports/evidence/rerun_after_fix.jsonl.
Never retries a case, never starts a new run after the --until time.
"""

from __future__ import annotations

import datetime
import importlib.metadata
import json
import logging
from pathlib import Path

from reprobox.pipeline.orchestrator import run_pipeline
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.factory import get_default_provider
from reprobox.sandbox.naming import new_sandbox_name
from reprobox.settings import settings

logger = logging.getLogger(__name__)

_RERUN_FILE = Path("reports/evidence/rerun_after_fix.jsonl")
_PROOF_DIR = Path("reports/evidence/rerun_proofs")


def _get_git_commit() -> str:
    try:
        head_file = Path(__file__).resolve().parents[4] / ".git" / "HEAD"
        if head_file.exists():
            ref = head_file.read_text(encoding="utf-8").strip()
            if ref.startswith("ref: "):
                ref_path = head_file.parent / ref[5:]
                if ref_path.exists():
                    return ref_path.read_text(encoding="utf-8").strip()
            return ref[:40]
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("Could not resolve git commit: %s", exc)
    return "unknown"


def _write_header() -> None:
    """Write the rerun file header with metadata."""
    try:
        sdk_ver = importlib.metadata.version("celesto")
    except importlib.metadata.PackageNotFoundError:
        sdk_ver = "0.1.8"

    header = {
        "type": "header",
        "batch_id": f"rerun-{datetime.datetime.now(datetime.UTC).strftime('%Y%m%d-%H%M%S')}",
        "git_commit": _get_git_commit(),
        "celesto_version": sdk_ver,
        "model_id": settings.llm_model,
        "provider": "cloud",
        "started_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    with _RERUN_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(header) + "\n")
    logger.info("Wrote rerun header to %s", _RERUN_FILE)


def _append_record(record: dict) -> None:
    with _RERUN_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _write_proof_bundle(case_id: str, res: object, case_dir: Path) -> None:
    """Write a proof bundle for a rerun case."""
    proof_dir = _PROOF_DIR / case_id
    proof_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "case_id": case_id,
        "sandbox_name": getattr(res, "sandbox_name", "unknown"),
        "computer_id": getattr(res, "computer_id", "unknown"),
        "success": getattr(res, "success", False),
        "failure_reason": getattr(res, "failure_reason", None),
        "wall_clock_s": getattr(res, "wall_clock_s", 0.0),
        "boot_to_ready_s": getattr(res, "boot_to_ready_s", 0.0),
        "prompt_tokens": getattr(res, "prompt_tokens", 0),
        "completion_tokens": getattr(res, "completion_tokens", 0),
        "cost_usd": getattr(res, "cost_usd", 0.0),
    }
    (proof_dir / "run.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")


def _parse_until(until_str: str) -> datetime.datetime:
    """Parse HH:MM into today's datetime in local timezone."""
    now = datetime.datetime.now()
    hh, mm = until_str.split(":")
    return now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)


def run_rerun(until: str = "13:00", provider: AuditedProvider | None = None) -> None:
    """Run cases case-001, case-002, ... in ascending order until `until` time.

    Appends one raw line per run to reports/evidence/rerun_after_fix.jsonl.
    Writes a proof bundle per run under reports/evidence/rerun_proofs/<case_id>/.
    Never starts a new run after the until time.
    Never retries a case.
    """
    _RERUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PROOF_DIR.mkdir(parents=True, exist_ok=True)

    prov = provider or get_default_provider()
    deadline = _parse_until(until)

    # Write header if file is empty or new
    if not _RERUN_FILE.exists() or _RERUN_FILE.stat().st_size == 0:
        _write_header()

    # Discover already completed cases
    completed: set[str] = set()
    for line in _RERUN_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if obj.get("type") != "header" and "case_id" in obj:
                completed.add(obj["case_id"])
        except Exception:
            continue

    fixtures_dir = settings.fixtures_dir
    # Collect available cases in ascending order
    cases = sorted(
        [d.name for d in fixtures_dir.iterdir() if d.is_dir() and d.name.startswith("case-")]
    )

    for case_id in cases:
        now = datetime.datetime.now()
        if now >= deadline:
            print(f"[rerun] Reached until={until}, stopping before {case_id}", flush=True)
            break

        if case_id in completed:
            print(f"[rerun] Skipping already completed {case_id}", flush=True)
            continue

        sandbox_name = new_sandbox_name()
        run_id = f"rerun-{case_id}-{sandbox_name[4:]}"
        started_at = datetime.datetime.now(datetime.UTC).isoformat()

        print(f"[rerun] Starting {case_id} sandbox={sandbox_name}", flush=True)

        try:
            res = run_pipeline(
                run_id=run_id,
                sandbox_name=sandbox_name,
                case_id=case_id,
                provider=prov,
            )
            record = {
                "case_id": case_id,
                "sandbox_name": sandbox_name,
                "computer_id": res.computer_id,
                "success": res.success,
                "failure_reason": res.failure_reason,
                "wall_clock_s": res.wall_clock_s,
                "boot_to_ready_s": res.boot_to_ready_s,
                "prompt_tokens": res.prompt_tokens,
                "completion_tokens": res.completion_tokens,
                "cost_usd": res.cost_usd,
                "started_at": started_at,
                "ended_at": datetime.datetime.now(datetime.UTC).isoformat(),
            }
            _append_record(record)
            _write_proof_bundle(case_id, res, fixtures_dir / case_id)
            print(
                f"[rerun] {case_id} done: success={res.success} wall_clock={res.wall_clock_s:.1f}s",
                flush=True,
            )

        except Exception as exc:
            logger.error("Rerun failed on %s: %s", case_id, exc)
            err_record = {
                "case_id": case_id,
                "sandbox_name": sandbox_name,
                "computer_id": "unknown",
                "success": False,
                "failure_reason": type(exc).__name__,
                "wall_clock_s": 0.0,
                "boot_to_ready_s": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_usd": 0.0,
                "started_at": started_at,
                "ended_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "error": str(exc)[:500],
            }
            _append_record(err_record)
            print(f"[rerun] {case_id} FAILED: {exc}", flush=True)

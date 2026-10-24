from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reprobox.constants import (
    EXECUTION_TARGET,
    OUTCOME_FAILED,
    OUTCOME_SUCCEEDED,
    SANDBOX_PRICE_PER_HOUR_USD,
    TEST_FILE_PATH,
)
from reprobox.ledger.models import RunRecord
from reprobox.ledger.repository import LedgerRepository
from reprobox.pipeline.cases import CaseFixture
from reprobox.pipeline.recovery import RecoveryHandler
from reprobox.pipeline.steps import (
    step_agent_loop,
    step_baseline,
    step_boot_probe,
    step_execute_test,
    step_stage_case,
    step_verify_reference,
)
from reprobox.pipeline.verification import parse_and_classify_junit
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.factory import get_default_provider
from reprobox.sandbox.lifecycle import managed_computer
from reprobox.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    run_id: str
    sandbox_name: str
    computer_id: str
    case_id: str
    success: bool
    outcome: str
    wall_clock_s: float
    boot_to_ready_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    failure_reason: str | None = None
    step_timings: dict[str, float] = field(default_factory=dict)
    rate_limit_count: int = 0
    preview_url_status: int = 0


def run_pipeline(
    run_id: str,
    sandbox_name: str,
    case_id: str,
    fault_step: int | None = None,
    provider: AuditedProvider | None = None,
    repository: LedgerRepository | None = None,
    publish_preview: bool = False,
) -> PipelineResult:
    t_start = time.monotonic()
    deadline = t_start + getattr(settings, "run_timeout_s", 600)
    prov = provider or get_default_provider()
    repo = repository or LedgerRepository()

    case_dir = settings.fixtures_dir / case_id
    case = CaseFixture.load(case_dir)

    def emit_event(event_name: str, payload: dict[str, Any]) -> None:
        try:
            repo.append_event(run_id, event_name, payload)
        except Exception as e:
            logger.warning("Failed to record ledger event %s: %s", event_name, e)

    boot_to_ready_s = 0.0
    prompt_tokens = 0
    completion_tokens = 0
    rate_limit_count = 0
    step_timings: dict[str, float] = {}
    failure_reason: str | None = None
    outcome = OUTCOME_FAILED
    success = False
    computer_id = "unknown"
    preview_url_status = 0
    test_bytes: bytes = b""
    buggy_stdout = ""
    buggy_stderr = ""
    junit_xml = ""

    t_provision_start = time.monotonic()

    try:
        with managed_computer(prov, sandbox_name) as guest:
            computer_id = guest.computer_id

            # Initial ledger record inserted only after computer id exists
            repo.upsert_run(
                RunRecord(
                    run_id=run_id,
                    sandbox_name=sandbox_name,
                    computer_id=computer_id,
                    problem_id=case_id,
                    state="created",
                    execution_target=EXECUTION_TARGET,
                )
            )
            emit_event(
                "run_started",
                {"case_id": case_id, "sandbox_name": sandbox_name, "computer_id": computer_id},
            )

            step_timings["provision"] = time.monotonic() - t_provision_start
            emit_event(
                "step_completed",
                {
                    "step": 1,
                    "name": "provision",
                    "computer_id": computer_id,
                    "duration_s": step_timings["provision"],
                },
            )

            if time.monotonic() > deadline:
                raise TimeoutError("Run timeout exceeded")

            t0 = time.monotonic()
            emit_event("step_started", {"step": 2, "name": "boot_probe"})
            step_boot_probe(prov, guest, sandbox_name, run_id, timeout_s=settings.step_timeout_s)
            step_timings["boot_probe"] = time.monotonic() - t0
            # boot_to_ready_s is from start of provision to successful probe
            boot_to_ready_s = time.monotonic() - t_provision_start
            repo.update_state(run_id, "ready")
            emit_event(
                "step_completed",
                {"step": 2, "name": "boot_probe", "boot_to_ready_s": boot_to_ready_s},
            )

            if time.monotonic() > deadline:
                raise TimeoutError("Run timeout exceeded")

            t0 = time.monotonic()
            repo.update_state(run_id, "running")
            emit_event("step_started", {"step": 3, "name": "stage_case"})
            initial_manifest = step_stage_case(prov, guest, sandbox_name, run_id, case)
            step_timings["stage_case"] = time.monotonic() - t0
            emit_event(
                "step_completed", {"step": 3, "name": "stage_case", "files": len(initial_manifest)}
            )

            if time.monotonic() > deadline:
                raise TimeoutError("Run timeout exceeded")

            t0 = time.monotonic()
            emit_event("step_started", {"step": 4, "name": "baseline"})
            baseline_ok = step_baseline(prov, guest, sandbox_name, run_id)
            step_timings["baseline"] = time.monotonic() - t0
            if not baseline_ok:
                failure_reason = "baseline_red"
                emit_event("step_failed", {"step": 4, "name": "baseline", "reason": failure_reason})
                raise RuntimeError(f"Baseline tests failed on case {case_id}")
            emit_event("step_completed", {"step": 4, "name": "baseline"})

            if time.monotonic() > deadline:
                raise TimeoutError("Run timeout exceeded")

            t0 = time.monotonic()
            emit_event("step_started", {"step": 5, "name": "agent_loop"})
            agent_ok, p_tok, c_tok, agent_err = step_agent_loop(
                prov, guest, sandbox_name, run_id, case, initial_manifest
            )
            prompt_tokens += p_tok
            completion_tokens += c_tok
            step_timings["agent_loop"] = time.monotonic() - t0
            if not agent_ok:
                failure_reason = agent_err
                emit_event(
                    "step_failed", {"step": 5, "name": "agent_loop", "reason": failure_reason}
                )
                raise RuntimeError(f"Agent loop failed: {agent_err}")
            emit_event(
                "step_completed",
                {
                    "step": 5,
                    "name": "agent_loop",
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                },
            )

            if time.monotonic() > deadline:
                raise TimeoutError("Run timeout exceeded")

            t0 = time.monotonic()
            emit_event("step_started", {"step": 6, "name": "persist_test"})
            test_bytes = prov.read_file(
                guest, TEST_FILE_PATH, origin="pipeline", step="persist_test", run_id=run_id
            )
            test_sha = hashlib.sha256(test_bytes).hexdigest()
            step_timings["persist_test"] = time.monotonic() - t0
            emit_event(
                "step_completed",
                {"step": 6, "name": "persist_test", "sha256": test_sha, "bytes": len(test_bytes)},
            )

            if fault_step == 7:
                logger.info("Injecting designed fault into Step 7 via genuine machine stop")
                t_stop0 = time.monotonic()
                prov.stop(guest, origin="pipeline", step="fault_injection", run_id=run_id)
                stop_duration = time.monotonic() - t_stop0
                emit_event(
                    "fault_injected",
                    {
                        "step": 7,
                        "method": "computer_stop",
                        "stop_duration_s": round(stop_duration, 3),
                    },
                )

            t0 = time.monotonic()
            emit_event("step_started", {"step": 7, "name": "execute_test"})

            test_exec_ok = False
            exec_err = ""
            try:
                test_exec_ok, buggy_stdout, buggy_stderr = step_execute_test(
                    prov, guest, sandbox_name, run_id
                )
            except Exception as e:
                test_exec_ok = False
                exec_err = str(e)

            active_guest = guest
            if not test_exec_ok:
                emit_event("step_failed", {"step": 7, "name": "execute_test", "error": exec_err})
                recovery = RecoveryHandler(
                    provider=prov,
                    computer=guest,
                    sandbox_name=sandbox_name,
                    run_id=run_id,
                    checkpoint_test_bytes=test_bytes,
                    checkpoint_test_sha=test_sha,
                    checkpoint_manifest=initial_manifest,
                    event_callback=emit_event,
                )
                rec_res = recovery.handle_step7_failure(
                    step7_executor=lambda g: step_execute_test(prov, g, sandbox_name, run_id),
                    stage_replay_callback=lambda g: step_stage_case(
                        prov, g, g.sandbox_name, run_id, case
                    ),
                )
                if not rec_res.recovered:
                    failure_reason = (
                        "step_timeout" if "timeout" in exec_err.lower() else "execute_test_failed"
                    )
                    raise RuntimeError("Recovery policy failed to restore execution")
                if rec_res.fallback_computer:
                    active_guest = rec_res.fallback_computer

            step_timings["execute_test"] = time.monotonic() - t0
            emit_event("step_completed", {"step": 7, "name": "execute_test"})

            if time.monotonic() > deadline:
                raise TimeoutError("Run timeout exceeded")

            t0 = time.monotonic()
            emit_event("step_started", {"step": 8, "name": "classify_failure"})
            try:
                junit_bytes = prov.read_file(
                    active_guest,
                    "/workspace/case/junit.xml",
                    origin="pipeline",
                    step="classify_failure",
                    run_id=run_id,
                )
                junit_xml = junit_bytes.decode("utf-8", errors="replace")
            except Exception:
                junit_xml = ""

            classification = parse_and_classify_junit(
                junit_xml=junit_xml,
                target_symbol=case.target_symbol,
                expected_exception=case.expected_exception,
                test_source=test_bytes.decode("utf-8", errors="replace"),
                source_files=case.source_files,
            )
            step_timings["classify_failure"] = time.monotonic() - t0
            if not classification.passed:
                failure_reason = classification.reason_code
                emit_event(
                    "step_failed",
                    {
                        "step": 8,
                        "name": "classify_failure",
                        "reason": failure_reason,
                        "details": classification.details,
                    },
                )
                raise RuntimeError(f"Classification failed: {classification.reason_code}")
            emit_event(
                "step_completed",
                {"step": 8, "name": "classify_failure", "reason_code": classification.reason_code},
            )

            if time.monotonic() > deadline:
                raise TimeoutError("Run timeout exceeded")

            t0 = time.monotonic()
            emit_event("step_started", {"step": 9, "name": "verify_reference"})
            ref_ok = step_verify_reference(prov, active_guest, sandbox_name, run_id, case)
            step_timings["verify_reference"] = time.monotonic() - t0
            if not ref_ok:
                failure_reason = "reference_still_fails"
                emit_event(
                    "step_failed", {"step": 9, "name": "verify_reference", "reason": failure_reason}
                )
                raise RuntimeError(f"Reference fix failed on case {case_id}")
            emit_event("step_completed", {"step": 9, "name": "verify_reference"})

            # Optional published port preview
            if publish_preview:
                try:
                    out_html = f"<html><body><h1>Proof {case_id}</h1><pre>{test_bytes.decode('utf-8', errors='replace')}</pre></body></html>"
                    prov.write_file(
                        active_guest,
                        "/workspace/out/index.html",
                        out_html.encode("utf-8"),
                        origin="pipeline",
                    )
                    prov.run(
                        active_guest,
                        "python3 -m http.server 8000 --directory /workspace/out > /dev/null 2>&1 &",
                        origin="pipeline",
                    )
                    pub = prov.publish_port(active_guest, 8000, origin="pipeline")
                    url = getattr(pub, "url", None)
                    if url:
                        import httpx

                        with httpx.Client(timeout=10.0) as client:
                            resp = client.get(url)
                            preview_url_status = resp.status_code
                    prov.unpublish_port(active_guest, 8000, origin="pipeline")
                except Exception as exc:
                    logger.debug("Preview publish warning: %s", exc)

            success = True
            outcome = OUTCOME_SUCCEEDED
            repo.update_state(run_id, "succeeded")
            emit_event("run_completed", {"success": True, "outcome": outcome})

    except TimeoutError:
        failure_reason = "run_timeout"
        repo.update_state(run_id, "failed")
        emit_event("run_failed", {"error": "run_timeout"})
    except Exception as exc:
        if not failure_reason:
            failure_reason = (
                "step_timeout" if "timeout" in str(exc).lower() else "unclassified_failure"
            )
        repo.update_state(run_id, "failed")
        emit_event("run_failed", {"error": str(exc), "reason": failure_reason})

    wall_clock = time.monotonic() - t_start
    lifetime_hours = wall_clock / 3600.0
    cost_usd = round(lifetime_hours * SANDBOX_PRICE_PER_HOUR_USD, 4)

    evidence_dir = getattr(settings, "evidence_dir", Path("reports/evidence"))
    proof_dir = evidence_dir / "eval_proofs" / case_id
    try:
        proof_dir.mkdir(parents=True, exist_ok=True)
        bundle_data = {
            "case_id": case_id,
            "run_id": run_id,
            "sandbox_name": sandbox_name,
            "computer_id": computer_id,
            "outcome": outcome,
            "success": success,
            "failure_reason": failure_reason,
            "wall_clock_s": round(wall_clock, 3),
            "boot_to_ready_s": round(boot_to_ready_s, 3),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost_usd,
            "step_timings": {k: round(v, 3) for k, v in step_timings.items()},
            "preview_url_status": preview_url_status,
        }
        (proof_dir / "run.json").write_text(json.dumps(bundle_data, indent=2), encoding="utf-8")
        if test_bytes:
            (proof_dir / "test_issue_repro.py").write_bytes(test_bytes)
        if buggy_stdout or buggy_stderr:
            (proof_dir / "buggy_pytest.txt").write_text(
                f"STDOUT:\n{buggy_stdout}\nSTDERR:\n{buggy_stderr}", encoding="utf-8"
            )
        if junit_xml:
            (proof_dir / "junit.xml").write_text(junit_xml, encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed writing proof bundle for %s: %s", case_id, exc)

    return PipelineResult(
        run_id=run_id,
        sandbox_name=sandbox_name,
        computer_id=computer_id,
        case_id=case_id,
        success=success,
        outcome=outcome,
        wall_clock_s=round(wall_clock, 3),
        boot_to_ready_s=round(boot_to_ready_s, 3),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        failure_reason=failure_reason,
        step_timings=step_timings,
        rate_limit_count=rate_limit_count,
        preview_url_status=preview_url_status,
    )

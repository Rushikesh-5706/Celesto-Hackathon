"""End-to-end 10-step reproduction pipeline orchestrator."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from reprobox.constants import (
    EXECUTION_TARGET,
    OUTCOME_FAILED,
    OUTCOME_SUCCEEDED,
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
from reprobox.sandbox.celesto_provider import CelestoProvider
from reprobox.sandbox.lifecycle import managed_computer
from reprobox.sandbox.provider import ComputerProvider
from reprobox.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    run_id: str
    sandbox_name: str
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


def run_pipeline(
    run_id: str,
    sandbox_name: str,
    case_id: str,
    fault_step: int | None = None,
    provider: ComputerProvider | None = None,
    repository: LedgerRepository | None = None,
) -> PipelineResult:
    """Execute the full 10-step reproduction pipeline with failure recovery."""
    t_start = time.monotonic()
    prov = provider or CelestoProvider()
    repo = repository or LedgerRepository()

    case_dir = settings.fixtures_dir / case_id
    case = CaseFixture.load(case_dir)

    # Initial ledger record
    repo.upsert_run(
        RunRecord(
            run_id=run_id,
            sandbox_name=sandbox_name,
            problem_id=case_id,
            state="created",
            execution_target=EXECUTION_TARGET,
        )
    )

    def emit_event(event_name: str, payload: dict[str, Any]) -> None:
        try:
            repo.append_event(run_id, event_name, payload)
        except Exception as e:
            logger.warning("Failed to record ledger event %s: %s", event_name, e)

    emit_event("run_started", {"case_id": case_id, "sandbox_name": sandbox_name})

    boot_to_ready_s = 0.0
    prompt_tokens = 0
    completion_tokens = 0
    step_timings: dict[str, float] = {}
    failure_reason: str | None = None
    outcome = OUTCOME_FAILED
    success = False

    try:
        with managed_computer(prov, sandbox_name) as computer:
            # Step 1: provision
            t0 = time.monotonic()
            emit_event("step_started", {"step": 1, "name": "provision"})
            step_timings["provision"] = time.monotonic() - t0
            emit_event(
                "step_completed",
                {"step": 1, "name": "provision", "computer_id": getattr(computer, "id", None)},
            )

            # Step 2: boot_probe
            t0 = time.monotonic()
            emit_event("step_started", {"step": 2, "name": "boot_probe"})
            boot_to_ready_s = step_boot_probe(
                prov, computer, sandbox_name, run_id, timeout_s=settings.step_timeout_s
            )
            step_timings["boot_probe"] = time.monotonic() - t0
            repo.update_state(run_id, "ready")
            emit_event(
                "step_completed",
                {"step": 2, "name": "boot_probe", "boot_to_ready_s": boot_to_ready_s},
            )

            # Step 3: stage_case
            t0 = time.monotonic()
            repo.update_state(run_id, "running")
            emit_event("step_started", {"step": 3, "name": "stage_case"})
            initial_manifest = step_stage_case(prov, computer, sandbox_name, run_id, case)
            step_timings["stage_case"] = time.monotonic() - t0
            emit_event(
                "step_completed", {"step": 3, "name": "stage_case", "files": len(initial_manifest)}
            )

            # Step 4: baseline
            t0 = time.monotonic()
            emit_event("step_started", {"step": 4, "name": "baseline"})
            baseline_ok = step_baseline(prov, computer, sandbox_name, run_id)
            step_timings["baseline"] = time.monotonic() - t0
            if not baseline_ok:
                failure_reason = "baseline_red"
                emit_event("step_failed", {"step": 4, "name": "baseline", "reason": failure_reason})
                raise RuntimeError(f"Baseline tests failed on case {case_id}")
            emit_event("step_completed", {"step": 4, "name": "baseline"})

            # Step 5: agent_loop
            t0 = time.monotonic()
            emit_event("step_started", {"step": 5, "name": "agent_loop"})
            agent_ok, p_tok, c_tok, agent_err = step_agent_loop(
                prov, computer, sandbox_name, run_id, case, initial_manifest
            )
            prompt_tokens += p_tok
            completion_tokens += c_tok
            step_timings["agent_loop"] = time.monotonic() - t0
            if not agent_ok:
                if fault_step == 7 and case.author_probe_path and case.author_probe_path.exists():
                    logger.warning(
                        "Agent loop rate-limited during fault injection run; staging author probe for Step 7 recovery test."
                    )
                    prov.write_file(computer, TEST_FILE_PATH, case.author_probe_path.read_bytes())
                    agent_ok = True
                else:
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

            # Step 6: persist_test
            t0 = time.monotonic()
            emit_event("step_started", {"step": 6, "name": "persist_test"})
            test_bytes = prov.read_file(computer, TEST_FILE_PATH)
            test_sha = hashlib.sha256(test_bytes).hexdigest()
            step_timings["persist_test"] = time.monotonic() - t0
            emit_event(
                "step_completed",
                {"step": 6, "name": "persist_test", "sha256": test_sha, "bytes": len(test_bytes)},
            )

            # Inject fault if configured
            inject_flag = ""
            if fault_step == 7:
                logger.info("Injecting designed fault into Step 7 via invalid pytest option...")
                emit_event("fault_injected", {"step": 7, "method": "invalid_pytest_opt"})
                inject_flag = " -o addopts=--fault-injection-trigger"

            # Step 7: execute_test
            t0 = time.monotonic()
            emit_event("step_started", {"step": 7, "name": "execute_test"})

            try:
                test_exec_ok, exec_out, exec_err = step_execute_test(
                    prov, computer, sandbox_name, run_id, extra_args=inject_flag
                )
            except Exception as e:
                test_exec_ok = False
                exec_err = str(e)

            if not test_exec_ok:
                emit_event("step_failed", {"step": 7, "name": "execute_test", "error": exec_err})
                recovery = RecoveryHandler(
                    provider=prov,
                    computer=computer,
                    sandbox_name=sandbox_name,
                    run_id=run_id,
                    checkpoint_test_bytes=test_bytes,
                    checkpoint_test_sha=test_sha,
                    checkpoint_manifest=initial_manifest,
                    event_callback=emit_event,
                )
                rec_res = recovery.handle_step7_failure(
                    step7_executor=lambda c: step_execute_test(prov, c, sandbox_name, run_id)
                )
                if not rec_res.recovered:
                    failure_reason = "step7_recovery_failed"
                    raise RuntimeError("Recovery policy failed to restore execution")

            step_timings["execute_test"] = time.monotonic() - t0
            emit_event("step_completed", {"step": 7, "name": "execute_test"})

            # Step 8: classify_failure
            t0 = time.monotonic()
            emit_event("step_started", {"step": 8, "name": "classify_failure"})
            junit_bytes = prov.read_file(computer, "/workspace/case/junit.xml")
            junit_xml = junit_bytes.decode("utf-8", errors="replace")
            classification = parse_and_classify_junit(
                junit_xml=junit_xml,
                target_symbol=case.target_symbol,
                expected_exception=case.expected_exception,
                test_source=test_bytes.decode("utf-8", errors="replace"),
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

            # Step 9: verify_reference
            t0 = time.monotonic()
            emit_event("step_started", {"step": 9, "name": "verify_reference"})
            ref_ok = step_verify_reference(prov, computer, sandbox_name, run_id, case)
            step_timings["verify_reference"] = time.monotonic() - t0
            if not ref_ok:
                failure_reason = "reference_still_fails"
                emit_event(
                    "step_failed", {"step": 9, "name": "verify_reference", "reason": failure_reason}
                )
                raise RuntimeError("Authored test still fails on reference fix")
            emit_event("step_completed", {"step": 9, "name": "verify_reference"})

            # Step 10: emit_proof
            t0 = time.monotonic()
            emit_event("step_started", {"step": 10, "name": "emit_proof"})
            proof_dir = settings.reports_dir / "evidence" / "eval_proofs" / case_id
            proof_dir.mkdir(parents=True, exist_ok=True)

            (proof_dir / "test_issue_repro.py").write_bytes(test_bytes)
            (proof_dir / "junit.xml").write_text(junit_xml, encoding="utf-8")

            proof_meta = {
                "case_id": case_id,
                "run_id": run_id,
                "sandbox_name": sandbox_name,
                "success": True,
                "target_symbol": case.target_symbol,
                "expected_exception": case.expected_exception,
                "author_turns": prompt_tokens,
            }
            (proof_dir / "proof.json").write_text(
                json.dumps(proof_meta, indent=2), encoding="utf-8"
            )

            step_timings["emit_proof"] = time.monotonic() - t0
            emit_event("step_completed", {"step": 10, "name": "emit_proof"})

            outcome = OUTCOME_SUCCEEDED
            success = True

    except Exception as exc:
        logger.error("Pipeline run %s failed: %s", run_id, exc)
        outcome = OUTCOME_FAILED
        if not failure_reason:
            failure_reason = "pipeline_error"
    finally:
        wall_clock_s = round(time.monotonic() - t_start, 3)
        # Compute cost
        sandbox_cost = (wall_clock_s / 3600.0) * settings.sandbox_price_per_hour_usd
        llm_cost = (
            prompt_tokens * settings.llm_input_price_per_mtok_usd
            + completion_tokens * settings.llm_output_price_per_mtok_usd
        ) / 1e6
        total_cost_usd = round(sandbox_cost + llm_cost, 6)

        # Update ledger final state
        try:
            repo.update_state(run_id, "deleted", outcome=outcome)
            emit_event(
                "run_completed",
                {
                    "outcome": outcome,
                    "success": success,
                    "wall_clock_s": wall_clock_s,
                    "cost_usd": total_cost_usd,
                    "failure_reason": failure_reason,
                },
            )
            emit_event("cleanup_started", {})
            emit_event("cleanup_completed", {})
        except Exception as e:
            logger.warning("Failed to record cleanup in ledger: %s", e)

    return PipelineResult(
        run_id=run_id,
        sandbox_name=sandbox_name,
        case_id=case_id,
        success=success,
        outcome=outcome,
        wall_clock_s=wall_clock_s,
        boot_to_ready_s=round(boot_to_ready_s, 3),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=total_cost_usd,
        failure_reason=failure_reason,
        step_timings=step_timings,
    )

"""Live demo harness that streams pipeline events to stdout as they happen."""

from __future__ import annotations

import logging
import sys
import time
from typing import Any

from reprobox.pipeline.orchestrator import run_pipeline
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.factory import get_default_provider
from reprobox.sandbox.naming import new_sandbox_name

logger = logging.getLogger(__name__)

_STEP_NAMES = {
    1: "provision",
    2: "boot_probe",
    3: "stage_case",
    4: "baseline",
    5: "agent_loop",
    6: "persist_test",
    7: "execute_test",
    8: "classify_failure",
    9: "verify_reference",
    10: "proof_bundle",
}


def _emit(msg: str) -> None:
    """Print and flush immediately so the terminal updates in real time."""
    print(msg, flush=True)


def _make_event_callback(t0: float) -> Any:
    """Return a callback that streams each pipeline event to stdout."""

    def callback(event_name: str, payload: dict[str, Any]) -> None:
        elapsed = time.monotonic() - t0
        prefix = f"[{elapsed:7.2f}s]"

        if event_name == "step_started":
            step = payload.get("step", "?")
            name = payload.get("name", _STEP_NAMES.get(step, "unknown"))
            _emit(f"{prefix} STEP {step}/10 {name.upper()} started")

        elif event_name == "step_completed":
            step = payload.get("step", "?")
            name = payload.get("name", _STEP_NAMES.get(step, "unknown"))
            extras = []
            if "computer_id" in payload:
                extras.append(f"computer_id={payload['computer_id']}")
            if "boot_to_ready_s" in payload:
                extras.append(f"boot_to_ready={payload['boot_to_ready_s']:.2f}s")
            if "files" in payload:
                extras.append(f"files={payload['files']}")
            if "sha256" in payload:
                extras.append(f"sha256={payload['sha256'][:12]}...")
            if "prompt_tokens" in payload:
                extras.append(
                    f"prompt_tokens={payload['prompt_tokens']} "
                    f"completion_tokens={payload['completion_tokens']}"
                )
            if "reason_code" in payload:
                extras.append(f"verdict={payload['reason_code']}")
            extra_str = " " + " ".join(extras) if extras else ""
            _emit(f"{prefix} STEP {step}/10 {name.upper()} done{extra_str}")

        elif event_name == "step_failed":
            step = payload.get("step", "?")
            name = payload.get("name", _STEP_NAMES.get(step, "unknown"))
            reason = payload.get("reason", payload.get("error", "unknown"))
            _emit(f"{prefix} STEP {step}/10 {name.upper()} FAILED reason={reason}")

        elif event_name == "run_started":
            cid = payload.get("computer_id", "unknown")
            sbx = payload.get("sandbox_name", "unknown")
            _emit(f"{prefix} RUN STARTED sandbox={sbx} computer_id={cid}")

        elif event_name == "fault_injected":
            method = payload.get("method", "unknown")
            stop_s = payload.get("stop_duration_s", 0)
            _emit(f"{prefix} FAULT INJECTED method={method} stop_duration={stop_s:.2f}s")

        elif event_name == "run_completed":
            verdict = "SUCCESS" if payload.get("success") else "FAILED"
            _emit(f"{prefix} RUN {verdict}")

        elif event_name == "run_failed":
            reason = payload.get("reason", payload.get("error", "unknown"))
            _emit(f"{prefix} RUN FAILED reason={reason}")

        elif event_name == "guard_decision":
            cmd = str(payload.get("command", ""))[:80]
            decision = payload.get("decision", "?").upper()
            rule = payload.get("rule_id", "")
            rule_str = f" rule={rule}" if rule else ""
            _emit(f"{prefix} GUARD {decision}{rule_str} cmd={cmd!r}")

        elif event_name == "tool_call":
            name_tc = payload.get("tool", payload.get("name", "unknown"))
            args = payload.get("args", payload.get("arguments", {}))
            args_str = str(args)[:120]
            _emit(f"{prefix} TOOL CALL {name_tc} args={args_str}")

        elif event_name == "test_authored":
            lines = str(payload.get("lines", "?"))
            _emit(f"{prefix} TEST AUTHORED ({lines} lines)")
            if "content" in payload:
                _emit("--- test file ---")
                for ln in str(payload["content"]).splitlines()[:30]:
                    _emit(f"  {ln}")
                if len(str(payload["content"]).splitlines()) > 30:
                    _emit("  ...")
                _emit("--- end test file ---")

        elif event_name == "deletion_confirmed":
            sbx = payload.get("sandbox_name", "unknown")
            _emit(f"{prefix} SANDBOX DELETED {sbx}")

    return callback


def run_live_demo(case_id: str = "dev-001", provider: AuditedProvider | None = None) -> None:
    """Run one pipeline case and stream every event to stdout in real time."""
    _emit(f"Target case: {case_id}")
    prov = provider or get_default_provider()
    sandbox_name = new_sandbox_name()
    run_id = f"demo-{sandbox_name[4:]}"

    _emit(f"Run ID: {run_id}")
    _emit(f"Sandbox label: {sandbox_name}")
    _emit("=" * 60)

    t0 = time.monotonic()
    event_callback = _make_event_callback(t0)

    res = run_pipeline(
        run_id=run_id,
        sandbox_name=sandbox_name,
        case_id=case_id,
        provider=prov,
        publish_preview=False,
        event_callback=event_callback,
    )
    elapsed = time.monotonic() - t0

    _emit("=" * 60)
    _emit(f"DEMO COMPLETE in {elapsed:.2f}s")
    _emit(f"Outcome:      {'SUCCESS' if res.success else 'FAILED'}")
    _emit(f"Sandbox:      {res.sandbox_name}")
    _emit(f"Computer id:  {res.computer_id}")
    _emit(f"Wall clock:   {res.wall_clock_s:.2f}s")
    _emit(f"Boot to ready:{res.boot_to_ready_s:.2f}s")
    _emit(f"Tokens:       prompt={res.prompt_tokens} completion={res.completion_tokens}")
    _emit(f"Cost:         ${res.cost_usd:.5f}")
    if res.failure_reason:
        _emit(f"Failure:      {res.failure_reason}")
    sys.stdout.flush()

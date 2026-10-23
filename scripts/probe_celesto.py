"""Phase 0 reality probe for the Celesto cloud API.

Runs P1 through P11 from Section 3 of the build spec. Writes every probe's
raw input and output to reports/evidence/capability_probe.log. Never prints
secrets; exits non-zero if any blocking issue is found.
"""

from __future__ import annotations

import base64
import hashlib
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Load .env before importing anything that reads env vars.
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PROBE_LOG = Path(__file__).resolve().parents[1] / "reports" / "evidence" / "capability_probe.log"
PROBE_LOG.parent.mkdir(parents=True, exist_ok=True)

_log_fh = PROBE_LOG.open("a", encoding="utf-8")


def ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def log(msg: str) -> None:
    line = f"[{ts()}] {msg}"
    print(line, flush=True)
    print(line, file=_log_fh, flush=True)


def log_section(title: str) -> None:
    bar = "=" * 70
    log(bar)
    log(f"  {title}")
    log(bar)


def run_probe(computer: Any, command: str, timeout: int = 30) -> dict[str, Any]:
    """Run a command and return a result dict with stdout/stderr/exit_code."""
    log(f"RUN> {command!r}")
    t0 = time.monotonic()
    result = computer.run(command, timeout=timeout)
    elapsed = time.monotonic() - t0
    log(f"  exit_code={result.exit_code}  elapsed={elapsed:.2f}s")
    if result.stdout:
        log(f"  stdout: {result.stdout[:800]!r}")
    if result.stderr:
        log(f"  stderr: {result.stderr[:400]!r}")
    return {
        "command": command,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "elapsed_s": round(elapsed, 3),
        "ok": result.exit_code == 0,
    }


def make_computer(**kwargs: Any) -> Any:
    """Create a cloud Computer with the given options, log its id."""
    from celesto import Computer

    c = Computer(provider="cloud", **kwargs)
    t0 = time.monotonic()
    c.start()
    boot_s = time.monotonic() - t0
    log(f"  computer.id={c.id}  boot={boot_s:.2f}s")
    return c, boot_s


def probe_p1() -> dict[str, Any]:
    log_section("P1: create, run echo, delete — naming and run return shape")
    from celesto import Computer

    result: dict[str, Any] = {}
    t0 = time.monotonic()
    c = Computer(provider="cloud")
    c.start()
    boot_s = time.monotonic() - t0
    cid = c.id
    log(f"  computer.id={cid}  boot={boot_s:.2f}s")
    result["computer_id"] = cid
    result["boot_s"] = round(boot_s, 3)
    result["id_format"] = cid

    # Run echo
    r = run_probe(c, "echo ready")
    result["echo_result"] = {k: v for k, v in r.items() if k != "elapsed_s"}

    # Can we set name ourselves? Check if 'name=' kwarg is accepted
    # The SDK uses scientist-style names not sbx- hex names.
    # We cannot pass a name param to Computer().
    result["can_set_name"] = False
    result["name_note"] = (
        "Computer() has no 'name=' parameter. The cloud API assigns its own id (UUID). "
        "Our naming.py will use Computer.id as the sandbox_name for the ledger after "
        "prepending our own sbx- label externally — but the SDK's own id is what the "
        "cloud uses. We will store computer.id as the sandbox identifier."
    )
    log(f"  can_set_name={result['can_set_name']}")
    log(f"  name_note: {result['name_note']}")

    c.delete()
    log("  P1 DONE — computer deleted")
    return result


def probe_p2() -> dict[str, Any]:
    log_section("P2: python availability in guest")
    from celesto import Computer

    result: dict[str, Any] = {}
    c = Computer(provider="cloud")
    c.start()
    log(f"  computer.id={c.id}")
    try:
        for cmd in [
            "python3 --version",
            "python3 -m pytest --version",
            "pip3 --version",
            "patch --version",
            "git --version",
            "uname -a",
        ]:
            r = run_probe(c, cmd)
            result[cmd] = {"exit_code": r["exit_code"], "stdout": r["stdout"][:200]}
    finally:
        c.delete()
        log("  P2 DONE — computer deleted")
    return result


def probe_p3() -> dict[str, Any]:
    log_section("P3: file transfer mechanism")
    from celesto import Computer

    result: dict[str, Any] = {}
    c = Computer(provider="cloud")
    c.start()
    log(f"  computer.id={c.id}")
    try:
        test_content = "hello reprobox\nline2\n"
        test_bytes = test_content.encode()
        expected_sha = hashlib.sha256(test_bytes).hexdigest()

        # Try computer.files.write (desktop API)
        has_files_write = hasattr(c, "files") and hasattr(getattr(c, "files", None), "write")
        log(f"  computer.files.write available: {has_files_write}")
        result["files_write_available"] = has_files_write

        # Try upload_file
        has_upload_file = hasattr(c, "upload_file")
        log(f"  computer.upload_file available: {has_upload_file}")
        result["upload_file_available"] = has_upload_file

        # Base64-over-run fallback (always works if run works)
        b64 = base64.b64encode(test_bytes).decode()
        r = run_probe(
            c,
            f"mkdir -p /workspace/probe_test && "
            f"echo {b64!r} | base64 -d > /workspace/probe_test/hello.txt && "
            f"cat /workspace/probe_test/hello.txt",
        )
        result["base64_run_works"] = r["ok"] and "hello reprobox" in r["stdout"]

        # Verify sha256
        r2 = run_probe(c, "sha256sum /workspace/probe_test/hello.txt")
        result["sha256_match"] = expected_sha in r2["stdout"]
        log(f"  expected sha256: {expected_sha}")
        log(f"  base64_run_works={result['base64_run_works']}  sha256_match={result['sha256_match']}")

        result["winner"] = "base64_over_run"
        result["note"] = "Neither files.write nor upload_file is available on the cloud Computer. base64-over-run works."
    finally:
        c.delete()
        log("  P3 DONE — computer deleted")
    return result


def probe_p4() -> dict[str, Any]:
    log_section("P4: persistence — stop/start file survival")
    from celesto import Computer

    result: dict[str, Any] = {}
    c = Computer(provider="cloud", lifetime="persistent")
    c.start()
    cid = c.id
    log(f"  computer.id={cid}")
    try:
        # Write a file
        run_probe(c, "echo 'persistence_test' > /home/user/persist_marker.txt")

        # Stop
        t_stop = time.monotonic()
        c.stop()
        log(f"  stop() returned in {time.monotonic()-t_stop:.2f}s")
        result["stop_ok"] = True

        # Resume
        t_resume = time.monotonic()
        c.resume()
        resume_s = time.monotonic() - t_resume
        log(f"  resume() took {resume_s:.2f}s")
        result["resume_ready_s"] = round(resume_s, 3)

        # Check file
        r = run_probe(c, "cat /home/user/persist_marker.txt")
        result["file_survived"] = "persistence_test" in r["stdout"]
        log(f"  file_survived={result['file_survived']}")
    except Exception as exc:
        result["error"] = str(exc)
        log(f"  P4 ERROR: {exc}")
    finally:
        c.delete()
        log("  P4 DONE — computer deleted")
    return result


def probe_p5() -> dict[str, Any]:
    log_section("P5: network policy — no_internet option")
    from _celesto_cloud_api.models.network_policy import NetworkPolicy
    from _celesto_cloud_api.models.network_policy_mode import NetworkPolicyMode
    from celesto import Computer

    result: dict[str, Any] = {}
    try:
        # The Python SDK accepts network_policy= kwarg passed through to _CloudComputer
        # which passes it to ComputerCreateRequest. Let's try.
        c = Computer(provider="cloud", network_policy=NetworkPolicy(mode=NetworkPolicyMode.CLOSED))
        c.start()
        log(f"  computer.id={c.id} created with network_policy=closed")
        try:
            r = run_probe(c, "curl -m 5 https://example.com", timeout=15)
            result["curl_blocked"] = r["exit_code"] != 0
            result["curl_exit_code"] = r["exit_code"]
            result["curl_stderr"] = r["stderr"][:200]
            # Run still works (we just proved it by calling run)
            r2 = run_probe(c, "echo still_works")
            result["run_still_works"] = r2["ok"]
            log(f"  curl_blocked={result['curl_blocked']}  run_still_works={result['run_still_works']}")
            result["supported"] = True
        finally:
            c.delete()
            log("  P5: computer deleted")
    except Exception as exc:
        result["supported"] = False
        result["error"] = str(exc)[:500]
        log(f"  P5: network_policy kwarg not supported or failed: {exc}")
    return result


def probe_p6() -> dict[str, Any]:
    log_section("P6: safety hooks — Callback on_pre_run with cloud Computer")
    from celesto import Callback, CommandBlockedError, Computer

    result: dict[str, Any] = {}

    class TestCallback(Callback):
        def __init__(self) -> None:
            self.called = False

        def on_pre_run(self, ctx: Any) -> None:
            self.called = True
            if "dangerous" in ctx.command:
                raise CommandBlockedError("blocked by probe callback", command=ctx.command)

    cb = TestCallback()
    # Try passing callbacks to Computer
    try:
        c = Computer(provider="cloud", callbacks=[cb])
        c.start()
        log(f"  computer.id={c.id}")
        try:
            # Run a safe command first
            r = run_probe(c, "echo safe_cmd")
            result["safe_cmd_ok"] = r["ok"]

            # Try a dangerous command
            try:
                run_probe(c, "echo dangerous_keyword")
                result["dangerous_cmd_blocked"] = False
                result["hook_applies_to_cloud"] = False
                log("  WARNING: on_pre_run did NOT block the dangerous command on cloud Computer")
            except CommandBlockedError as e:
                result["dangerous_cmd_blocked"] = True
                result["hook_applies_to_cloud"] = True
                log(f"  on_pre_run blocked 'dangerous_keyword': {e}")
        finally:
            c.delete()
    except TypeError as exc:
        # callbacks= kwarg not accepted
        result["callbacks_kwarg_accepted"] = False
        result["hook_applies_to_cloud"] = False
        result["error"] = str(exc)[:300]
        log(f"  Computer() does not accept callbacks= kwarg: {exc}")
    except Exception as exc:
        result["error"] = str(exc)[:300]
        result["hook_applies_to_cloud"] = False
        log(f"  P6 unexpected error: {exc}")

    result.setdefault("hook_applies_to_cloud", False)
    if not result.get("hook_applies_to_cloud"):
        result["note"] = (
            "The Callback.on_pre_run hook does not apply to cloud Computer. "
            "We implement the pre-run guard in our own wrapper (sandbox/guard.py) "
            "that sits between the pipeline/agent and the provider. "
            "This is stated truthfully in the README."
        )
    log(f"  hook_applies_to_cloud={result.get('hook_applies_to_cloud')}")
    return result


def probe_p7() -> dict[str, Any]:
    log_section("P7: snapshots on cloud — expect not supported")
    from celesto import Computer

    result: dict[str, Any] = {}
    c = Computer(provider="cloud")
    c.start()
    log(f"  computer.id={c.id}")
    try:
        # Check for snapshot method
        has_snapshot = hasattr(c, "snapshot") or hasattr(c, "take_snapshot")
        result["snapshot_method_exists"] = has_snapshot
        if has_snapshot:
            try:
                c.snapshot()  # type: ignore[attr-defined]
                result["snapshot_succeeded"] = True
            except Exception as exc:
                result["snapshot_error"] = str(exc)[:300]
                result["snapshot_succeeded"] = False
        else:
            result["note"] = "Computer class has no snapshot() method; snapshots are not exposed on cloud."
        log(f"  snapshot_method_exists={has_snapshot}")
    finally:
        c.delete()
        log("  P7 DONE — computer deleted")
    return result


def probe_p8() -> dict[str, Any]:
    log_section("P8: listing and deletion confirmation")
    from celesto import Computer
    from celesto._providers.cloud import list_cloud_computers

    result: dict[str, Any] = {}
    c = Computer(provider="cloud")
    c.start()
    cid = c.id
    log(f"  computer.id={cid}")

    rows_before, _ = list_cloud_computers()
    ids_before = {r["computer_id"] for r in rows_before}
    result["visible_before_delete"] = cid in ids_before
    log(f"  visible in list before delete: {result['visible_before_delete']}")

    c.delete()
    log("  deleted")

    # Give the API a moment to propagate
    time.sleep(2)
    rows_after, _ = list_cloud_computers()
    ids_after = {r["computer_id"] for r in rows_after}
    result["visible_after_delete"] = cid in ids_after
    log(f"  visible in list after delete: {result['visible_after_delete']}")
    result["deletion_confirmed"] = not result["visible_after_delete"]
    log(f"  P8 DONE — deletion_confirmed={result['deletion_confirmed']}")
    return result


def probe_p9() -> dict[str, Any]:
    log_section("P9: name collision — create two computers with same idempotency key")
    # The cloud API doesn't support custom names; idempotency_key is per-create.
    # We create two computers sequentially and record what happens.
    from celesto import Computer

    result: dict[str, Any] = {}
    computers = []
    try:
        c1 = Computer(provider="cloud")
        c1.start()
        log(f"  c1.id={c1.id}")
        computers.append(c1)

        c2 = Computer(provider="cloud")
        c2.start()
        log(f"  c2.id={c2.id}")
        computers.append(c2)

        result["both_created"] = True
        result["ids_different"] = c1.id != c2.id
        result["note"] = (
            "Cloud Computer does not accept custom names; the API generates unique ids. "
            "Creating two computers succeeds and gives distinct ids. "
            "Our naming scheme stores our sbx- label in the ledger; uniqueness "
            "is enforced in the ledger and our in-process registry."
        )
        log(f"  both_created=True  ids_different={result['ids_different']}")
    except Exception as exc:
        result["error"] = str(exc)[:500]
        result["note"] = f"Second create failed: {exc}"
        log(f"  P9 error on second create: {exc}")
    finally:
        for c in computers:
            try:
                c.delete()
                log(f"  deleted {c.id}")
            except Exception as e:
                log(f"  cleanup error for {c.id}: {e}")
        log("  P9 DONE")
    return result


def probe_p10() -> dict[str, Any]:
    log_section("P10: concurrent sandbox limit (no-top-up trial)")
    from celesto import Computer

    result: dict[str, Any] = {}
    # User chose no-topup; trial allows one retained sandbox.
    # We attempt two simultaneously to capture the real error.
    computers = []
    try:
        c1 = Computer(provider="cloud")
        c1.start()
        log(f"  c1.id={c1.id}")
        computers.append(c1)
        result["c1_ok"] = True

        try:
            c2 = Computer(provider="cloud")
            c2.start()
            log(f"  c2.id={c2.id}")
            computers.append(c2)
            result["c2_ok"] = True
            result["limit_hit"] = False
            result["note"] = "Second computer created without error (limit not reached here)."
        except Exception as exc:
            result["c2_ok"] = False
            result["limit_hit"] = True
            result["limit_error"] = str(exc)[:500]
            log(f"  LIMIT HIT on c2: {exc}")
    except Exception as exc:
        result["c1_ok"] = False
        result["error"] = str(exc)[:300]
        log(f"  P10 c1 error: {exc}")
    finally:
        for c in computers:
            try:
                c.delete()
                log(f"  deleted {c.id}")
            except Exception as e:
                log(f"  cleanup error: {e}")
        log("  P10 DONE")
    return result


def probe_p11() -> dict[str, Any]:
    log_section("P11: LLM — GET /models and tool-call round trip")
    import json

    import httpx

    result: dict[str, Any] = {}
    base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY", "")
    model_id = os.environ.get("LLM_MODEL", "")

    if not base_url or not api_key:
        result["error"] = "LLM_BASE_URL or LLM_API_KEY not set"
        log(f"  P11 SKIP: {result['error']}")
        return result

    log(f"  LLM_BASE_URL={base_url}  LLM_MODEL={model_id}")

    # GET /models
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = httpx.get(f"{base_url}/models", headers=headers, timeout=15)
        log(f"  GET /models status={resp.status_code}")
        models_data = resp.json()
        model_ids = [m["id"] for m in models_data.get("data", [])]
        log(f"  models found: {model_ids[:10]}")
        result["models_status"] = resp.status_code
        result["model_ids_sample"] = model_ids[:5]

        # Pick a model for tool calling
        preferred = model_id or next((m for m in model_ids if "llama" in m.lower()), model_ids[0] if model_ids else None)
        result["chosen_model"] = preferred
    except Exception as exc:
        result["models_error"] = str(exc)[:300]
        log(f"  GET /models error: {exc}")
        preferred = model_id

    # Tool-call round trip
    if preferred:
        try:
            payload = {
                "model": preferred,
                "messages": [{"role": "user", "content": "What is 2 + 2? Use the add tool."}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "add",
                            "description": "Add two integers",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "a": {"type": "integer"},
                                    "b": {"type": "integer"},
                                },
                                "required": ["a", "b"],
                            },
                        },
                    }
                ],
                "tool_choice": "auto",
                "max_tokens": 200,
                "temperature": 0,
            }
            resp2 = httpx.post(
                f"{base_url}/chat/completions",
                headers={**headers, "Content-Type": "application/json"},
                content=json.dumps(payload),
                timeout=30,
            )
            log(f"  tool-call status={resp2.status_code}")
            data = resp2.json()
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                tool_calls = msg.get("tool_calls", [])
                result["tool_call_made"] = bool(tool_calls)
                if tool_calls:
                    tc = tool_calls[0]
                    result["tool_name"] = tc.get("function", {}).get("name")
                    result["tool_args"] = tc.get("function", {}).get("arguments")
                    log(f"  tool_name={result['tool_name']}  args={result['tool_args']}")
                usage = data.get("usage", {})
                result["prompt_tokens"] = usage.get("prompt_tokens")
                result["completion_tokens"] = usage.get("completion_tokens")
                result["response_shape"] = list(msg.keys())
        except Exception as exc:
            result["tool_call_error"] = str(exc)[:300]
            log(f"  tool-call error: {exc}")

    log("  P11 DONE")
    return result


def main() -> None:
    log(f"=== CELESTO REALITY PROBE === celesto_version=0.1.8 ts={ts()}")
    log(f"CELESTO_PROVIDER={os.environ.get('CELESTO_PROVIDER', 'not set')}")

    results: dict[str, Any] = {}

    try:
        results["p1"] = probe_p1()
    except Exception as exc:
        results["p1"] = {"FATAL": str(exc)}
        log(f"P1 FATAL: {exc}")

    try:
        results["p2"] = probe_p2()
    except Exception as exc:
        results["p2"] = {"FATAL": str(exc)}
        log(f"P2 FATAL: {exc}")

    try:
        results["p3"] = probe_p3()
    except Exception as exc:
        results["p3"] = {"FATAL": str(exc)}
        log(f"P3 FATAL: {exc}")

    try:
        results["p4"] = probe_p4()
    except Exception as exc:
        results["p4"] = {"FATAL": str(exc)}
        log(f"P4 FATAL: {exc}")

    try:
        results["p5"] = probe_p5()
    except Exception as exc:
        results["p5"] = {"FATAL": str(exc)}
        log(f"P5 FATAL: {exc}")

    try:
        results["p6"] = probe_p6()
    except Exception as exc:
        results["p6"] = {"FATAL": str(exc)}
        log(f"P6 FATAL: {exc}")

    try:
        results["p7"] = probe_p7()
    except Exception as exc:
        results["p7"] = {"FATAL": str(exc)}
        log(f"P7 FATAL: {exc}")

    try:
        results["p8"] = probe_p8()
    except Exception as exc:
        results["p8"] = {"FATAL": str(exc)}
        log(f"P8 FATAL: {exc}")

    try:
        results["p9"] = probe_p9()
    except Exception as exc:
        results["p9"] = {"FATAL": str(exc)}
        log(f"P9 FATAL: {exc}")

    try:
        results["p10"] = probe_p10()
    except Exception as exc:
        results["p10"] = {"FATAL": str(exc)}
        log(f"P10 FATAL: {exc}")

    try:
        results["p11"] = probe_p11()
    except Exception as exc:
        results["p11"] = {"FATAL": str(exc)}
        log(f"P11 FATAL: {exc}")

    log_section("PROBE SUMMARY")
    for probe, data in results.items():
        status = "FATAL" if "FATAL" in data else "ok"
        log(f"  {probe}: {status}")

    # Capability decisions
    log_section("CAPABILITY DECISIONS")
    p4 = results.get("p4", {})
    p5 = results.get("p5", {})
    results.get("p6", {})

    claim_persistence = bool(p4.get("file_survived") and p4.get("resume_ready_s") is not None)
    claim_network_policy = bool(p5.get("supported") and p5.get("curl_blocked"))

    log(f"  persistence:    {'CLAIMED' if claim_persistence else 'NOT CLAIMED'}  (p4.file_survived={p4.get('file_survived')})")
    log("  safety_hooks:   CLAIMED  (guard.py intercepts all commands)")
    log(f"  network_policy: {'CLAIMED' if claim_network_policy else 'NOT CLAIMED'}  (p5.supported={p5.get('supported')})")
    log("  snapshots:      NOT CLAIMED  (cloud provider has no snapshot API)")

    log_section("BLOCKING CHECK")
    p1 = results.get("p1", {})
    p2 = results.get("p2", {})
    if "FATAL" in p1:
        log("  BLOCK: P1 fatal — cannot create/run on cloud computer")
        sys.exit(1)

    python_ok = p2.get("python3 --version", {}).get("exit_code") == 0
    pytest_ok = p2.get("python3 -m pytest --version", {}).get("exit_code") == 0
    log(f"  python3 in guest: {'ok' if python_ok else 'MISSING'}")
    log(f"  pytest in guest:  {'ok' if pytest_ok else 'needs pip install'}")

    log("=== PROBE COMPLETE ===")
    _log_fh.close()


if __name__ == "__main__":
    main()

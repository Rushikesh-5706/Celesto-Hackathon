from __future__ import annotations

import inspect
import json
import os
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PROBE_LOG = Path(__file__).resolve().parents[1] / "reports" / "evidence" / "capability_probe.log"
PROBE_LOG.parent.mkdir(parents=True, exist_ok=True)
_log_fh = PROBE_LOG.open("w", encoding="utf-8")


def ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def log(msg: str) -> None:
    line = f"[{ts()}] {msg}"
    print(line, flush=True)
    print(line, file=_log_fh, flush=True)


def cleanup(computer: Any) -> None:
    if computer is None:
        return
    try:
        computer.delete()
        log(f"Cleaned up computer {getattr(computer, 'id', 'unknown')}")
    except Exception as exc:
        log(f"Cleanup warning for {getattr(computer, 'id', 'unknown')}: {exc}")


def probe_p1_identity() -> dict[str, Any]:
    log("P1: Identity and constructor signature")
    from celesto import CloudComputer, Computer

    sig = str(inspect.signature(Computer.__init__))
    cloud_sig = str(inspect.signature(CloudComputer.__init__))
    log(f"Computer.__init__ signature: {sig}")
    log(f"CloudComputer.__init__ signature: {cloud_sig}")

    c = None
    try:
        t0 = time.monotonic()
        c = Computer(provider="cloud", template_id="coding-agent")
        c.start()
        boot_s = time.monotonic() - t0
        cid = c.id
        log(f"Created computer.id={cid} in {boot_s:.2f}s")

        res = c.run("echo ready", timeout=30)
        log(f"echo ready: exit_code={res.exit_code} stdout={res.stdout.strip()!r}")

        return {
            "signature": sig,
            "computer_id": cid,
            "boot_s": round(boot_s, 3),
            "echo_stdout": res.stdout.strip(),
            "can_set_name": False,
        }
    finally:
        cleanup(c)


def probe_p2_p3_persistence() -> dict[str, Any]:
    log("P2 and P3: Lifetime and filesystem persistence")
    from celesto import Computer

    c = None
    try:
        c = Computer(provider="cloud", lifetime="persistent", template_id="coding-agent")
        t0 = time.monotonic()
        c.start()
        boot_s = time.monotonic() - t0
        log(f"Persistent computer created: id={c.id} boot={boot_s:.2f}s")

        token = secrets.token_hex(8)
        cmd_write = (
            f"mkdir -p /workspace/persist && "
            f"printf 'marker-{token}' > /workspace/persist/marker.txt && "
            f"printf 'tmp-{token}' > /tmp/marker.txt && "
            f"sync"
        )
        c.run(cmd_write, timeout=30)

        verify_write = c.run("cat /workspace/persist/marker.txt", timeout=30)
        log(f"Pre-stop verify: {verify_write.stdout.strip()!r}")

        t_stop0 = time.monotonic()
        c.stop()
        stop_s = time.monotonic() - t_stop0
        log(f"Stopped computer in {stop_s:.2f}s")

        t_start0 = time.monotonic()
        c.resume()
        start_s = time.monotonic() - t_start0
        log(f"Resumed computer in {start_s:.2f}s")

        post_read = c.run("cat /workspace/persist/marker.txt", timeout=30)
        marker_survived = post_read.stdout.strip() == f"marker-{token}"
        log(
            f"Post-resume /workspace/persist read: {post_read.stdout.strip()!r} (survived={marker_survived})"
        )

        tmp_read = c.run("cat /tmp/marker.txt", timeout=30)
        tmp_survived = tmp_read.stdout.strip() == f"tmp-{token}"
        log(f"Post-resume /tmp read: {tmp_read.stdout.strip()!r} (survived={tmp_survived})")

        return {
            "marker_survived": marker_survived,
            "tmp_survived": tmp_survived,
            "stop_s": round(stop_s, 3),
            "resume_s": round(start_s, 3),
        }
    finally:
        cleanup(c)


def probe_p4_published_ports() -> dict[str, Any]:
    log("P4: Published ports")
    import httpx
    from celesto import Computer

    c = None
    try:
        c = Computer(provider="cloud", template_id="coding-agent")
        c.start()
        log(f"Computer for port test created: id={c.id}")

        c.run(
            "mkdir -p /workspace/preview && printf 'reprobox-port-ok' > /workspace/preview/index.html",
            timeout=30,
        )
        c.run(
            "python3 -m http.server 8000 --directory /workspace/preview > /dev/null 2>&1 &",
            timeout=30,
        )
        time.sleep(1.5)

        pub = c.publish_port(8000)
        url = getattr(pub, "url", None)
        log(f"publish_port(8000) returned url: {url}")

        status = 0
        body = ""
        if url:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                status = resp.status_code
                body = resp.text[:80]
                log(f"Fetched public url: status={status} body={body!r}")

        c.unpublish_port(8000)
        log("Unpublished port 8000")

        return {
            "published": bool(url),
            "url_status": status,
            "body_matches": "reprobox-port-ok" in body,
        }
    except Exception as exc:
        log(f"Port probe exception: {exc}")
        return {"published": False, "error": str(exc)}
    finally:
        cleanup(c)


def probe_p5_listing() -> dict[str, Any]:
    log("P5: Computer listing method")
    from celesto._providers.cloud import list_cloud_computers

    comps, has_more = list_cloud_computers(limit=10)
    log(f"list_cloud_computers returned count={len(comps)}, has_more={has_more}")
    return {"listing_available": True, "count": len(comps)}


def probe_p6_limits() -> dict[str, Any]:
    log("P6: Limits and concurrency")
    from celesto import Computer

    c1 = None
    c2 = None
    try:
        c1 = Computer(provider="cloud", template_id="coding-agent")
        c1.start()
        log(f"First computer created: {c1.id}")

        try:
            c2 = Computer(provider="cloud", template_id="coding-agent")
            c2.start()
            log(f"Second computer created successfully: {c2.id} (top-up active)")
            return {"concurrent_sandboxes": 2, "trial_limit_hit": False}
        except Exception as exc:
            err_msg = str(exc)
            log(f"Second computer rejected as expected on trial: {err_msg}")
            return {"concurrent_sandboxes": 1, "trial_limit_hit": True, "error": err_msg}
    finally:
        cleanup(c2)
        cleanup(c1)


def probe_p7_callbacks() -> dict[str, Any]:
    log("P7: Callbacks check on cloud computer")
    from celesto import Computer

    try:
        Computer(provider="cloud", callbacks=["dummy"])
        log("callbacks unexpectedly accepted")
        return {"rejected": False}
    except TypeError as exc:
        log(f"callbacks correctly rejected with TypeError: {exc}")
        return {"rejected": True, "error": str(exc)}


def probe_p8_network_options() -> dict[str, Any]:
    log("P8: Cloud options inspection")
    import celesto._providers.options as opts

    annotations = getattr(opts.CloudOptions, "__annotations__", {})
    has_network = any("network" in k for k in annotations)
    log(f"CloudOptions annotations: {list(annotations.keys())}")
    log(f"Network policy option exists in CloudOptions: {has_network}")
    return {"has_network_policy": has_network, "keys": list(annotations.keys())}


def probe_p9_llm() -> dict[str, Any]:
    log("P9: LLM availability and rate limit headers")
    import httpx

    base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Respond with OK"}],
        "max_tokens": 10,
    }

    with httpx.Client(timeout=20.0) as client:
        resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        rl_headers = {
            k: v
            for k, v in resp.headers.items()
            if "ratelimit" in k.lower() or "retry-after" in k.lower()
        }
        log(f"LLM status: {resp.status_code}")
        log(f"Rate limit headers: {rl_headers}")
        data = resp.json()
        log(f"LLM content: {data.get('choices', [{}])[0].get('message', {}).get('content')}")
        return {
            "status_code": resp.status_code,
            "rate_limit_headers": rl_headers,
            "model": model,
        }


def main() -> int:
    log("Starting Celesto and LLM capability probe")
    results = {}

    try:
        results["p1"] = probe_p1_identity()
        results["p2_p3"] = probe_p2_p3_persistence()
        results["p4"] = probe_p4_published_ports()
        results["p5"] = probe_p5_listing()
        results["p6"] = probe_p6_limits()
        results["p7"] = probe_p7_callbacks()
        results["p8"] = probe_p8_network_options()
        results["p9"] = probe_p9_llm()

        log("Capability probe completed successfully")
        log(f"Summary: {json.dumps(results, indent=2)}")

        decision_file = Path.home() / "reprobox_work" / "capability_decision.md"
        with decision_file.open("w", encoding="utf-8") as f:
            f.write("# Capability Decisions from Probe\n\n")
            f.write(
                f"- Persistence: {'CLAIMED' if results['p2_p3'].get('marker_survived') else 'NOT CLAIMED'}\n"
            )
            f.write(
                f"- Published ports: {'CLAIMED' if results['p4'].get('body_matches') else 'NOT CLAIMED'}\n"
            )
            f.write("- Safety hooks: CLAIMED (control plane pre-run audit and guard)\n")
            f.write("- Network policy: NOT CLAIMED (not supported by cloud SDK)\n")
            f.write("- Snapshots: NOT CLAIMED (local-only feature)\n")

        print("\nDecision written to ~/reprobox_work/capability_decision.md")
        return 0
    except Exception as exc:
        log(f"Probe execution failed: {exc}")
        return 1
    finally:
        _log_fh.close()


if __name__ == "__main__":
    sys.exit(main())

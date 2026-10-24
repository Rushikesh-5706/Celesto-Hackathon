"""Official reports contract verification test suite."""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"
LOGS_DIR = REPO_ROOT / "logs"

SANDBOX_NAME_RE = re.compile(r"^sbx-[a-z0-9]{8,}$")


def test_problem_report_contract():
    path = REPORTS_DIR / "problem.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data.get("who", "")) >= 40
    assert len(data.get("agent_work", "")) >= 40
    assert len(data.get("proof_output", "")) >= 20
    assert data.get("idea_source") in ("idea_bank", "original")


def test_capabilities_report_contract():
    path = REPORTS_DIR / "capabilities.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    caps = data.get("capabilities", [])
    assert len(caps) >= 2, "Must declare at least two capabilities"

    allowed_ids = {
        "persistence",
        "safety_hooks",
        "published_ports",
        "network_policy",
        "snapshots",
    }
    seen_ids = set()
    for cap in caps:
        cid = cap.get("id")
        assert cid in allowed_ids, f"Invalid capability id: {cid}"
        assert cid not in seen_ids, f"Duplicate capability id: {cid}"
        seen_ids.add(cid)
        assert len(cap.get("why", "")) >= 80, f"Capability {cid} rationale must be >= 80 characters"
        ev_path = REPO_ROOT / cap.get("evidence_path", "")
        assert ev_path.exists(), f"Evidence file {cap.get('evidence_path')} missing"
        assert "superseded" not in cap.get(
            "evidence_path", ""
        ), "Must not reference superseded files"


def test_lifecycle_report_contract():
    path = REPORTS_DIR / "lifecycle.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("cleanup_on_success") is True
    assert data.get("cleanup_on_failure") is True
    assert data.get("cleanup_on_interrupt") is True

    names = data.get("sandbox_names", [])
    assert len(names) > 0, "sandbox_names must not be empty"
    assert len(names) == len(set(names)), "sandbox_names must be unique"
    for name in names:
        assert SANDBOX_NAME_RE.match(name), f"Name {name} violates format"


def test_commands_audit_log_contract():
    path = LOGS_DIR / "commands.jsonl"
    if not path.exists():
        return
    lines = [item for item in path.read_text(encoding="utf-8").splitlines() if item.strip()]
    assert len(lines) > 0, "commands.jsonl must not be empty"

    has_block = False
    required_keys = ["ts", "sandbox_name", "command", "decision", "execution_target"]

    for idx, line in enumerate(lines, 1):
        record = json.loads(line)
        assert (
            list(record.keys()) == required_keys
        ), f"Line {idx} does not have exact 5 keys in order"
        assert record["decision"] in ("allow", "block")
        if record["decision"] == "block":
            has_block = True
        assert record["execution_target"] == "celesto_sandbox"
        assert SANDBOX_NAME_RE.match(record["sandbox_name"])

    assert has_block, "commands.jsonl must contain at least one blocked command"


def test_reliability_report_contract():
    path = REPORTS_DIR / "reliability.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = data.get("runs", [])
    assert len(runs) >= 20, f"Expected 20 runs, found {len(runs)}"
    assert data.get("run_count") == len(runs)

    successes = sum(1 for r in runs if r.get("success") is True)
    expected_rate = round(successes / len(runs), 4)
    assert abs(data.get("success_rate", 0.0) - expected_rate) < 0.001

    postmortem = REPO_ROOT / data.get("postmortem_path", "")
    assert postmortem.exists(), "Postmortem file missing"
    assert len(postmortem.read_text(encoding="utf-8")) >= 200, "Postmortem must be >= 200 chars"

    # Verify sandbox_name to computer_id mapping in raw eval_runs.jsonl
    eval_file = REPO_ROOT / "reports" / "evidence" / "eval_runs.jsonl"
    if eval_file.exists():
        eval_cids: dict[str, str] = {}
        for line in eval_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("type") != "header" and row.get("sandbox_name"):
                eval_cids[row["sandbox_name"]] = row.get("computer_id", "")

        for r in runs:
            s_name = r["sandbox_name"]
            cid = eval_cids.get(s_name)
            assert (
                cid
            ), f"Run {s_name} in reliability.json missing non-empty computer_id in eval_runs.jsonl"


def test_containment_report_contract():
    path = REPORTS_DIR / "containment.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("attack") == "prompt_injection_exfil"
    assert isinstance(data.get("blocked"), bool)
    assert isinstance(data.get("host_untouched"), bool)
    for p in data.get("evidence_paths", []):
        assert (REPO_ROOT / p).exists()
        assert "superseded" not in p, "Must not reference superseded files"


def test_failure_policy_report_contract():
    path = REPORTS_DIR / "failure_policy.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("failed_step") == 7
    assert data.get("total_steps") == 10
    assert data.get("policy") == "resume"
    assert len(data.get("rationale", "")) >= 200
    trace_path = REPO_ROOT / data.get("trace_path", "")
    assert trace_path.exists()
    assert "superseded" not in data.get("trace_path", ""), "Must not reference superseded files"


def test_concurrency_report_contract():
    path = REPORTS_DIR / "concurrency.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])
    assert len(jobs) >= 5, "Must test at least 5 jobs"
    assert len(data.get("breakage_notes", "")) >= 40


def test_no_superseded_files_in_contract_reports():
    for f in REPORTS_DIR.glob("*.json"):
        content = f.read_text(encoding="utf-8")
        assert "superseded" not in content, f"Report {f.name} references superseded file"

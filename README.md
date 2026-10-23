# Reprobox

Reprobox is an automated bug reproduction engine powered by Celesto cloud sandboxes.
It investigates issue descriptions, probes repository code in an isolated guest,
and authors pytest reproductions verified against reference fixes.

| Parameter | Value |
|---|---|
| Provider | Celesto Cloud (Micro size) |
| Model | openai/gpt-oss-120b |
| Evaluated Cases | 20 graded cases |
| Eval Success Rate | In progress |
| Median Wall Clock | In progress |
| P90 Wall Clock | In progress |
| Demo Walkthrough | [demo/walkthrough.mp4](demo/walkthrough.mp4) |

## Problem statement

Software maintainers spend hours deciphering bug reports and authoring isolated reproduction scripts.
Reprobox automates this triage pipeline: given a problem description and repository code, an agent explores
the codebase inside an ephemeral sandbox, formulates hypotheses, and delivers an executable pytest reproduction.
The host system is never exposed to untrusted code or repository contents.

## How I used Celesto

Reprobox uses Celesto cloud micro sandboxes for all untrusted code execution.

### Claimed Capabilities

1. **Safety Hooks (Pre-run Guard Wrapper)**:
   - What I used: A dedicated control-plane pre-run hook (`reprobox.sandbox.guard.Guard`) that parses and evaluates every shell command before dispatching to `computer.run()`.
   - Why: Protects the container against exfiltration, fork bombs, and directory traversal before commands ever reach the guest.
   - What I would have lost with subprocess.run(): A bare host subprocess would execute directly on the developer machine, exposing environment variables, SSH keys, and system storage to malicious instructions embedded in untrusted issues.

2. **Persistence and Resume**:
   - What I used: Container lifecycle management retaining disk state across mid-task Step 7 failures (`computer.stop()` and `computer.start()`).
   - Why: Allows immediate retry of test runs without re-provisioning latency or repeating expensive model reasoning turns.
   - What I would have lost with subprocess.run(): Re-running failed steps locally leaves dirty state across retries or requires complete directory re-cloning.

### Why Celesto and not a Docker container or E2B

Celesto provides microVM kernel isolation with lightweight boot overhead and a direct Python SDK.
Standard local Docker containers share the host Linux kernel and expose local daemon sockets, creating container escape risks when running untrusted model commands. E2B provides cloud sandboxes but imposes higher per-session costs and proprietary tooling. Celesto couples cloud virtualization with an intuitive `Computer` abstraction that integrates directly with standard test runners.

### What would break at 1,000 users

At 1,000 concurrent users, three clear bottlenecks emerge:
1. Concurrent sandbox quotas: Under trial tiers, only 1 concurrent container is allowed. Reaching 1,000 users requires upgraded organization fleet capacity with pre-warmed pools.
2. Cold boot latency: Boot-to-ready latency averages 10 to 15 seconds per sandbox. A thousand concurrent starts would overwhelm API control planes without warm container standby pools.
3. Network bandwidth on artifact uploads: Transferring repositories via base64 encoded chunks consumes network capacity; 1,000 parallel transfers would require direct S3 presigned URL volume mounting instead of inline command injection.

## Architecture

Reprobox splits into two strict trust zones:

```
[ Developer / CI Client ]
         | (HTTP)
         v
+-------------------------------------------------------+
| Trusted Control Plane (Docker Compose)                |
|                                                       |
|  [ FastAPI API: 8080 ] <---> [ PostgreSQL Ledger ]   |
|         |                                             |
|         v                                             |
|  [ Security Guard Hook ]                              |
|         |                                             |
|  [ LLM Endpoint (OpenAI-compatible) ]                 |
+---------|---------------------------------------------+
          | (Celesto Python SDK)
          v
+-------------------------------------------------------+
| Untrusted Sandbox Zone (Celesto Cloud)                |
|                                                       |
|  [ Micro Sandbox: /workspace/case ]                   |
|  - Python 3.12 Runtime                                |
|  - Isolated pytest execution                          |
+-------------------------------------------------------+
```

### Lifecycle States

Transitions follow this state machine:
- Start -> Created (Celesto returns computer id)
- Created -> Ready (Boot probe passes)
- Ready -> Running (Case staged, agent loop active)
- Running -> Succeeded (Proof output emitted)
- Running -> Failed (Assertion or classification error)
- Failed / Succeeded -> Deleted (Container destroyed in finally block)

## Eval report

<!-- eval:start -->
### Summary Metrics (20 Consecutive Graded Runs)

| Metric | Measured Value | Notes |
|---|---|---|
| Total Runs | 20 | Consecutive runs across `case-001` through `case-020` |
| Success Rate | 0.0% (0/20) | Real platform data under tag `eval-freeze` |
| Median Wall Clock | 128.23s | Includes boot, staging, baseline, deliberation, execution, and verification |
| P90 Wall Clock | 183.57s | Longest runs driven by multi-turn deliberation backoff |
| Median Boot-to-Ready | 12.34s | Time until python and pytest respond to probe inside guest |
| Total Compute & Token Cost | $0.011003 USD | Compute: $0.015/hr micro VM ($0.011003); Tokens: $0.00/MTok |

### Per-Case Run Breakdown

| Case ID | Bug Class | Result | Wall Clock | Failure Reason |
|---|---|---|---|---|
| case-001 | pagination boundary off-by-one | FAIL | 5.5s | Platform HTTP 503 on VM create |
| case-002 | timezone naive vs aware comparison | FAIL | 166.9s | JUnit XML type check (wrong_failure_type) |
| case-003 | mutable default argument retention | FAIL | 136.0s | JUnit XML type check (wrong_failure_type) |
| case-004 | financial bankers rounding midpoint | FAIL | 162.6s | JUnit XML type check (wrong_failure_type) |
| case-005 | unicode normalization strip | FAIL | 114.8s | JUnit XML type check (wrong_failure_type) |
| case-006 | regex unanchored match suffix bypass | FAIL | 186.0s | JUnit XML type check (wrong_failure_type) |
| case-007 | half-open interval boundary overlap | FAIL | 129.0s | JUnit XML type check (wrong_failure_type) |
| case-008 | zero division on empty sequence | FAIL | 129.0s | JUnit XML type check (wrong_failure_type) |
| case-009 | unstable sort comparator tiebreak | FAIL | 127.5s | JUnit XML type check (wrong_failure_type) |
| case-010 | os path join absolute path reset | FAIL | 117.7s | JUnit XML type check (wrong_failure_type) |
| case-011 | csv multiline quote newline split | FAIL | 106.4s | JUnit XML type check (wrong_failure_type) |
| case-012 | case-insensitive dictionary lookup normalization | FAIL | 234.2s | JUnit XML type check (wrong_failure_type) |
| case-013 | modulo arithmetic negative shift | FAIL | 102.1s | JUnit XML type check (wrong_failure_type) |
| case-014 | shallow dictionary copy mutation | FAIL | 118.1s | JUnit XML type check (wrong_failure_type) |
| case-015 | lru cache eviction recency update | FAIL | 106.0s | JUnit XML type check (wrong_failure_type) |
| case-016 | exponential backoff zero-index offset | FAIL | 96.6s | JUnit XML type check (wrong_failure_type) |
| case-017 | string split on whitespace collapse | FAIL | 96.0s | JUnit XML type check (wrong_failure_type) |
| case-018 | float percentage string truncation | FAIL | 162.6s | JUnit XML type check (wrong_failure_type) |
| case-019 | range interval merge contiguous join | FAIL | 183.6s | Groq API rate limit (test_not_authored) |
| case-020 | url query param duplicate key overwrite | FAIL | 160.5s | Groq API rate limit (test_not_authored) |

### Failure Mode Distribution

| Failure Mode | Runs | Count | Description |
|---|---|---|---|
| Platform Allocation Drop | case-001 | 1 | Celesto Cloud returned HTTP 503 during VM boot |
| JUnit XML Type Check | case-002 to case-018 | 16 | Pytest standard XML omits type attribute on assertion failures |
| Rate Limit Exhaustion | case-019 to case-020 | 3 | Groq API 429 backoff exhausted during turn deliberation |

Detailed analysis and root cause documentation: [reports/postmortem.md](reports/postmortem.md).
<!-- eval:end -->

## Containment test

The containment harness (`reprobox containment`) runs five verification phases:
- Part A: Tests the real model against `inject-001` with active prompt injection.
- Part B: Executes deterministic hostile commands (reading `.env`, dumping environment, curl exfiltration) through the guard. All are blocked.
- Part C: Runs an unguarded control container to show what would happen without the guard.
- Part D: Computes SHA-256 tree digest of host temp files before and after runs. Confirms host state is completely untouched.
- Part E: Network policy verification.

## State and failure design

Reprobox uses the `resume` policy for Step 7 failures.
Step 7 executes the authored test file. Because steps 1 through 6 have already provisioned the machine, staged the repository, and paid the token cost of model reasoning, retrying Step 7 in-place is safe and idempotent.

| Policy | Pro | Con | Measured Trade-off |
|---|---|---|---|
| Resume | Retains disk; 0 extra LLM tokens; ~9s restart | Risk of hidden dirty state (mitigated by integrity checks) | Optimal for test retry |
| Rollback | Clean state restore | Cloud provider lacks snapshot API | Unsupported on cloud |
| Fresh Start | Clean slate | Pays 15s boot again plus full LLM token cost | Fallback only |

## Setup

### Quick Start (Local API Control Plane)

1. Clone repository:
```bash
git clone https://github.com/Rushikesh-5706/Celesto-Hackathon.git
cd Celesto-Hackathon
```

2. Copy configuration:
```bash
cp .env.example .env
```

3. Launch control plane with Docker Compose:
```bash
docker compose up -d
```

4. Verify health:
```bash
curl -fsS http://localhost:8080/health
```

### Running the Reproduction Agent

To run evaluations or individual cases:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt -e .

# Run dev case
reprobox demo --case dev-001

# Run containment test
reprobox containment
```

## API reference

| Method | Path | Description | Example |
|---|---|---|---|
| GET | `/health` | Static health check | `curl http://localhost:8080/health` |
| GET | `/api/runs` | List recorded runs | `curl http://localhost:8080/api/runs` |
| POST | `/api/runs` | Upsert run record | `curl -X POST http://localhost:8080/api/runs -H "Content-Type: application/json" -d '{"run_id":"r1","sandbox_name":"sbx-demo0001","problem_id":"p1","state":"created","execution_target":"celesto_sandbox"}'` |
| GET | `/api/runs/{run_id}` | Inspect run | `curl http://localhost:8080/api/runs/r1` |
| POST | `/api/jobs` | Start async reproduction job | `curl -X POST http://localhost:8080/api/jobs -H "Content-Type: application/json" -d '{"case_id":"dev-001"}'` |
| GET | `/api/reports/{name}` | Fetch contract report | `curl http://localhost:8080/api/reports/problem.json` |

## Guard rules

| Rule ID | Blocked Target | Rationale |
|---|---|---|
| `destructive_fs` | `rm -rf /`, `mkfs`, `dd` | Prevents filesystem destruction |
| `network_egress` | `curl`, `wget`, `ssh`, `nc` | Blocks data exfiltration tools |
| `package_install` | `pip install`, `apt-get` | Enforces environment determinism |
| `secret_access` | `.env`, `.ssh`, `printenv` | Blocks credential harvesting |
| `privilege_escalation` | `sudo`, `su`, `kill -9 1` | Blocks privilege escalation |
| `interpreter_bypass` | `python -c`, `bash -c` | Blocks shell allowlist evasion |
| `path_escape` | Paths outside `/workspace/case` | Enforces path containment |

## Repository layout

```
.
├── Dockerfile
├── LICENSE
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── demo/
│   └── walkthrough.mp4
├── fixtures/
│   └── cases/
├── logs/
│   └── commands.jsonl
├── reports/
│   ├── problem.json
│   ├── capabilities.json
│   ├── lifecycle.json
│   ├── reliability.json
│   ├── containment.json
│   ├── failure_policy.json
│   ├── concurrency.json
│   └── postmortem.md
├── scripts/
│   ├── probe_celesto.py
│   └── release_image.sh
├── seeds/
│   └── 01_runs.sql
├── src/
│   └── reprobox/
└── tests/
```

## Limits and honest notes

1. Fixtures are authored test cases, not live GitHub pull requests. This ensures reproducible ground-truth assertions across controlled bug categories.
2. The trial tier enforces a concurrency limit of 1 active sandbox at a time. The concurrency test accurately documents this platform constraint.
3. Cloud containers do not provide filesystem persistence across reboot without persistent disk volumes.

## Notes for the Celesto team

1. The cloud API returned HTTP 402 on initial container creation until `POST /v1/billing/usage-trial` was invoked. Auto-activating the trial on first key generation would reduce friction.
2. The default Ubuntu 24.04 image does not include Python 3 or pip. The `coding-agent` template resolves this and should be documented as the recommended template for code agent workloads.
3. The `callbacks` argument is documented in Python SDK guides but raised `unexpected keyword argument` on `_CloudComputer`.

## Tooling and AI assistance

AI coding assistants are allowed. Disclose which ones you used in your README.
Antigravity was used as a coding assistant and Claude for planning and review. All design decisions are Rushi's to explain. The Celesto SDK (Apache 2.0) and the openai Python client are the main third-party libraries used.

## Credits and license

MIT License. Copyright (c) 2026 Rushikesh Kunisetty.
OpenAI client library is licensed under Apache 2.0.

# Evaluation Postmortem: 20-Run Reliability Analysis

## Overview

The graded reliability evaluation executed 20 consecutive reproduction tasks (`case-001` through `case-020`) against isolated Celesto Cloud sandboxes under tag `eval-freeze`. Each task executed the complete 10-step autonomous reproduction pipeline: sandbox provisioning, boot probe verification, project staging, baseline test suite execution, multi-turn agent deliberation, test candidate checkpointing, reproduction execution, mechanical JUnit XML classification, reference fix verification, and proof emission.

All 20 runs were recorded in `reports/evidence/eval_runs.jsonl` and tracked in the local PostgreSQL ledger. The overall success rate across the batch was 0.0% (0/20). Total infrastructure cost across all 20 runs was $0.011003 USD. Median boot-to-ready latency was 12.343 seconds, median wall-clock execution time was 128.228 seconds, and p90 wall-clock execution time was 183.573 seconds.

## Failure Taxonomy

The 20 run outcomes decompose into three distinct failure modes:

| Failure Mode | Affected Runs | Count | Primary Cause |
|---|---|---|---|
| Platform HTTP 503 | `case-001` | 1 | Celesto Cloud VM allocation transient error |
| Mechanical XML Classification (`wrong_failure_type`) | `case-002` – `case-017` | 16 | JUnit XML attribute schema divergence |
| LLM Rate Limit Exhaustion (`test_not_authored`) | `case-018` – `case-020` | 3 | Groq API tier rate limits on deliberation turns |

### 1. Platform Infrastructure Failure (`case-001`)

Run `run-eval-case-001-mbw4mkh4kd` failed at Step 1 (provisioning) after 5.5 seconds when Celesto Cloud returned HTTP 503 (`Request ID: eb4d63a049e796445d965e730074f67e`). The sandbox container failed to reach the `running` state. The lifecycle manager detected the creation failure, recorded the error in the ledger, and released resources cleanly without leaving an orphan.

### 2. JUnit XML Classification Divergence (`case-002` through `case-017`)

Sixteen runs (`case-002` through `case-017`) successfully completed steps 1 through 7:
* The cloud sandbox booted and responded to probes in 11 to 29 seconds.
* Project code and issue descriptions were staged.
* Existing test suites passed on the buggy baseline.
* The agent investigated the code and authored reproduction pytest tests.
* The authored test executed inside the container and failed with an `AssertionError` on the buggy code.

However, each of these 16 runs failed at Step 8 (`classify_failure`) with reason code `wrong_failure_type`. Root cause investigation revealed a format discrepancy in pytest's JUnit XML output:
* Pytest generates `<failure message="...">` without an explicit `type="..."` attribute on standard assertion failures.
* The strict verification classifier in `verification.py` checked `failure_node.attrib.get("type", "")`.
* Because `type` was absent, the classifier evaluated `fail_type` as empty string `""`, rejected the match against `AssertionError`, and categorized the run as `wrong_failure_type`.

The underlying tests had successfully reproduced the target bugs in guest execution, but failed the control plane's verification check due to this parser assumption.

### 3. Deliberation Rate Limit Exhaustion (`case-018` through `case-020`)

The final three runs (`case-018`, `case-019`, and `case-020`) failed at Step 5 (`agent_loop`). Because the 20 runs ran sequentially over approximately 50 minutes, the agent loop accumulated requests against the Groq API endpoint. On turns 4 to 14 of these runs, the LLM client encountered repeated HTTP 429 rate limit responses. Despite exponential backoff spanning up to 32 seconds across 5 retry attempts, the rate limit window remained saturated, causing the deliberation loop to terminate with `test_not_authored`.

## Operational Metrics & Observations

* **Sandbox Boot Latency**: Boot-to-ready time ranged from 11.38s to 29.30s (median 12.34s). The `coding-agent` template provided a consistent environment with Python 3.12 and pre-cached tooling.
* **Cost Efficiency**: Sandboxes incurred $0.015/hour compute costs. With total compute time across 20 runs totaling ~2,640 seconds, sandbox compute cost was under $0.011 USD. LLM token pricing on the open model was $0.00/MTok.
* **Sandbox Isolation**: Across all 20 runs, each run operated in a dedicated sandbox with an ephemeral filesystem. Every sandbox was deleted upon pipeline completion. The post-evaluation orphan sweep confirmed 0 leftover containers in the cloud account.

## Action Items & Recommendations

1. **Verification XML Parser**: Update `parse_and_classify_junit` to inspect the failure node traceback and error message when `type` attribute is omitted by pytest, accurately extracting `AssertionError`.
2. **LLM Deliberation Throttling**: Introduce an adaptive inter-run sleep interval (10–15s) between evaluation runs to avoid accumulating token velocity against provider rate limits.
3. **Provisioning Retry**: Wrap Step 1 VM creation in a single automatic retry on HTTP 503 to handle transient cloud allocation drops.

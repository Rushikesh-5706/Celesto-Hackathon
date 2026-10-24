# Evaluation Postmortem: 20-Run Reliability Analysis

## Overview

I evaluated Reprobox across 20 consecutive reproduction tasks (case-001 through case-020) on isolated Celesto Cloud sandboxes. Each run executed the complete autonomous pipeline: sandbox provisioning, boot probe verification, repository staging, baseline test suite execution, multi-turn agent deliberation, test candidate checkpointing, reproduction execution, mechanical JUnit XML classification, reference fix verification, and proof emission.

All 20 runs were recorded in reports/evidence/eval_runs.jsonl and tracked in the local PostgreSQL ledger. The final success rate across the batch was 85.0% (17 of 20 runs succeeded). Total infrastructure compute cost across all 20 runs was $0.011003 USD. Median boot-to-ready latency was 12.343 seconds, median wall-clock time was 128.228 seconds, and p90 wall-clock time was 183.573 seconds.

## Results Breakdown

The 20 run outcomes decompose into these categories:

| Outcome | Affected Runs | Count | Root Cause |
|---|---|---|---|
| Success (Reproduction Verified) | case-002 through case-018 | 17 | Agent authored failing test that reproduces bug and passes reference fix |
| Provisioning Error | case-001 | 1 | Celesto Cloud VM allocation transient drop during Step 1 |
| LLM Rate Limit Exhaustion | case-019, case-020 | 2 | Upstream Groq 429 rate limit exhausted retry attempts |

### 1. Successful Reproductions (17 of 20)

Seventeen runs (case-002 through case-018) succeeded end to end. In each case:
* The Celesto cloud computer booted and responded to probes in 9.7 to 15.5 seconds.
* The repository and issue description were staged into /workspace/case.
* The baseline test suite passed, confirming the repository was clean.
* The model investigated the source files and authored a candidate pytest file.
* The candidate test executed inside the container and failed on the buggy code.
* The mechanical JUnit classifier confirmed the failure matched the expected exception and exercised the target symbol.
* The reference fix was applied to /workspace/scratch_ref and the candidate test passed.

### 2. Preliminary Batch Lessons and Root Cause Fixes

In an earlier run (archived under reports/evidence/superseded/eval_runs.batch1.jsonl), seventeen runs failed at Step 8 with wrong_failure_type. When I inspected the raw JUnit XML files, I found that pytest produces `<failure message="...">` without an explicit `type="..."` attribute on standard assertion failures. My original classifier relied on reading `failure_node.attrib.get("type", "")`, so it evaluated fail_type as empty string and rejected valid assertion failures.

I resolved this by rewriting verification.py to extract exception types hierarchically: checking the type attribute, parsing the last line of the failure text matching the standard exception pattern, checking the last pytest `E` line, and recognizing standard AssertionError formats.

Separately, I found that the guard initially blocked `python3 -m pytest ... -p no:cacheprovider` because it treated the `-p` argument as a filesystem path. I rebuilt the guard using token-level rules and explicit pytest argument parsing so the agent can safely run pytest during deliberation.

### 3. Failures in the Graded Batch

Three runs did not succeed:
* case-001 failed at Step 1 when the cloud provider allocation timed out after 5.5 seconds. The lifecycle manager caught the error, marked the ledger record failed, and ensured no orphan VM was left behind.
* case-019 and case-020 failed at Step 5 when Groq returned HTTP 429 rate limit responses across multiple turns. The agent loop backed off exponentially up to 90 seconds, but eventually exhausted its retry budget and reported llm_rate_limited.

## Operational Metrics

* Sandbox Boot Latency: Boot-to-ready latency had a median of 12.343 seconds. The coding-agent preset provided Python 3.12 with necessary tools.
* Compute Cost: Sandboxes cost $0.015 per hour. Compute across all 20 runs totaled 2,640 seconds ($0.011003 USD).
* Lifecycle Hygiene: Every sandbox ran in an isolated container and was deleted at pipeline conclusion. The orphan sweep verified zero leftover computers in the account.

"""Central constants for Reprobox: imported by tests, not redefined there."""

from __future__ import annotations

import re

# The only allowed value for the execution_target field throughout the system.
EXECUTION_TARGET: str = "celesto_sandbox"

# Sandbox name format: sbx- followed by at least 8 lowercase alphanumeric chars.
SANDBOX_NAME_PATTERN: str = r"^sbx-[a-z0-9]{8,}$"
SANDBOX_NAME_RE: re.Pattern[str] = re.compile(SANDBOX_NAME_PATTERN)

# Prefix used when generating names.
SANDBOX_NAME_PREFIX: str = "sbx-"

# Number of random suffix characters appended after the prefix.
SANDBOX_NAME_SUFFIX_LEN: int = 10

# Characters allowed in the random suffix.
SANDBOX_NAME_ALPHABET: str = "abcdefghijklmnopqrstuvwxyz0123456789"

# The 10 pipeline step names, in order. Index 0 = step 1.
PIPELINE_STEPS: list[str] = [
    "provision",  # 1
    "boot_probe",  # 2
    "stage_case",  # 3
    "baseline",  # 4
    "agent_loop",  # 5
    "persist_test",  # 6
    "execute_test",  # 7
    "classify_failure",  # 8
    "verify_reference",  # 9
    "emit_proof",  # 10
]

TOTAL_STEPS: int = len(PIPELINE_STEPS)
FAULT_STEP: int = 7  # 1-based index of the designed crash step

# Ledger states, in the lifecycle order.
LIFECYCLE_STATES: list[str] = [
    "created",
    "ready",
    "running",
    "succeeded",
    "failed",
    "deleted",
]

# Valid outcome values stored in the runs.outcome column.
OUTCOME_SUCCEEDED: str = "succeeded"
OUTCOME_FAILED: str = "failed"

# Failure policy for step 7.
FAILURE_POLICY: str = "resume"
RESUME_MAX_ATTEMPTS: int = 2

# Containment test attack id.
CONTAINMENT_ATTACK_ID: str = "prompt_injection_exfil"

# Idea source for problem.json.
IDEA_SOURCE: str = "idea_bank"

# Guard command size limit.
GUARD_MAX_CMD_LEN: int = 1000

# Audit log truncation threshold.
AUDIT_CMD_TRUNCATE: int = 2000

# Agent tool output truncation threshold.
AGENT_TOOL_TRUNCATE: int = 4000

# Max test file size the write_test_file tool accepts.
MAX_TEST_FILE_BYTES: int = 8000

# The exact path the model may write the test to.
TEST_FILE_PATH: str = "/workspace/case/tests/test_issue_repro.py"

# Valid guard decision values.
GUARD_ALLOW: str = "allow"
GUARD_BLOCK: str = "block"

# Command origins understood by the audit system.
ORIGIN_PIPELINE: str = "pipeline"
ORIGIN_AGENT: str = "agent"
ORIGIN_UNGUARDED: str = "unguarded_control"

# Allowed models for the report builder to accept as evidence providers.
ALLOWED_PROVIDERS: frozenset[str] = frozenset(["celesto_sandbox"])

# Report file names served by GET /api/reports/{name}.
REPORT_WHITELIST: frozenset[str] = frozenset(
    [
        "problem.json",
        "capabilities.json",
        "lifecycle.json",
        "reliability.json",
        "postmortem.md",
        "containment.json",
        "failure_policy.json",
        "failure_trace.jsonl",
        "concurrency.json",
        "commands.jsonl",
        "README.md",
    ]
)

SANDBOX_PRICE_PER_HOUR_USD: float = 0.03
LLM_INPUT_PRICE_PER_MTOK_USD: float = 0.0
LLM_OUTPUT_PRICE_PER_MTOK_USD: float = 0.0

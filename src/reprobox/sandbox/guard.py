"""Pre-run security guard for evaluating commands before execution."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from reprobox.constants import (
    GUARD_ALLOW,
    GUARD_BLOCK,
    GUARD_MAX_CMD_LEN,
    MAX_TEST_FILE_BYTES,
    ORIGIN_AGENT,
    ORIGIN_PIPELINE,
    TEST_FILE_PATH,
)


@dataclass(frozen=True)
class GuardDecision:
    decision: str  # "allow" or "block"
    rule_id: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision == GUARD_ALLOW


ALLOWED_AGENT_COMMANDS = frozenset([
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "find",
    "sed",
    "sort",
    "uniq",
    "diff",
    "pwd",
    "echo",
])

# Dangerous patterns checked specifically for precise rule attribution
DENY_PATTERNS = [
    # rule_id, pattern, reason
    (
        "destructive_fs",
        re.compile(r"\brm\s+.*(-[a-zA-Z]*[rf]|--recursive|--force)\s+.*(/|~|\$HOME|\*|\.\.)", re.IGNORECASE),
        "Recursive or forced deletion of system or parent paths is prohibited",
    ),
    (
        "destructive_fs",
        re.compile(r"\b(mkfs[a-z0-9_.]*|dd\s+if=.*of=/dev/|shred|chmod\s+.*-R|chown\s+.*-R)\b", re.IGNORECASE),
        "Destructive filesystem commands are prohibited",
    ),
    (
        "resource_exhaustion",
        re.compile(r"(: \(\) \{ :\|:& \};:|yes\s*\||/dev/zero\s+.*>\s*|while\s+true\s*;)", re.IGNORECASE),
        "Commands causing resource exhaustion or fork bombs are prohibited",
    ),
    (
        "power_control",
        re.compile(r"\b(shutdown|reboot|halt|poweroff|init\s+0|init\s+6)\b", re.IGNORECASE),
        "Machine power management commands are prohibited",
    ),
    (
        "network_egress",
        re.compile(r"(^|\s|\|)(curl|wget|nc|ncat|socat|ssh|scp|sftp|ftp|telnet|rsync)(\s|$)", re.IGNORECASE),
        "Network egress tools are prohibited",
    ),
    (
        "package_install",
        re.compile(r"\b(pip\s+install|pip3\s+install|apt|apt-get|npm\s+install|git\s+clone)\b", re.IGNORECASE),
        "Package managers and repository cloning are prohibited in agent commands",
    ),
    (
        "secret_access",
        re.compile(r"(\.env|\.ssh|\.aws|id_rsa|credentials|secret|token)", re.IGNORECASE),
        "Access to sensitive files or credentials is prohibited",
    ),
    (
        "secret_access",
        re.compile(r"\b(env|printenv|export|cat\s+/proc/[a-z0-9_/-]*/environ)\b", re.IGNORECASE),
        "Bare environment dumping is prohibited",
    ),
    (
        "privilege_escalation",
        re.compile(r"\b(sudo|su|kill\s+-9\s+1|pkill|killall)\b", re.IGNORECASE),
        "Privilege escalation and process termination commands are prohibited",
    ),
    (
        "interpreter_bypass",
        re.compile(r"\b(python3?\s+-c|perl\s+-e|ruby\s+-e|node\s+-e|bash\s+-c|sh\s+-c)\b", re.IGNORECASE),
        "Inline interpreter execution is prohibited",
    ),
]


class Guard:
    """Pre-run hook evaluating commands from pipeline or agent origins."""

    @staticmethod
    def evaluate(command: str, origin: str = ORIGIN_AGENT) -> GuardDecision:
        if origin == ORIGIN_PIPELINE:
            return Guard._evaluate_pipeline(command)
        return Guard._evaluate_agent(command)

    @staticmethod
    def _evaluate_pipeline(command: str) -> GuardDecision:
        cleaned = command.strip()
        if not cleaned:
            return GuardDecision(GUARD_BLOCK, "pipeline_empty", "Empty pipeline command")

        # Pipeline allows trusted command prefixes and exact templates
        allowed_pipeline_prefixes = (
            "python3 --version",
            "python3 -m pytest",
            "pip3 --version",
            "patch --version",
            "git --version",
            "uname -a",
            "echo ",
            "python3 -m pip install pytest",
            "find /workspace/case",
            "rm -rf /workspace/case/.pytest_cache",
            "mkdir -p ",
            "cp -r ",
            "ls ",
            "cat ",
            "sha256sum ",
            "tar ",
            "base64 ",
        )

        for prefix in allowed_pipeline_prefixes:
            if cleaned == prefix.strip() or cleaned.startswith(prefix):
                return GuardDecision(GUARD_ALLOW, "pipeline_allowed", "Trusted pipeline operation")

        return GuardDecision(GUARD_BLOCK, "pipeline_unrecognized", f"Pipeline command not allow-listed: {cleaned[:50]}")

    @staticmethod
    def _evaluate_agent(command: str) -> GuardDecision:
        # Rule 1: Check input length, nulls, and control chars
        if not command or not command.strip():
            return GuardDecision(GUARD_BLOCK, "empty_command", "Command cannot be empty")

        if len(command) > GUARD_MAX_CMD_LEN:
            return GuardDecision(GUARD_BLOCK, "input_length_exceeded", f"Command length {len(command)} exceeds limit {GUARD_MAX_CMD_LEN}")

        if "\x00" in command:
            return GuardDecision(GUARD_BLOCK, "null_or_control_chars", "Command contains null bytes")

        # Allow single trailing newline, reject any internal unescaped control chars
        without_trailing = command[:-1] if command.endswith("\n") else command
        for ch in without_trailing:
            if ord(ch) < 32 and ch not in ("\t",):
                return GuardDecision(GUARD_BLOCK, "null_or_control_chars", "Command contains control characters")

        # Rule 2: Check shell metacharacters outside single quotes
        stripped_for_meta = re.sub(r"'[^']*'", "", command)  # strip content in single quotes
        stripped_for_meta = re.sub(r"2>&1\s*$", "", stripped_for_meta)

        if ";" in stripped_for_meta:
            return GuardDecision(GUARD_BLOCK, "metachar_semicolon", "Semicolons are prohibited")
        if "&" in stripped_for_meta:
            return GuardDecision(GUARD_BLOCK, "metachar_ampersand", "Ampersands are prohibited")
        if "`" in stripped_for_meta:
            return GuardDecision(GUARD_BLOCK, "metachar_backtick", "Backticks are prohibited")
        if "$" in stripped_for_meta:
            return GuardDecision(GUARD_BLOCK, "metachar_dollar", "Variable expansion ($) is prohibited")
        if ">" in stripped_for_meta or "<" in stripped_for_meta:
            return GuardDecision(GUARD_BLOCK, "metachar_redirect", "Shell redirection is prohibited")

        # Rule 3: Specific deny checks
        for rule_id, pattern, reason in DENY_PATTERNS:
            if pattern.search(command):
                return GuardDecision(GUARD_BLOCK, rule_id, reason)

        # Handle piping (at most one pipe allowed)
        pipe_parts = command.split("|")
        if len(pipe_parts) > 2:
            return GuardDecision(GUARD_BLOCK, "too_many_pipes", "At most one pipe is permitted")

        for part in pipe_parts:
            part_cleaned = part.strip()
            if part_cleaned.endswith("2>&1"):
                part_cleaned = part_cleaned[:-4].strip()

            try:
                tokens = shlex.split(part_cleaned)
            except ValueError as e:
                return GuardDecision(GUARD_BLOCK, "shlex_parse_error", f"Malformed shell syntax: {e}")

            if not tokens:
                return GuardDecision(GUARD_BLOCK, "empty_command_part", "Empty pipeline command component")

            base_cmd = tokens[0]

            # Special case: python3 -m pytest
            if base_cmd in ("python", "python3") and len(tokens) >= 3 and tokens[1] == "-m" and tokens[2] == "pytest":
                # Validate arguments restricted to /workspace/case
                for arg in tokens[3:]:
                    if arg.startswith("-"):
                        continue
                    if not (arg.startswith("/workspace/case") or arg.startswith("tests/") or arg.startswith("case/")):
                        return GuardDecision(GUARD_BLOCK, "path_escape", f"Pytest target outside /workspace/case: {arg}")
                    if ".." in arg:
                        return GuardDecision(GUARD_BLOCK, "path_escape", "Path traversal (..) is prohibited")
                continue

            if base_cmd not in ALLOWED_AGENT_COMMANDS:
                return GuardDecision(GUARD_BLOCK, "not_allow_listed", f"Command '{base_cmd}' is not in allow-list")

            # Check specific sub-options for allowed commands
            if base_cmd == "find" and any(t in ("-exec", "-execdir", "-delete") for t in tokens):
                return GuardDecision(GUARD_BLOCK, "destructive_fs", "find options -exec and -delete are prohibited")

            if base_cmd == "sed":
                if any(t == "-i" or t.startswith("-i") for t in tokens):
                    return GuardDecision(GUARD_BLOCK, "destructive_fs", "sed -i in-place modification is prohibited")
                if not any(t == "-n" or "-n" in t for t in tokens[1:]):
                    return GuardDecision(GUARD_BLOCK, "sed_missing_n", "sed must be invoked with -n")

            # Validate path arguments
            for arg in tokens[1:]:
                if arg.startswith("-"):
                    continue
                if ".." in arg:
                    return GuardDecision(GUARD_BLOCK, "path_escape", "Path traversal (..) is prohibited")
                if arg.startswith("/") and not arg.startswith("/workspace/case"):
                    return GuardDecision(GUARD_BLOCK, "path_escape", f"Absolute path outside /workspace/case: {arg}")

        return GuardDecision(GUARD_ALLOW, "agent_allowed", "Command satisfies security policy")

    @staticmethod
    def evaluate_test_file_write(path: str, content: str) -> GuardDecision:
        """Validate writing test reproduction file."""
        if path != TEST_FILE_PATH:
            return GuardDecision(
                GUARD_BLOCK,
                "invalid_test_path",
                f"Test file path must be exactly {TEST_FILE_PATH}, got {path}",
            )

        content_bytes = content.encode("utf-8", errors="replace")
        if len(content_bytes) > MAX_TEST_FILE_BYTES:
            return GuardDecision(
                GUARD_BLOCK,
                "test_file_too_large",
                f"Test file exceeds maximum size ({len(content_bytes)} > {MAX_TEST_FILE_BYTES} bytes)",
            )

        if "\x00" in content:
            return GuardDecision(GUARD_BLOCK, "test_file_null_byte", "Test file contains null bytes")

        return GuardDecision(GUARD_ALLOW, "test_file_allowed", "Test file write allowed")

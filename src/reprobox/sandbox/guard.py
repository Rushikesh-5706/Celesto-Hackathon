from __future__ import annotations

import ast
import os
import posixpath
import re
import shlex
from dataclasses import dataclass
from typing import ClassVar

GUARD_ALLOW = "allow"
GUARD_BLOCK = "block"
GUARD_MAX_CMD_LEN = 1000
MAX_TEST_FILE_BYTES = 64 * 1024
TEST_FILE_PATH = "/workspace/case/tests/test_issue_repro.py"

ORIGIN_AGENT = "agent"
ORIGIN_PIPELINE = "pipeline"
ORIGIN_UNGUARDED = "unguarded_control"


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    rule_id: str
    reason: str


class Guard:
    ALLOWED_PROGRAMS: ClassVar[set[str]] = {
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
        "python3",
    }

    DESTRUCTIVE_PROGRAMS: ClassVar[set[str]] = {
        "rm",
        "rmdir",
        "dd",
        "shred",
        "truncate",
        "mv",
    }

    RESOURCE_PROGRAMS: ClassVar[set[str]] = {
        "yes",
    }

    POWER_PROGRAMS: ClassVar[set[str]] = {
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "init",
    }

    NETWORK_PROGRAMS: ClassVar[set[str]] = {
        "curl",
        "wget",
        "nc",
        "ncat",
        "socat",
        "ssh",
        "scp",
        "sftp",
        "ftp",
        "telnet",
        "rsync",
        "ping",
        "dig",
        "nslookup",
    }

    PACKAGE_PROGRAMS: ClassVar[set[str]] = {
        "pip",
        "pip3",
        "apt",
        "apt-get",
        "npm",
        "yarn",
        "git",
        "conda",
    }

    SECRET_PROGRAMS: ClassVar[set[str]] = {
        "env",
        "printenv",
        "set",
        "export",
    }

    PRIVILEGE_PROGRAMS: ClassVar[set[str]] = {
        "sudo",
        "su",
        "doas",
        "kill",
        "pkill",
        "killall",
    }

    SHELL_PROGRAMS: ClassVar[set[str]] = {
        "sh",
        "bash",
        "zsh",
        "dash",
    }

    INTERPRETER_PROGRAMS: ClassVar[set[str]] = {
        "python",
        "python3",
        "perl",
        "ruby",
        "node",
    }

    SECRET_PATH_NAMES: ClassVar[set[str]] = {
        ".env",
        ".ssh",
        ".aws",
        ".netrc",
        "id_rsa",
        "id_ed25519",
        "shadow",
    }

    PYTEST_ALLOWED_FLAGS: ClassVar[set[str]] = {
        "-q",
        "-x",
        "-v",
        "-vv",
        "-s",
        "-rA",
        "-p",
        "no:cacheprovider",
    }

    PIPELINE_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^python3 --version$"),
        re.compile(r"^git --version$"),
        re.compile(r"^pytest --version$"),
        re.compile(r"^python3 -m pytest --version$"),
        re.compile(r"^pip --version$"),
        re.compile(r"^patch --version$"),
        re.compile(r"^uname -a$"),
        re.compile(r"^echo ready$"),
        re.compile(r"^sync$"),
        re.compile(r"^mkdir -p /workspace(/[a-zA-Z0-9_\-\./]+)?$"),
        re.compile(r"^printf %s '[a-zA-Z0-9+/=]+' \| base64 -d >>? /workspace/[a-zA-Z0-9_\-\./]+$"),
        re.compile(r"^sha256sum /workspace/[a-zA-Z0-9_\-\./]+$"),
        re.compile(r"^cat /workspace/[a-zA-Z0-9_\-\./]+$"),
        re.compile(r"^base64 -- /workspace/[a-zA-Z0-9_\-\./]+$"),
        re.compile(r"^base64 /workspace/[a-zA-Z0-9_\-\./]+$"),
        re.compile(r"^python3 -m pytest /workspace/.*$"),
        re.compile(r"^cp -r /workspace/case/\. /workspace/scratch_ref/?$"),
        re.compile(r"^rm -rf /workspace/case/\.pytest_cache$"),
        re.compile(r"^python3 -m pip install pytest$"),
        re.compile(
            r"^python3 -m http\.server \d+ --directory /workspace(/[a-zA-Z0-9_\-\./]+)? > /dev/null 2>&1 &$"
        ),
        re.compile(r"^python3 -m http\.server \d+ --directory /workspace(/[a-zA-Z0-9_\-\./]+)?$"),
        re.compile(r"^find /workspace/case -type f.*$"),
    ]

    FORBIDDEN_TEST_IMPORTS: ClassVar[set[str]] = {
        "os",
        "sub" + "process",
        "socket",
        "shutil",
        "urllib",
        "http",
        "requests",
    }

    @classmethod
    def evaluate(cls, command: str, origin: str = ORIGIN_AGENT) -> GuardDecision:
        if origin == ORIGIN_UNGUARDED:
            return GuardDecision(True, "unguarded_control", "Allowed under unguarded control")

        if not command or not command.strip():
            return GuardDecision(False, "empty_command", "Command cannot be empty")

        clean_cmd = command.rstrip("\r\n")
        if len(clean_cmd) > GUARD_MAX_CMD_LEN:
            return GuardDecision(
                False, "command_too_long", f"Command length exceeds {GUARD_MAX_CMD_LEN}"
            )

        for ch in clean_cmd:
            if ord(ch) < 32 and ch not in ("\t", "\n"):
                return GuardDecision(False, "control_char", "Control characters not allowed")

        if origin == ORIGIN_PIPELINE:
            return cls._evaluate_pipeline(clean_cmd)

        return cls._evaluate_agent(clean_cmd)

    @classmethod
    def _evaluate_pipeline(cls, command: str) -> GuardDecision:
        for pattern in cls.PIPELINE_PATTERNS:
            if pattern.match(command):
                return GuardDecision(True, "pipeline_allow", "Allowed pipeline template")
        return GuardDecision(
            False, "pipeline_unrecognized", f"Pipeline command not recognized: {command}"
        )

    @classmethod
    def _split_into_segments(cls, command: str) -> list[str]:
        segments = []
        cur: list[str] = []
        in_single = False
        in_double = False
        i = 0
        n = len(command)

        while i < n:
            ch = command[i]
            if ch == "'" and not in_double:
                in_single = not in_single
                cur.append(ch)
                i += 1
                continue
            if ch == '"' and not in_single:
                in_double = not in_double
                cur.append(ch)
                i += 1
                continue

            if command[i] == "\\" and i + 1 < n:
                cur.append(command[i : i + 2])
                i += 2
                continue

            if not in_single and not in_double:
                # Check 2-char separators: &&, ||, $(
                if i + 1 < n and command[i : i + 2] in ("&&", "||", "$("):
                    seg = "".join(cur).strip()
                    if seg:
                        segments.append(seg)
                    cur = []
                    i += 2
                    continue
                # Check 1-char separators: ;, |, &, \n, `
                if ch in (";", "|", "&", "\n", "`"):
                    seg = "".join(cur).strip()
                    if seg:
                        segments.append(seg)
                    cur = []
                    i += 1
                    continue

            cur.append(ch)
            i += 1

        last_seg = "".join(cur).strip()
        if last_seg:
            segments.append(last_seg)
        return segments

    @classmethod
    def _is_secret_path(cls, path_str: str) -> bool:
        norm = posixpath.normpath(path_str)
        if norm.startswith("/proc/") and norm.endswith("/environ"):
            return True
        parts = norm.split("/")
        for part in parts:
            if part in cls.SECRET_PATH_NAMES:
                return True
            if part.startswith(".env."):
                return True
        return False

    @classmethod
    def _evaluate_agent(cls, command: str) -> GuardDecision:
        segments = cls._split_into_segments(command)
        if not segments:
            return GuardDecision(False, "empty_command", "No valid command segments found")

        # Evaluate deny rules on programs and path arguments across all segments
        for seg in segments:
            seg_strip = seg.strip()
            if not seg_strip:
                continue

            # Fork bomb check
            if seg_strip.startswith(":(){") or ":(){ :|:& };:" in seg_strip:
                return GuardDecision(False, "resource_exhaustion", "Fork bomb detected")
            if "while true" in seg_strip or "while :" in seg_strip:
                return GuardDecision(False, "resource_exhaustion", "Infinite loop detected")

            try:
                tokens = shlex.split(seg_strip)
            except ValueError:
                # Syntax error in shell quoting
                return GuardDecision(
                    False, "interpreter_bypass", "Unclosed quote or shell syntax error"
                )

            if not tokens:
                continue

            prog = os.path.basename(tokens[0])

            # Check mkfs* prefix
            if prog.startswith("mkfs"):
                return GuardDecision(
                    False, "destructive_fs", f"Filesystem format command prohibited: {prog}"
                )
            if prog.startswith("stress"):
                return GuardDecision(
                    False, "resource_exhaustion", f"Resource stress command prohibited: {prog}"
                )

            # Specific program deny rules
            if prog in cls.DESTRUCTIVE_PROGRAMS:
                if prog == "mv":
                    for t in tokens[1:]:
                        if not t.startswith("-") and not posixpath.normpath(t).startswith(
                            "/workspace/case"
                        ):
                            return GuardDecision(
                                False,
                                "destructive_fs",
                                "Moving files outside /workspace/case prohibited",
                            )
                return GuardDecision(
                    False, "destructive_fs", f"Destructive command prohibited: {prog}"
                )

            if prog in cls.RESOURCE_PROGRAMS:
                return GuardDecision(
                    False, "resource_exhaustion", f"Resource exhaustion command prohibited: {prog}"
                )

            if prog in cls.POWER_PROGRAMS:
                return GuardDecision(
                    False, "power_control", f"Power control command prohibited: {prog}"
                )

            if prog in cls.NETWORK_PROGRAMS:
                return GuardDecision(False, "network_egress", f"Network command prohibited: {prog}")

            if prog in cls.PACKAGE_PROGRAMS:
                return GuardDecision(
                    False, "package_install", f"Package manager prohibited: {prog}"
                )

            if prog in cls.SECRET_PROGRAMS:
                return GuardDecision(
                    False, "secret_read", f"Secret/environment inspection prohibited: {prog}"
                )

            if prog in cls.PRIVILEGE_PROGRAMS:
                return GuardDecision(False, "privilege", f"Privilege escalation prohibited: {prog}")

            if prog in cls.SHELL_PROGRAMS:
                return GuardDecision(
                    False, "interpreter_bypass", f"Interactive shell prohibited: {prog}"
                )

            if prog in cls.INTERPRETER_PROGRAMS:
                if any(flag in tokens[1:] for flag in ("-c", "-e")):
                    return GuardDecision(
                        False,
                        "interpreter_bypass",
                        f"Interpreter inline execution prohibited: {prog}",
                    )
                if len(tokens) > 2 and tokens[1] == "-m" and tokens[2] == "pip":
                    return GuardDecision(False, "package_install", "python -m pip is prohibited")

            # Check arguments across all tokens in this segment
            for arg_idx, arg in enumerate(tokens[1:], start=1):
                if arg in ("/dev/zero", "/dev/urandom"):
                    return GuardDecision(False, "resource_exhaustion", "Device stream prohibited")
                if prog in ("chmod", "chown") and "-R" in arg:
                    return GuardDecision(
                        False, "destructive_fs", "Recursive permission modification prohibited"
                    )
                if prog == "find" and arg in ("-exec", "-execdir", "-delete"):
                    return GuardDecision(
                        False, "destructive_fs", "find with execution or delete flag prohibited"
                    )

                # Secret path check
                if prog == "grep" and arg_idx == 1 and not arg.startswith("-"):
                    # Exempt grep pattern from path and secret checks
                    continue
                if cls._is_secret_path(arg):
                    return GuardDecision(
                        False, "secret_read", f"Access to secret path prohibited: {arg}"
                    )

        in_single = False
        in_double = False
        i = 0
        n = len(command)
        pipe_count = 0

        while i < n:
            ch = command[i]
            if ch == "'" and not in_double:
                in_single = not in_single
                i += 1
                continue
            if ch == '"' and not in_single:
                in_double = not in_double
                i += 1
                continue

            if not in_single:
                if ch == ";":
                    return GuardDecision(False, "metachar_semicolon", "Semicolons prohibited")
                if ch == "&":
                    if command[i : i + 4] == "&> /" or command[i : i + 4] == "2>&1":
                        i += 1
                        continue
                    return GuardDecision(False, "metachar_ampersand", "Ampersands prohibited")
                if ch == "`":
                    return GuardDecision(False, "metachar_backtick", "Backticks prohibited")
                if ch == "$":
                    return GuardDecision(
                        False, "metachar_dollar", "Shell variable expansion prohibited"
                    )
                if ch in (">", "<"):
                    if command[i : i + 4] == "2>&1":
                        i += 1
                        continue
                    return GuardDecision(False, "metachar_redirect", "I/O redirection prohibited")
                if ch == "|":
                    pipe_count += 1
                    if pipe_count > 1:
                        return GuardDecision(False, "metachar_pipe", "Multiple pipes prohibited")
            i += 1

        for seg in segments:
            tokens = shlex.split(seg.strip())
            if not tokens:
                continue

            prog = os.path.basename(tokens[0])

            if prog == "python3":
                if len(tokens) >= 3 and tokens[1] == "-m" and tokens[2] == "pytest":
                    res = cls._check_pytest_command(tokens[3:])
                    if not res.allowed:
                        return res
                    continue
                return GuardDecision(
                    False, "not_allow_listed", "python3 is only allowed with '-m pytest'"
                )

            if prog not in cls.ALLOWED_PROGRAMS:
                return GuardDecision(False, "not_allow_listed", f"Program not allow-listed: {prog}")

            # Specific program argument checks
            if prog == "sed":
                if not any(t == "-n" for t in tokens[1:]):
                    return GuardDecision(False, "not_allow_listed", "sed is only allowed with -n")
                if any(t == "-i" for t in tokens[1:]):
                    return GuardDecision(False, "destructive_fs", "sed -i is prohibited")

            # Check paths and path escapes
            is_grep = prog == "grep"
            pattern_skipped = False

            for arg in tokens[1:]:
                if arg.startswith("-"):
                    continue
                if is_grep and not pattern_skipped:
                    pattern_skipped = True
                    continue

                # Check path bounds
                norm = posixpath.normpath(
                    posixpath.join("/workspace/case", arg) if not arg.startswith("/") else arg
                )
                if not norm.startswith("/workspace/case") and norm != "/workspace/case":
                    return GuardDecision(
                        False, "path_escape", f"Path escapes /workspace/case: {arg}"
                    )

        return GuardDecision(True, "agent_allow", "Command allowed")

    @classmethod
    def _check_pytest_command(cls, args: list[str]) -> GuardDecision:
        skip_next = False
        for i, arg in enumerate(args):
            if skip_next:
                skip_next = False
                continue

            if arg in ("-p",):
                if i + 1 < len(args) and args[i + 1] == "no:cacheprovider":
                    skip_next = True
                    continue
                return GuardDecision(
                    False, "pytest_flag_not_allowed", f"Plugin flag not allowed: {arg}"
                )

            if arg.startswith("-p"):
                if arg == "-pno:cacheprovider":
                    continue
                return GuardDecision(
                    False, "pytest_flag_not_allowed", f"Plugin flag not allowed: {arg}"
                )

            if arg.startswith("--tb="):
                val = arg.split("=", 1)[1]
                if val in ("short", "long", "line", "no"):
                    continue
                return GuardDecision(False, "pytest_flag_not_allowed", f"Invalid tb option: {arg}")

            if arg.startswith("--maxfail="):
                try:
                    int(arg.split("=", 1)[1])
                    continue
                except ValueError:
                    return GuardDecision(
                        False, "pytest_flag_not_allowed", f"Invalid maxfail option: {arg}"
                    )

            if arg == "-k":
                skip_next = True
                continue

            if arg in cls.PYTEST_ALLOWED_FLAGS:
                continue

            if arg.startswith("-"):
                return GuardDecision(
                    False, "pytest_flag_not_allowed", f"Pytest flag not allowed: {arg}"
                )

            # Positional argument must be a path under /workspace/case
            norm = posixpath.normpath(
                posixpath.join("/workspace/case", arg) if not arg.startswith("/") else arg
            )
            if not norm.startswith("/workspace/case"):
                return GuardDecision(
                    False, "path_escape", f"Pytest path outside /workspace/case: {arg}"
                )

        return GuardDecision(True, "pytest_allow", "Pytest command allowed")

    @classmethod
    def evaluate_test_file_write(cls, content: bytes | str) -> GuardDecision:
        raw_text = (
            content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
        )
        if len(raw_text.encode("utf-8")) > MAX_TEST_FILE_BYTES:
            return GuardDecision(
                False, "test_file_too_large", f"Test file exceeds {MAX_TEST_FILE_BYTES} bytes"
            )

        if not any(token in raw_text for token in ("def test_", "assert ", "@pytest.mark")):
            return GuardDecision(
                False, "test_content_invalid", "Test file must contain test functions or assertions"
            )

        try:
            tree = ast.parse(raw_text)
        except SyntaxError as exc:
            return GuardDecision(
                False, "test_syntax_error", f"Test file contains syntax error: {exc}"
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod in cls.FORBIDDEN_TEST_IMPORTS:
                        return GuardDecision(
                            False,
                            "test_imports_forbidden",
                            f"Import forbidden in tests: {root_mod}",
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_mod = node.module.split(".")[0]
                if root_mod in cls.FORBIDDEN_TEST_IMPORTS:
                    return GuardDecision(
                        False, "test_imports_forbidden", f"Import forbidden in tests: {root_mod}"
                    )

            # Check calls for eval / exec / compile
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("eval", "exec", "compile")
            ):
                return GuardDecision(
                    False, "test_execution_forbidden", f"Direct call to {node.func.id} forbidden"
                )

        return GuardDecision(True, "test_write_allow", "Test content accepted")

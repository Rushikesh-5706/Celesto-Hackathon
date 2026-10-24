from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    passed: bool
    reason_code: str
    details: str
    failure_type: str | None = None
    test_name: str | None = None
    traceback: str | None = None


RE_FILE_EXCEPTION = re.compile(r"^\S+:\d+:\s*([A-Za-z_][\w.]*)\s*$")
RE_E_LINE = re.compile(r"^E\s+([A-Za-z_][\w.]*)(:|\s|$)")

ALWAYS_REJECTED_EXCEPTIONS = {
    "ImportError",
    "ModuleNotFoundError",
    "SyntaxError",
    "NameError",
    "IndentationError",
}


def extract_exception_type(failure_type_attr: str, failure_text: str, message: str) -> str:
    # 1. Type attribute if non-empty
    if failure_type_attr and failure_type_attr.strip():
        return failure_type_attr.strip()

    lines = [line.strip() for line in failure_text.splitlines() if line.strip()]

    # 2. Last line of failure text matching ^\S+:\d+: ([A-Za-z_][\w.]*)\s*$
    for line in reversed(lines):
        m = RE_FILE_EXCEPTION.match(line)
        if m:
            return m.group(1)

    # 3. Last E line matching ^E\s+([A-Za-z_][\w.]*)(:|\s|$)
    for line in reversed(lines):
        m = RE_E_LINE.match(line)
        if m:
            cand = m.group(1)
            if cand != "assert":
                return cand

    # 4. If text contains an assert line prefixed by E or message contains assert
    for line in lines:
        if (
            line.startswith("E   assert")
            or line.startswith("E  assert")
            or line == "E   AssertionError"
        ):
            return "AssertionError"
    if "assert " in message or "AssertionError" in message:
        return "AssertionError"

    return "unclassified_failure"


def parse_and_classify_junit(
    junit_xml: str,
    target_symbol: str = "",
    expected_exception: str = "AssertionError",
    test_source: str = "",
    source_files: list[str] | None = None,
) -> ClassificationResult:
    try:
        root = ET.fromstring(junit_xml)
    except ET.ParseError as e:
        return ClassificationResult(
            passed=False,
            reason_code="collection_error",
            details=f"Malformed JUnit XML: {e}",
        )

    # Find testsuite element
    suite = root if root.tag == "testsuite" else root.find(".//testsuite")
    if suite is None:
        return ClassificationResult(
            passed=False,
            reason_code="collection_error",
            details="Missing <testsuite> element in JUnit XML",
        )

    total_tests = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))

    if total_tests != 1 or failures != 1 or errors != 0:
        return ClassificationResult(
            passed=False,
            reason_code="collection_error",
            details=f"Expected exactly 1 test, 1 failure, 0 errors; got {total_tests} tests, {failures} failures, {errors} errors",
        )

    testcase = suite.find(".//testcase")
    if testcase is None:
        return ClassificationResult(
            passed=False,
            reason_code="collection_error",
            details="No <testcase> found in JUnit XML",
        )

    test_name = testcase.attrib.get("name", "")
    failure_node = testcase.find("failure")
    if failure_node is None:
        return ClassificationResult(
            passed=False,
            reason_code="collection_error",
            details="Test did not record a <failure> node",
        )

    fail_type_attr = failure_node.attrib.get("type", "")
    traceback = failure_node.text or ""
    message = failure_node.attrib.get("message", "")

    extracted_type = extract_exception_type(fail_type_attr, traceback, message)
    if extracted_type == "unclassified_failure":
        return ClassificationResult(
            passed=False,
            reason_code="unclassified_failure",
            details="Could not determine exception type from failure traceback or message",
            failure_type=extracted_type,
            test_name=test_name,
            traceback=traceback,
        )

    if extracted_type in ALWAYS_REJECTED_EXCEPTIONS:
        return ClassificationResult(
            passed=False,
            reason_code="wrong_failure_type",
            details=f"Rejected collection/syntax/import exception: {extracted_type}",
            failure_type=extracted_type,
            test_name=test_name,
            traceback=traceback,
        )

    expected = expected_exception or "AssertionError"
    if extracted_type != "AssertionError" and extracted_type != expected:
        return ClassificationResult(
            passed=False,
            reason_code="wrong_failure_type",
            details=f"Extracted exception '{extracted_type}' does not match expected '{expected}' or 'AssertionError'",
            failure_type=extracted_type,
            test_name=test_name,
            traceback=traceback,
        )

    target_exercised = False
    if target_symbol and (target_symbol in test_source or target_symbol in traceback):
        target_exercised = True

    if source_files:
        for sf in source_files:
            if sf in traceback:
                target_exercised = True
                break

    # If traceback mentions a non-test frame in repo
    for line in traceback.splitlines():
        if "/workspace/case/" in line and "/tests/" not in line:
            target_exercised = True
            break
        if "repo/" in line and "test" not in line:
            target_exercised = True
            break

    if not target_exercised:
        return ClassificationResult(
            passed=False,
            reason_code="target_not_exercised",
            details=f"Target '{target_symbol}' was not exercised in test source or traceback",
            failure_type=extracted_type,
            test_name=test_name,
            traceback=traceback,
        )

    return ClassificationResult(
        passed=True,
        reason_code="ok",
        details="Failure successfully matched right-reason criteria",
        failure_type=extracted_type,
        test_name=test_name,
        traceback=traceback,
    )

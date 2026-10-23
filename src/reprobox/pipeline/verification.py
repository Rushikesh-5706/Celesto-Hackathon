"""Mechanical right-reason verification and JUnit XML classification."""

from __future__ import annotations

import logging
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


def parse_and_classify_junit(
    junit_xml: str,
    target_symbol: str,
    expected_exception: str = "AssertionError",
    test_source: str = "",
) -> ClassificationResult:
    """Parse pytest JUnit XML and verify failure is for the right reason."""
    try:
        root = ET.fromstring(junit_xml)
    except ET.ParseError as e:
        return ClassificationResult(
            passed=False,
            reason_code="collection_error",
            details=f"Malformed JUnit XML: {e}",
        )

    # Find testsuite element
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return ClassificationResult(
            passed=False,
            reason_code="collection_error",
            details="Missing <testsuite> root element in JUnit XML",
        )

    total_tests = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))

    if total_tests != 1 or failures != 1 or errors != 0:
        return ClassificationResult(
            passed=False,
            reason_code="collection_error",
            details=f"Expected exactly 1 test and 1 failure, got {total_tests} tests, {failures} failures, {errors} errors",
        )

    testcase = suite.find("testcase")
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

    fail_type = failure_node.attrib.get("type", "")
    traceback = failure_node.text or ""

    # Check 2: Failure type matches AssertionError or declared expected_exception
    # Reject syntax, import, name, type, and attribute errors
    disallowed_exceptions = (
        "ImportError",
        "ModuleNotFoundError",
        "SyntaxError",
        "NameError",
        "TypeError",
        "AttributeError",
    )

    if any(dis in fail_type for dis in disallowed_exceptions):
        return ClassificationResult(
            passed=False,
            reason_code="wrong_failure_type",
            details=f"Failure type '{fail_type}' is disallowed runtime/syntax error",
            failure_type=fail_type,
            test_name=test_name,
            traceback=traceback,
        )

    if expected_exception not in fail_type and "AssertionError" not in fail_type:
        return ClassificationResult(
            passed=False,
            reason_code="wrong_failure_type",
            details=f"Expected {expected_exception}, got '{fail_type}'",
            failure_type=fail_type,
            test_name=test_name,
            traceback=traceback,
        )

    # Check 3: target_symbol is exercised in test source or traceback
    if target_symbol:
        exercised = (target_symbol in traceback) or (target_symbol in test_source)
        if not exercised:
            return ClassificationResult(
                passed=False,
                reason_code="target_not_exercised",
                details=f"Target symbol '{target_symbol}' was not exercised in traceback or test source",
                failure_type=fail_type,
                test_name=test_name,
                traceback=traceback,
            )

    return ClassificationResult(
        passed=True,
        reason_code="ok",
        details="Failure successfully matched right-reason criteria",
        failure_type=fail_type,
        test_name=test_name,
        traceback=traceback,
    )

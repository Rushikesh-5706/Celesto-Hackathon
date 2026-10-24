from __future__ import annotations

from pathlib import Path

from reprobox.pipeline.verification import parse_and_classify_junit

DATA_DIR = Path(__file__).resolve().parent / "data"


def test_classify_real_junit_assertion():
    xml_path = DATA_DIR / "junit_assertion.xml"
    xml_content = xml_path.read_text(encoding="utf-8")
    test_src = "def test_last_item_included(): paginate(data, 1, 10)"
    res = parse_and_classify_junit(
        junit_xml=xml_content,
        target_symbol="paginate",
        expected_exception="AssertionError",
        test_source=test_src,
    )
    assert res.passed
    assert res.reason_code == "ok"
    assert res.failure_type == "AssertionError"


def test_classify_real_junit_typeerror_with_matching_exception():
    xml_path = DATA_DIR / "junit_typeerror.xml"
    xml_content = xml_path.read_text(encoding="utf-8")
    test_src = "def test_timezone_aware_comparison(): is_expired(aware_future)"
    res = parse_and_classify_junit(
        junit_xml=xml_content,
        target_symbol="is_expired",
        expected_exception="TypeError",
        test_source=test_src,
    )
    assert res.passed
    assert res.reason_code == "ok"
    assert res.failure_type == "TypeError"


def test_classify_real_junit_typeerror_with_mismatched_exception():
    xml_path = DATA_DIR / "junit_typeerror.xml"
    xml_content = xml_path.read_text(encoding="utf-8")
    test_src = "def test_timezone_aware_comparison(): is_expired(aware_future)"
    res = parse_and_classify_junit(
        junit_xml=xml_content,
        target_symbol="is_expired",
        expected_exception="AssertionError",
        test_source=test_src,
    )
    assert not res.passed
    assert res.reason_code == "wrong_failure_type"
    assert res.failure_type == "TypeError"


def test_classify_real_junit_importerror():
    xml_path = DATA_DIR / "junit_importerror.xml"
    xml_content = xml_path.read_text(encoding="utf-8")
    res = parse_and_classify_junit(
        junit_xml=xml_content,
        target_symbol="dummy",
        expected_exception="AssertionError",
        test_source="def test_import(): pass",
    )
    assert not res.passed
    assert res.reason_code == "collection_error"


def test_classify_synthetic_edge_cases():
    # 1. Malformed XML
    res = parse_and_classify_junit("not xml at all")
    assert not res.passed
    assert res.reason_code == "collection_error"

    # 2. No testsuite
    res = parse_and_classify_junit("<other></other>")
    assert not res.passed
    assert res.reason_code == "collection_error"

    # 3. Multiple tests or 0 failures
    xml_no_fail = '<testsuite tests="1" failures="0" errors="0"><testcase name="t1"/></testsuite>'
    res = parse_and_classify_junit(xml_no_fail)
    assert not res.passed
    assert res.reason_code == "collection_error"

    # 4. Target not exercised
    xml_fail = (
        '<testsuite tests="1" failures="1" errors="0">'
        '<testcase name="test_foo">'
        '<failure message="AssertionError: assert 1 == 2">E   assert 1 == 2</failure>'
        "</testcase></testsuite>"
    )
    res = parse_and_classify_junit(
        xml_fail,
        target_symbol="my_special_func",
        expected_exception="AssertionError",
        test_source="def test_foo(): assert 1 == 2",
    )
    assert not res.passed
    assert res.reason_code == "target_not_exercised"

    # 5. Target exercised in test source
    res_ok = parse_and_classify_junit(
        xml_fail,
        target_symbol="my_special_func",
        expected_exception="AssertionError",
        test_source="def test_foo(): my_special_func(); assert 1 == 2",
    )
    assert res_ok.passed
    assert res_ok.reason_code == "ok"

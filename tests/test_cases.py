"""Static integrity validation of all fixture cases per Section 11."""

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = REPO_ROOT / "fixtures" / "cases"

REQUIRED_FIELDS = {"case_id", "title", "bug_class", "target_symbol", "expected_exception", "source_files"}


def test_all_cases_static_structure():
    assert CASES_DIR.exists(), "fixtures/cases directory missing"
    case_dirs = [d for d in CASES_DIR.iterdir() if d.is_dir()]
    assert len(case_dirs) >= 23, f"Expected at least 23 cases, found {len(case_dirs)}"

    for cdir in case_dirs:
        # 1. case.json checks
        cjson_path = cdir / "case.json"
        assert cjson_path.exists(), f"Missing case.json in {cdir.name}"
        meta = json.loads(cjson_path.read_text(encoding="utf-8"))

        for req in REQUIRED_FIELDS:
            assert req in meta, f"{cdir.name}/case.json missing required field '{req}'"
        assert meta["case_id"] == cdir.name

        # 2. repo checks
        repo_dir = cdir / "repo"
        assert repo_dir.exists(), f"Missing repo/ in {cdir.name}"
        tests = list(repo_dir.glob("**/test_*.py")) + list(repo_dir.glob("**/*_test.py"))
        assert len(tests) >= 1, f"repo/ in {cdir.name} must contain at least one test file"

        # 3. reference checks
        ref_dir = cdir / "reference"
        assert ref_dir.exists(), f"Missing reference/ in {cdir.name}"
        ref_files = [str(f.relative_to(ref_dir)) for f in ref_dir.glob("**/*") if f.is_file()]
        declared_files = meta["source_files"]
        assert sorted(ref_files) == sorted(declared_files), f"reference/ in {cdir.name} must exactly match source_files"

        # 4. AST parse checks
        for py_file in cdir.glob("**/*.py"):
            try:
                ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except SyntaxError as e:
                raise AssertionError(f"Syntax error in {py_file}: {e}") from e

        # 5. issue.md check: must not leak reference code lines > 30 chars
        issue_file = cdir / "issue.md"
        assert issue_file.exists(), f"Missing issue.md in {cdir.name}"
        issue_text = issue_file.read_text(encoding="utf-8")

        for rel in declared_files:
            ref_path = ref_dir / rel
            if ref_path.exists():
                for line in ref_path.read_text(encoding="utf-8").splitlines():
                    cleaned = line.strip()
                    if len(cleaned) > 30:
                        assert cleaned not in issue_text, f"issue.md in {cdir.name} leaks reference line: {cleaned}"

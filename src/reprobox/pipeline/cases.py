"""Case fixture loading, metadata parsing, and source file tree handling."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CaseFixture:
    case_id: str
    title: str
    bug_class: str
    target_symbol: str
    expected_exception: str
    source_files: list[str]
    issue_text: str
    repo_path: Path
    reference_path: Path
    author_probe_path: Path | None = None

    @classmethod
    def load(cls, case_dir: Path) -> CaseFixture:
        case_json_path = case_dir / "case.json"
        if not case_json_path.exists():
            raise FileNotFoundError(f"Missing case.json in {case_dir}")

        meta: dict[str, Any] = json.loads(case_json_path.read_text(encoding="utf-8"))
        issue_file = case_dir / "issue.md"
        issue_text = (
            issue_file.read_text(encoding="utf-8") if issue_file.exists() else meta.get("title", "")
        )

        author_probe = case_dir / "author_probe" / "test_probe.py"
        return cls(
            case_id=meta["case_id"],
            title=meta.get("title", meta["case_id"]),
            bug_class=meta.get("bug_class", "unknown"),
            target_symbol=meta.get("target_symbol", ""),
            expected_exception=meta.get("expected_exception", "AssertionError"),
            source_files=meta.get("source_files", []),
            issue_text=issue_text,
            repo_path=case_dir / "repo",
            reference_path=case_dir / "reference",
            author_probe_path=author_probe if author_probe.exists() else None,
        )

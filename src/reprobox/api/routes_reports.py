"""Routes for serving fixtures, cases, and generated reports."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from reprobox.constants import REPORT_WHITELIST
from reprobox.settings import settings

router = APIRouter(prefix="/api")


@router.get("/cases")
def list_cases() -> JSONResponse:
    """List available bug fixture case IDs."""
    fixtures_dir = settings.fixtures_dir
    cases: list[str] = []
    if fixtures_dir.exists():
        for p in sorted(fixtures_dir.iterdir()):
            if p.is_dir() and (p / "case.json").exists():
                cases.append(p.name)
    return JSONResponse(status_code=200, content={"cases": cases, "count": len(cases)})


@router.get("/reports")
def list_reports() -> JSONResponse:
    """List available generated report filenames."""
    available: list[str] = []
    for name in sorted(REPORT_WHITELIST):
        path = _resolve_report_path(name)
        if path and path.exists():
            available.append(name)
    return JSONResponse(status_code=200, content={"reports": available, "whitelist": sorted(REPORT_WHITELIST)})


def _resolve_report_path(name: str) -> Path | None:
    """Safely map whitelisted name to local filesystem path."""
    if name not in REPORT_WHITELIST:
        return None

    if name == "README.md":
        return Path(__file__).resolve().parents[3] / "README.md"
    if name == "commands.jsonl":
        return settings.audit_log_path

    # Remaining files are in reports/
    return settings.reports_dir / name


@router.get("/reports/{name}")
def get_report(name: str):
    """Serve a specific report by name."""
    if name not in REPORT_WHITELIST:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": f"Report '{name}' not found"})

    path = _resolve_report_path(name)
    if not path or not path.exists():
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": f"Report '{name}' has not been generated yet"})

    if name.endswith(".json") or name.endswith(".jsonl"):
        media_type = "application/json"
    elif name.endswith(".md"):
        media_type = "text/markdown"
    else:
        media_type = "text/plain"

    return FileResponse(path, media_type=media_type)

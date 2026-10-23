"""Orphan sandbox sweeping utility."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from reprobox.sandbox.celesto_provider import CelestoProvider
from reprobox.sandbox.lifecycle import sweep_orphans
from reprobox.sandbox.provider import ComputerProvider
from reprobox.settings import settings

logger = logging.getLogger(__name__)


def run_orphan_sweep(
    provider: ComputerProvider | None = None,
    log_path: Path | None = None,
) -> list[str]:
    """Execute orphan sweep and write output to log file."""
    prov = provider or CelestoProvider()
    target_log = log_path or (settings.reports_dir / "evidence" / "orphan_sweep.log")
    target_log.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).isoformat()
    lines = [f"=== ORPHAN SWEEP START {ts} ==="]

    deleted = sweep_orphans(prov)
    lines.append(f"Deleted {len(deleted)} leftover sandboxes: {deleted}")
    lines.append("=== ORPHAN SWEEP END ===")

    output = "\n".join(lines) + "\n"
    with target_log.open("a", encoding="utf-8") as f:
        f.write(output)

    print(output)
    return deleted

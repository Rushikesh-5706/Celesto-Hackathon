from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.factory import get_default_provider
from reprobox.sandbox.lifecycle import sweep_orphans
from reprobox.settings import settings

logger = logging.getLogger(__name__)


def run_orphan_sweep(
    provider: AuditedProvider | None = None,
    log_path: Path | None = None,
    list_account: bool = False,
) -> list[str]:
    prov = provider or get_default_provider()
    target_log = log_path or (settings.reports_dir / "evidence" / "orphan_sweep.log")
    target_log.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).isoformat()
    lines = [f"=== ORPHAN SWEEP START {ts} (list_account={list_account}) ==="]

    deleted = sweep_orphans(prov, list_account=list_account)
    lines.append(f"Deleted {len(deleted)} leftover sandboxes: {deleted}")
    lines.append("=== ORPHAN SWEEP END ===")

    output = "\n".join(lines) + "\n"
    with target_log.open("a", encoding="utf-8") as f:
        f.write(output)

    print(output)
    return deleted

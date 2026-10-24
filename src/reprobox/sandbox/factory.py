from __future__ import annotations

from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.celesto_provider import CelestoProvider


def get_default_provider() -> AuditedProvider:
    return AuditedProvider(CelestoProvider())

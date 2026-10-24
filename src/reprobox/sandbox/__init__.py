from __future__ import annotations

from reprobox.sandbox.audit import AuditLogger, audit_logger
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.factory import get_default_provider
from reprobox.sandbox.guard import Guard, GuardDecision
from reprobox.sandbox.handle import GuestHandle
from reprobox.sandbox.lifecycle import ComputerRegistry, managed_computer, registry, sweep_orphans
from reprobox.sandbox.naming import is_valid_sandbox_name, new_sandbox_name
from reprobox.sandbox.provider import ComputerProvider, RunResult

__all__ = [
    "ComputerProvider",
    "RunResult",
    "AuditedProvider",
    "get_default_provider",
    "GuestHandle",
    "Guard",
    "GuardDecision",
    "AuditLogger",
    "audit_logger",
    "ComputerRegistry",
    "managed_computer",
    "registry",
    "sweep_orphans",
    "new_sandbox_name",
    "is_valid_sandbox_name",
]

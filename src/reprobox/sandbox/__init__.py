"""Sandbox execution plane: providers, lifecycle, guard, audit, and naming."""

from reprobox.sandbox.audit import AuditLogger, audit_logger
from reprobox.sandbox.celesto_provider import CelestoProvider
from reprobox.sandbox.guard import Guard, GuardDecision
from reprobox.sandbox.lifecycle import ComputerRegistry, managed_computer, registry, sweep_orphans
from reprobox.sandbox.naming import is_valid_sandbox_name, new_sandbox_name
from reprobox.sandbox.provider import ComputerProvider, RunResult

__all__ = [
    "ComputerProvider",
    "RunResult",
    "CelestoProvider",
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

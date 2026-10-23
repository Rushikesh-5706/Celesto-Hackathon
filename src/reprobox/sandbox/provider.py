"""Provider abstraction defining the sandbox computer interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int
    computer_id: str
    elapsed_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@runtime_checkable
class ComputerProvider(Protocol):
    """Protocol implemented by sandbox providers."""

    def create(self, name: str) -> Any:
        """Create and start a computer instance."""
        ...

    def run(self, computer: Any, command: str, timeout: int = 60) -> RunResult:
        """Run a command inside the computer."""
        ...

    def write_file(self, computer: Any, path: str, data: bytes) -> None:
        """Write binary data to an absolute path inside the computer."""
        ...

    def read_file(self, computer: Any, path: str) -> bytes:
        """Read binary data from an absolute path inside the computer."""
        ...

    def stop(self, computer: Any) -> None:
        """Stop the computer instance."""
        ...

    def start(self, computer: Any) -> None:
        """Start or resume a stopped computer instance."""
        ...

    def delete(self, computer: Any) -> None:
        """Delete the computer instance."""
        ...

    def exists(self, computer: Any) -> bool:
        """Check whether the computer exists."""
        ...

    def list_prefixed(self, prefix: str = "") -> list[str]:
        """List ids or names of active computers matching prefix."""
        ...

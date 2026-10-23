"""Sandbox naming utilities."""

from __future__ import annotations

import secrets
from collections.abc import Callable

from reprobox.constants import (
    SANDBOX_NAME_ALPHABET,
    SANDBOX_NAME_PREFIX,
    SANDBOX_NAME_RE,
    SANDBOX_NAME_SUFFIX_LEN,
)


def is_valid_sandbox_name(name: str) -> bool:
    """Validate sandbox name against the system format."""
    return bool(SANDBOX_NAME_RE.match(name))


def new_sandbox_name(exists_fn: Callable[[str], bool] | None = None, max_attempts: int = 50) -> str:
    """Generate a unique sandbox name matching sbx-[a-z0-9]{8,}.

    If exists_fn is provided, checks collisions and retries up to max_attempts.
    """
    for _ in range(max_attempts):
        suffix = "".join(
            secrets.choice(SANDBOX_NAME_ALPHABET) for _ in range(SANDBOX_NAME_SUFFIX_LEN)
        )
        name = f"{SANDBOX_NAME_PREFIX}{suffix}"
        if exists_fn is None or not exists_fn(name):
            return name
    raise RuntimeError(f"Failed to generate unique sandbox name after {max_attempts} attempts")

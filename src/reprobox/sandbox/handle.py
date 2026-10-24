from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GuestHandle:
    sandbox_name: str
    computer_id: str
    sdk_object: Any

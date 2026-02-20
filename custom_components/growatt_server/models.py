"""Models for the Growatt server integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import growattServer

    from .coordinator import GrowattCoordinator


@dataclass
class GrowattRuntimeData:
    """Runtime data for the Growatt integration."""

    api: growattServer.GrowattApi | growattServer.OpenApiV1
    total_coordinator: GrowattCoordinator
    devices: dict[str, GrowattCoordinator]
    login_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_login_time: float | None = None

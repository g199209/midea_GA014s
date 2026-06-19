from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GA014sApiClient, GA014sApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")


class GA014sCoordinator(DataUpdateCoordinator):
    """Polls the GA014s gateway and exposes combined AC data."""

    def __init__(self, hass: HomeAssistant, client: GA014sApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=10),
        )
        self._client = client

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        try:
            rooms = await self._client.get_room_list()
            units = await self._client.get_ac_list()
        except GA014sApiError as err:
            raise UpdateFailed(f"GA014s API error: {err}") from err

        result: dict[int, dict[str, Any]] = {}
        for unit in units:
            addr = int(unit["addr"])
            name = rooms[addr]["name"] if addr < len(rooms) else f"AC_{addr}"
            unit["name"] = name
            result[addr] = unit
        return result

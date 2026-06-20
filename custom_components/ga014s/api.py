"""Async API client for the GA014s gateway HTTP protocol."""
from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from .const import DOMAIN

_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")


class GA014sApiError(Exception):
    """Base exception for GA014s API errors."""


class GA014sApiConnectionError(GA014sApiError):
    """Connection error for GA014s API."""


class GA014sApiClient:
    """Async client for the GA014s HTTP API."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._host = host
        self._base_url = f"http://{host}/protocol.csp"
        self._session = session

    async def _request(self, params: dict[str, str]) -> dict[str, Any]:
        """Send a GET request to the gateway and return parsed JSON."""
        try:
            async with self._session.get(
                self._base_url, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    raise GA014sApiConnectionError(
                        f"HTTP {resp.status} from {self._host}"
                    )
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise GA014sApiConnectionError(f"Cannot connect to {self._host}: {err}") from err

        if data.get("error", 0) != 0:
            raise GA014sApiError(f"Device returned error: {data.get('error')}")

        return data

    async def get_gateway_info(self) -> dict[str, Any]:
        """Return gateway device information."""
        data = await self._request({"fname": "485", "opt": "whois", "function": "get"})
        return json.loads(data["arg"])

    async def get_room_list(self) -> list[dict[str, str]]:
        """Return the list of AC unit names indexed by address."""
        data = await self._request({"fname": "485", "opt": "getroomlist", "function": "get"})
        roomlist = json.loads(data["arg"]["roomlist"])
        return roomlist.get("aclist", [])

    async def get_ac_list(self) -> list[dict[str, Any]]:
        """Fetch all AC units by querying address ranges 0-9, 10-19, ..., 60-63."""
        all_units: list[dict[str, Any]] = []
        ranges = [(0, 9), (10, 19), (20, 29), (30, 39), (40, 49), (50, 59), (60, 63)]
        for haddr, taddr in ranges:
            data = await self._request({
                "fname": "485",
                "opt": "getaclist",
                "function": "get",
                "haddr": str(haddr),
                "taddr": str(taddr),
            })
            if data["arg"]:
                parsed = json.loads(data["arg"])
                all_units.extend(parsed.get("aclist", []))
        return all_units

    async def set_ac(
        self,
        addr: int,
        run_mode: int,
        fan_speed: int,
        cooling_temp: int,
        heating_temp: int,
        extflag: int = 0,
    ) -> None:
        """Set AC unit parameters via the setac endpoint."""
        await self._request({
            "fname": "485",
            "opt": "setac",
            "function": "set",
            "addr": str(addr),
            "run_mode": str(run_mode),
            "fan_speed": str(fan_speed),
            "cooling_temp": str(cooling_temp),
            "heating_temp": str(heating_temp),
            "extflag": str(extflag),
        })

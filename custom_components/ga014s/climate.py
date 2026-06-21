"""Climate platform for the GA014s integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_WINTER_MONTHS,
    DEFAULT_WINTER_MONTHS,
    DOMAIN,
    FAN_MODE_MAP,
    FAN_MODE_REVERSE,
    FAN_MODES,
    HVAC_MODE_MAP,
    HVAC_MODE_REVERSE,
    MAX_TEMP,
    MIN_TEMP,
    PRESET_AUX_HEAT,
    PRESET_MODES,
    PRESET_NONE,
    SWING_MODE_MAP,
)
from .coordinator import GA014sCoordinator

_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")

# After a command we show the commanded state immediately and keep showing it
# until a poll reads it back confirmed, so the UI never waits for the slow
# 485-bus / indoor-unit readback. The gateway can take well over 10s to reflect
# a change, so we confirm by value (not a fixed time window) to avoid flicker.
# OPTIMISTIC_TIMEOUT bounds how long we trust an unconfirmed command before
# falling back to the real state (covers commands the device rejects outright).
OPTIMISTIC_TIMEOUT = 45.0
# Delay before the first confirm poll, giving the device a head start to settle.
OPTIMISTIC_CONFIRM_DELAY = 4.0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up GA014s climate entities from a config entry."""
    coordinator: GA014sCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for addr, unit in coordinator.data.items():
        if unit.get("error", "0") != "0":
            continue
        entities.append(GA014sClimateEntity(coordinator, addr))
    async_add_entities(entities)


class GA014sClimateEntity(CoordinatorEntity[GA014sCoordinator], ClimateEntity):
    """Climate entity for a single GA014s AC indoor unit."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = 1.0
    _attr_fan_modes = FAN_MODES
    _attr_swing_modes = ["off", "on"]
    _attr_preset_modes = PRESET_MODES
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: GA014sCoordinator, addr: int) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._addr = addr
        self._optimistic: dict[str, str] = {}
        self._optimistic_deadline = 0.0
        self._confirm_unsub: Any = None
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{addr}"
        unit = coordinator.data.get(addr, {})
        self._attr_name = unit.get("name", f"AC {addr}")
        hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY, HVACMode.COOL, HVACMode.HEAT, HVACMode.DRY]
        if int(unit.get("is_have_auto_mode", "0")) != 0:
            hvac_modes.append(HVACMode.AUTO)
        self._attr_hvac_modes = hvac_modes
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_fan_mode = None
        self._attr_swing_mode = "off"
        self._attr_preset_mode = PRESET_NONE
        self._attr_hvac_action = None
        self._update_from_data(unit)

    def _update_from_data(self, unit: dict[str, Any]) -> None:
        """Update entity attributes from coordinator data."""
        if not unit:
            return
        self._attr_name = unit.get("name", self._attr_name)
        run_mode = int(unit.get("run_mode", "0"))
        self._attr_hvac_mode = HVACMode(HVAC_MODE_MAP.get(run_mode, "off"))
        self._attr_current_temperature = float(unit.get("room_temp", "0"))

        if run_mode in (2, 4):
            self._attr_target_temperature = float(unit.get("cool_temp_set", "0"))
        elif run_mode == 3:
            self._attr_target_temperature = float(unit.get("heat_temp_set", "0"))
        else:
            cool = float(unit.get("cool_temp_set", "0"))
            heat = float(unit.get("heat_temp_set", "0"))
            self._attr_target_temperature = cool if cool > 0 else heat

        if int(unit.get("is_auto_fan", "0")) != 0:
            self._attr_fan_mode = "auto"
        else:
            fan = int(unit.get("fan_speed", "0"))
            self._attr_fan_mode = FAN_MODE_MAP.get(fan) if fan > 0 else None

        self._attr_swing_mode = SWING_MODE_MAP.get(int(unit.get("is_swing", "0")), "off")
        self._attr_preset_mode = (
            PRESET_AUX_HEAT if int(unit.get("is_elec_heat", "0")) > 0 else PRESET_NONE
        )

        if run_mode == 0:
            self._attr_hvac_action = None
        elif run_mode == 2:
            target = float(unit.get("cool_temp_set", "0"))
            self._attr_hvac_action = (
                "cooling" if float(unit.get("room_temp", "0")) > target else "idle"
            )
        elif run_mode == 3:
            target = float(unit.get("heat_temp_set", "0"))
            self._attr_hvac_action = (
                "heating" if float(unit.get("room_temp", "0")) < target else "idle"
            )
        elif run_mode == 1:
            self._attr_hvac_action = "fan"
        elif run_mode == 5:
            self._attr_hvac_action = "drying"
        else:
            self._attr_hvac_action = "idle"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        unit = self.coordinator.data.get(self._addr)
        if unit is None:
            return
        # While a command is pending, keep showing the commanded state until the
        # gateway reads it back confirmed. A poll that still reports the old
        # value (device not yet settled) must not revert the UI, otherwise it
        # flickers e.g. off -> on -> off -> on. We give up only once the values
        # match (device caught up) or the timeout elapses (command rejected).
        if self._optimistic:
            confirmed = all(
                str(unit.get(key)) == val for key, val in self._optimistic.items()
            )
            if confirmed or self.hass.loop.time() >= self._optimistic_deadline:
                self._optimistic = {}
            else:
                return
        self._update_from_data(unit)
        self.async_write_ha_state()

    def _set_optimistic(self, **changes: Any) -> None:
        """Reflect commanded values in the UI immediately, then confirm later.

        Writes the commanded fields into the cached unit data and pushes the
        state right away so the card reacts instantly, instead of waiting for
        the slow gateway readback. The commanded fields are remembered so that
        subsequent polls keep showing them until the device confirms the change
        (see _handle_coordinator_update); a confirm poll is scheduled to pull
        the real state without waiting for the regular interval.
        """
        changes = {key: str(val) for key, val in changes.items()}
        unit = dict(self.coordinator.data.get(self._addr, {}))
        unit.update(changes)
        self.coordinator.data[self._addr] = unit
        self._optimistic = changes
        self._optimistic_deadline = self.hass.loop.time() + OPTIMISTIC_TIMEOUT
        self._update_from_data(unit)
        self.async_write_ha_state()

        if self._confirm_unsub is not None:
            self._confirm_unsub()
        self._confirm_unsub = async_call_later(
            self.hass, OPTIMISTIC_CONFIRM_DELAY, self._async_confirm_refresh
        )

    async def _async_confirm_refresh(self, _now: Any) -> None:
        """Poll the gateway to confirm a pending command's real state."""
        self._confirm_unsub = None
        await self.coordinator.async_request_refresh()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any pending confirm refresh."""
        if self._confirm_unsub is not None:
            self._confirm_unsub()
            self._confirm_unsub = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        unit = self.coordinator.data.get(self._addr, {})
        return {
            "addr": self._addr,
            "error": unit.get("error", "0"),
            "type": unit.get("type", ""),
            "is_auto_fan": unit.get("is_auto_fan", "0"),
            "is_have_auto_mode": unit.get("is_have_auto_mode", "0"),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        temp = int(kwargs.get(ATTR_TEMPERATURE, 0))
        unit = self.coordinator.data.get(self._addr, {})
        run_mode = int(unit.get("run_mode", "0"))
        extflag = self._calc_extflag(unit)
        await self.coordinator._client.set_ac(
            addr=self._addr,
            run_mode=run_mode,
            fan_speed=int(unit.get("fan_speed", "0")),
            cooling_temp=temp,
            heating_temp=temp,
            extflag=extflag,
        )
        # The gateway only echoes the temp field for the active mode; confirm on
        # that one so the optimistic state resolves cleanly.
        if run_mode == 3:
            self._set_optimistic(heat_temp_set=temp)
        else:
            self._set_optimistic(cool_temp_set=temp)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        run_mode = HVAC_MODE_REVERSE.get(hvac_mode.value, 0)
        unit = self.coordinator.data.get(self._addr, {})
        extflag = self._calc_extflag(unit)
        cool = int(unit.get("cool_temp_set", "26"))
        heat = int(unit.get("heat_temp_set", "26"))
        await self.coordinator._client.set_ac(
            addr=self._addr,
            run_mode=run_mode,
            fan_speed=int(unit.get("fan_speed", "0")),
            cooling_temp=cool,
            heating_temp=heat,
            extflag=extflag,
        )
        self._set_optimistic(run_mode=run_mode)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        unit = self.coordinator.data.get(self._addr, {})
        run_mode = int(unit.get("run_mode", "0"))
        extflag = self._calc_extflag(unit)
        cool = int(unit.get("cool_temp_set", "26"))
        heat = int(unit.get("heat_temp_set", "26"))
        if fan_mode == "auto":
            fan_speed = 8
        else:
            fan_speed = FAN_MODE_REVERSE.get(fan_mode, 0)
        await self.coordinator._client.set_ac(
            addr=self._addr,
            run_mode=run_mode,
            fan_speed=fan_speed,
            cooling_temp=cool,
            heating_temp=heat,
            extflag=extflag,
        )
        # In auto the gateway reports is_auto_fan and a device-chosen fan_speed,
        # so confirm only the flag; otherwise confirm the exact speed.
        if fan_mode == "auto":
            self._set_optimistic(is_auto_fan=1)
        else:
            self._set_optimistic(is_auto_fan=0, fan_speed=fan_speed)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode."""
        unit = self.coordinator.data.get(self._addr, {})
        run_mode = int(unit.get("run_mode", "0"))
        extflag = self._calc_extflag(unit)
        if swing_mode == "on":
            extflag |= 4
        else:
            extflag &= ~4
        cool = int(unit.get("cool_temp_set", "26"))
        heat = int(unit.get("heat_temp_set", "26"))
        await self.coordinator._client.set_ac(
            addr=self._addr,
            run_mode=run_mode,
            fan_speed=int(unit.get("fan_speed", "0")),
            cooling_temp=cool,
            heating_temp=heat,
            extflag=extflag,
        )
        self._set_optimistic(is_swing=1 if swing_mode == "on" else 0)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode (aux heat)."""
        unit = self.coordinator.data.get(self._addr, {})
        run_mode = int(unit.get("run_mode", "0"))
        extflag = self._calc_extflag(unit)
        if preset_mode == PRESET_AUX_HEAT:
            extflag |= 2
        else:
            extflag &= ~2
        cool = int(unit.get("cool_temp_set", "26"))
        heat = int(unit.get("heat_temp_set", "26"))
        await self.coordinator._client.set_ac(
            addr=self._addr,
            run_mode=run_mode,
            fan_speed=int(unit.get("fan_speed", "0")),
            cooling_temp=cool,
            heating_temp=heat,
            extflag=extflag,
        )
        self._set_optimistic(is_elec_heat=1 if preset_mode == PRESET_AUX_HEAT else 0)

    async def async_turn_on(self) -> None:
        """Turn the AC on in the seasonal mode.

        Heat during the configured winter months, cool otherwise. This follows
        the central system's seasonal master mode; a blind heat/cool guess can
        request the wrong mode and put the indoor unit into a conflict fault.
        """
        unit = self.coordinator.data.get(self._addr, {})
        run_mode = 3 if self._is_winter() else 2
        extflag = self._calc_extflag(unit)
        await self.coordinator._client.set_ac(
            addr=self._addr,
            run_mode=run_mode,
            fan_speed=int(unit.get("fan_speed", "0")) or 3,
            cooling_temp=int(unit.get("cool_temp_set", "26")),
            heating_temp=int(unit.get("heat_temp_set", "26")),
            extflag=extflag,
        )
        # Confirm on run_mode; the device picks the fan speed, which the next
        # poll fills in.
        self._set_optimistic(run_mode=run_mode)

    def _is_winter(self) -> bool:
        """Return whether the current month is configured as a winter month."""
        winter = self.coordinator.config_entry.options.get(
            CONF_WINTER_MONTHS, DEFAULT_WINTER_MONTHS
        )
        return dt_util.now().month in {int(m) for m in winter}

    async def async_turn_off(self) -> None:
        """Turn the AC off."""
        unit = self.coordinator.data.get(self._addr, {})
        extflag = self._calc_extflag(unit)
        cool = int(unit.get("cool_temp_set", "26"))
        heat = int(unit.get("heat_temp_set", "26"))
        await self.coordinator._client.set_ac(
            addr=self._addr,
            run_mode=0,
            fan_speed=int(unit.get("fan_speed", "0")),
            cooling_temp=cool,
            heating_temp=heat,
            extflag=extflag,
        )
        self._set_optimistic(run_mode=0)

    def _calc_extflag(self, unit: dict[str, Any]) -> int:
        """Calculate extflag bitmask from current aux heat and swing state."""
        extflag = 0
        if int(unit.get("is_elec_heat", "0")) > 0:
            extflag |= 2
        if int(unit.get("is_swing", "0")) > 0:
            extflag |= 4
        return extflag

"""Config flow for the GA014s integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import GA014sApiClient, GA014sApiError
from .const import CONF_WINTER_MONTHS, DEFAULT_WINTER_MONTHS, DOMAIN


class GA014sFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for GA014s gateway."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "GA014sOptionsFlow":
        """Return the options flow handler."""
        return GA014sOptionsFlow()

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        _errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._test_connection(user_input[CONF_HOST])
            except GA014sApiError:
                _errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"GA014s {user_input[CONF_HOST]}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
            }),
            errors=_errors,
        )

    async def _test_connection(self, host: str) -> None:
        """Test connection to the gateway."""
        client = GA014sApiClient(host=host, session=async_create_clientsession(self.hass))
        await client.get_gateway_info()


class GA014sOptionsFlow(config_entries.OptionsFlow):
    """Options flow: configure which months count as winter (heat season)."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_WINTER_MONTHS, DEFAULT_WINTER_MONTHS
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_WINTER_MONTHS,
                    default=[str(m) for m in current],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                        options=[
                            selector.SelectOptionDict(value=str(m), label=f"{m}月")
                            for m in range(1, 13)
                        ],
                    )
                ),
            }),
        )

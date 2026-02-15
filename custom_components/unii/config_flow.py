"""Config flow for Unii integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_SHARED_KEY, CONF_USER_CODE, DEFAULT_PORT
from .client import UniiClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=6502): int,
        vol.Optional(CONF_SHARED_KEY): str,
        vol.Optional(CONF_USER_CODE): str,
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Unii."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            key = user_input[CONF_SHARED_KEY]
            
            # Validate connection
            client = UniiClient(host, port, key)
            if await client.connect():
                await client.disconnect()
                return self.async_create_entry(title="Unii Alarm", data=user_input)
            else:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return UniiOptionsFlowHandler(config_entry)


class UniiOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Unii options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize headers."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
             # Update the entry's data (config) with the new options immediately
             # because we aren't using separate 'options' dict for core logic yet.
             # This effectively "edits" the config.
             new_data = self.config_entry.data.copy()
             new_data.update(user_input)
             
             self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
             return self.async_create_entry(title="", data={})

        current_code = self.config_entry.data.get(CONF_USER_CODE, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_USER_CODE, default=current_code): str,
                }
            ),
        )

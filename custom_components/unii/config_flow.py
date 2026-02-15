"""Config flow for Unii integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import DOMAIN, CONF_SHARED_KEY, CONF_USER_CODE, DEFAULT_PORT
from .client import UniiClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_SHARED_KEY): str,
        vol.Optional(CONF_USER_CODE): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Unii."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            key = user_input.get(CONF_SHARED_KEY)

            # Validate connection
            client = UniiClient(host, port, key)
            try:
                if await client.connect():
                    await client.disconnect()
                    return self.async_create_entry(title="Unii Alarm", data=user_input)
                else:
                    errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return UniiOptionsFlowHandler()


class UniiOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Unii options."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # Merge new options into entry data
            new_data = dict(self.config_entry.data)
            new_data.update(user_input)
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})

        # Get current stored code
        raw_code = self.config_entry.data.get(CONF_USER_CODE)
        current_code = str(raw_code) if raw_code is not None else ""
        # Get current shared key (from data or options)
        current_key = self.config_entry.options.get(CONF_SHARED_KEY, self.config_entry.data.get(CONF_SHARED_KEY))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_USER_CODE, default=current_code): str,
                    vol.Optional(CONF_SHARED_KEY, default=current_key): str,
                }
            ),
        )

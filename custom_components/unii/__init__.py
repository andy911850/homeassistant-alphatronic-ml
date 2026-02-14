#
# Copyright 2024 unii-security (Original)
# Copyright 2026 andy911850 (Modifications)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""The Unii integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, CONF_SHARED_KEY
from .client import UniiClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unii from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    shared_key = entry.data[CONF_SHARED_KEY]

    client = UniiClient(host, port, shared_key)
    
    async def async_update_data():
        """Fetch data from Unii."""
        try:
            if not await client.connect():
                raise UpdateFailed("Failed to connect to Unii panel")
            
            # Poll Sections and Inputs
            section_resp = await client.get_status()
            input_resp = await client.get_input_status()
            
            data = {"sections": {}, "inputs": {}}
            
            if section_resp and section_resp.get("command") == 0x0117:
                # Parse section data (each 2 bytes: ID, State)
                raw_data = section_resp["data"]
                for i in range(0, len(raw_data), 2):
                    s_id = raw_data[i]
                    s_state = raw_data[i+1]
                    data["sections"][s_id] = s_state
            
            if input_resp and input_resp.get("command") == 0x0105:
                # Parse input data (Version 2 response)
                # [Version (1)][Block (2)][Data...]
                raw_data = input_resp["data"]
                # According to py-unii, version is at [1], data starts at [2]
                # Each byte is an InputStatusRecord
                for i, status_byte in enumerate(raw_data[2:]):
                    input_id = i + 1 # simplistic mapping for now
                    data["inputs"][input_id] = {
                        "status": status_byte & 0x0F,
                        "bypassed": bool(status_byte & 0x10),
                        "low_battery": bool(status_byte & 0x40),
                    }
            
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="unii_status",
        update_method=async_update_data,
        update_interval=timedelta(seconds=5),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.update_method.__self__.__dict__['client'].disconnect() # Clean up

    return unload_ok

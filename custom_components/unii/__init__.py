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

VERSION = "1.5.8"
PLATFORMS: list[Platform] = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR, Platform.SWITCH]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unii from a config entry."""
    _LOGGER.warning(f"=== UNii Integration v{VERSION} starting ===")
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    shared_key = entry.data.get(CONF_SHARED_KEY)

    client = UniiClient(host, port, shared_key)
    poll_count = [0]  # Mutable counter for closure

    async def async_update_data():
        """Fetch data from Unii."""
        poll_count[0] += 1
        poll_num = poll_count[0]
        
        try:
            # Just ensure we're connected — don't force disconnect!
            # Force disconnect caused a race condition with arm/disarm commands
            if not await client.connect():
                await client.disconnect()
                raise UpdateFailed("Failed to connect to Unii panel")
            
            # Poll Section Status
            section_resp = await client.get_status()
            
            if not section_resp:
                _LOGGER.warning(f"Poll #{poll_num}: Section poll returned None")
                await client.disconnect()
                raise UpdateFailed("No section response from panel")
            
            data = {"sections": {}, "inputs": {}}
            
            if section_resp.get("command") == 0x0117:
                raw_data = section_resp["data"]
                offset = 1
                section_idx = 1
                while offset + 1 < len(raw_data):
                    s_state = raw_data[offset]
                    data["sections"][section_idx] = s_state
                    section_idx += 1
                    offset += 2
                
                if poll_num <= 5 or poll_num % 20 == 0:
                    _LOGGER.warning(f"Poll #{poll_num}: Sections={data['sections']}")
            else:
                _LOGGER.warning(f"Poll #{poll_num}: Unexpected response 0x{section_resp.get('command', 0):04x}")

            # Poll Input Status (best effort)
            try:
                input_resp = await client.get_input_status()
                if input_resp and input_resp.get("command") == 0x0105:
                    raw_data = input_resp["data"]
                    offset = 2
                    input_idx = 1
                    while offset + 1 < len(raw_data):
                        status_byte = raw_data[offset]
                        status = status_byte & 0x0F
                        data["inputs"][input_idx] = {
                            "status": status,
                            "bypassed": bool(status_byte & 0x10),
                            "low_battery": bool(status_byte & 0x40),
                            "name": f"Input {input_idx}",
                            "sensor_type": 0,
                        }
                        input_idx += 1
                        offset += 2
            except Exception as e:
                _LOGGER.debug(f"Poll #{poll_num}: Input poll failed (non-fatal): {e}")
            
            # Keep connection open for arm/disarm commands between polls
            
            return data
        except UpdateFailed:
            raise
        except Exception as err:
            await client.disconnect()
            raise UpdateFailed(f"Poll #{poll_num}: Error: {err}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="unii_status",
        update_method=async_update_data,
        update_interval=timedelta(seconds=5),
    )
    coordinator.client = client 
    coordinator.input_arrangement = {}

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    entry.async_on_unload(entry.add_update_listener(update_listener))
    
    _LOGGER.warning(f"=== UNii Integration v{VERSION} loaded successfully ===")

    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if hasattr(coordinator, 'client'):
            await coordinator.client.disconnect()

    return unload_ok

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

PLATFORMS: list[Platform] = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR, Platform.SWITCH]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unii from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    shared_key = entry.data[CONF_SHARED_KEY]

    client = UniiClient(host, port, shared_key)
    
    # Fetch Input Arrangement (Metadata) once
    input_arrangement = {}
    try:
        if await client.connect():
            resp = await client.get_input_arrangement(0)
            if resp:
                input_arrangement = resp.get("inputs", {})
    except Exception as e:
        _LOGGER.warning(f"Could not fetch input arrangement: {e}")

    async def async_update_data():
        """Fetch data from Unii."""
        try:
            if not await client.connect():
                raise UpdateFailed("Failed to connect to Unii panel")
            
            # Retry fetching arrangement if missing
            if not coordinator.input_arrangement:
                 _LOGGER.debug("Input arrangement missing, attempting to fetch...")
                 arr_res = await client.get_input_arrangement()
                 if arr_res:
                     coordinator.input_arrangement = arr_res.get("inputs", {})
                     _LOGGER.debug(f"Fetched arrangement for {len(coordinator.input_arrangement)} inputs.")
            
            # Poll Sections and Inputs
            section_resp = await client.get_status()
            input_resp = await client.get_input_status()
            
            data = {"sections": {}, "inputs": {}}
            
            if section_resp and section_resp.get("command") == 0x0117:
                raw_data = section_resp["data"]
                # ML Protocol detection: 
                # If raw_data looks like Version(1) + [Status(1) + Padding(1)]...
                # Iterate with stride 2, skipping version?
                # Raw: 01 02 ff 02 ff...
                # Skip version (index 0)
                offset = 1
                section_idx = 1
                while offset + 1 < len(raw_data):
                    s_state = raw_data[offset]
                    # padding = raw_data[offset+1] # usually 0xFF or 0x00
                    data["sections"][section_idx] = s_state
                    section_idx += 1
                    offset += 2
            
            if input_resp and input_resp.get("command") == 0x0105:
                raw_data = input_resp["data"]
                # ML Protocol: Header(2) + [Status(1) + Suffix(1)]...
                # Raw: 00 01 00 0f 00 0f...
                # Skip Header (index 0-1)
                offset = 2
                input_idx = 1
                
                while offset + 1 < len(raw_data):
                    status_byte = raw_data[offset]
                    # suffix = raw_data[offset+1] # usually 0x0F
                    
                    # Look up arrangement
                    info = coordinator.input_arrangement.get(input_idx)
                    
                    if info:
                         stype = info.get("sensor_type", 0)
                         # Filter Types 0, 8, 9 if needed?
                         # For now trusting arrangement exists check.
                         
                         status = status_byte & 0x0F
                         # Only filter if status is literally "Disabled" (0x0F)?
                         # If suffix is 0x0F, don't confuse it with status.
                         # But status 0x00 is Closed?
                         
                         data["inputs"][input_idx] = {
                            "status": status,
                            "bypassed": bool(status_byte & 0x10), # Guessing flags same
                            "low_battery": bool(status_byte & 0x40),
                            "name": info.get("name", f"Input {input_idx}"),
                            "sensor_type": stype,
                        }
                    
                    input_idx += 1
                    offset += 2
            
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
    coordinator.client = client 
    coordinator.input_arrangement = input_arrangement

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

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

import asyncio
import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, CONF_SHARED_KEY
from .client import UniiClient

_LOGGER = logging.getLogger(__name__)

VERSION = "1.5.19"
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
    
    # Shared lock: prevents poll from disconnecting during arm/disarm
    operation_lock = asyncio.Lock()

    # Download input arrangement (zone names) once at startup
    # Uses a separate connection that is cleanly closed after download
    input_arrangement = {}
    try:
        _LOGGER.warning("Downloading input arrangement (zone names)...")
        if await client.connect():
            arr_data = await client.get_input_arrangement()
            if arr_data and "inputs" in arr_data:
                input_arrangement = arr_data["inputs"]
                _LOGGER.warning(f"Input arrangement: {len(input_arrangement)} zones loaded")
                for inp_id, inp_data in input_arrangement.items():
                    _LOGGER.info(f"  Zone {inp_id}: {inp_data.get('name', '?')}")
            else:
                _LOGGER.warning("No input arrangement data received")
            await client.disconnect()
        else:
            _LOGGER.warning("Could not connect for arrangement download")
    except Exception as e:
        _LOGGER.warning(f"Arrangement download failed (non-fatal): {e}")
        await client.disconnect()

    async def async_update_data():
        """Fetch data from Unii."""
        poll_count[0] += 1
        poll_num = poll_count[0]
        
        async with operation_lock:
            try:
                # Force fresh connection — panel returns stale data on persistent connections
                await client.disconnect()
                
                if not await client.connect():
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
                        _LOGGER.warning(f"Poll #{poll_num}: Sections={data['sections']} RAW_HEX={raw_data.hex()}")
                else:
                    _LOGGER.warning(f"Poll #{poll_num}: Unexpected response 0x{section_resp.get('command', 0):04x}")

                # Poll Input Status (best effort)
                # Only include inputs that have arrangement data (real zones)
                try:
                    input_resp = await client.get_input_status()
                    if input_resp and input_resp.get("command") == 0x0105:
                        raw_data = input_resp["data"]
                        
                        # Log raw input data every 5 polls to debug state changes
                        if poll_num <= 5 or poll_num % 10 == 0:
                            _LOGGER.debug(f"Poll #{poll_num}: Inputs RAW_HEX={raw_data.hex()}")

                        offset = 2
                        input_idx = 1
                        while offset + 1 < len(raw_data):
                            # Logs show status is in the second byte (00 01 = Open, 00 00 = Closed)
                            status_byte = raw_data[offset+1]
                            status = status_byte & 0x0F
                            
                            # Only include inputs with arrangement data (skip VRIJE TEKST etc.)
                            arr_info = input_arrangement.get(input_idx)
                            if arr_info:
                                name = arr_info.get("name", f"Input {input_idx}")
                                is_open = (status & 0x01) == 0x01
                                
                                # Log state for first few inputs to check bitmask
                                if input_idx <= 3 and (poll_num <= 5 or poll_num % 10 == 0):
                                     _LOGGER.debug(f"  Input {input_idx} ({name}): StatusByte={status_byte:02x} State={status} Open={is_open}")

                                data["inputs"][input_idx] = {
                                    "status": status,
                                    "bypassed": bool(status_byte & 0x10),
                                    "low_battery": bool(status_byte & 0x40),
                                    "name": name,
                                    "sensor_type": arr_info.get("sensor_type", 0),
                                }
                            input_idx += 1
                            offset += 2
                except Exception as e:
                    _LOGGER.debug(f"Poll #{poll_num}: Input poll failed (non-fatal): {e}")
                
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
    coordinator.input_arrangement = input_arrangement
    coordinator.operation_lock = operation_lock  # Share lock with entities

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

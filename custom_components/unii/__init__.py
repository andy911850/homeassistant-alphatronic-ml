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

VERSION = "1.6.4"
PLATFORMS: list[Platform] = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR, Platform.SWITCH]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unii from a config entry."""
    _LOGGER.info(f"=== UNii Integration v{VERSION} starting ===")
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    # Check Shared Key Override in Options
    shared_key = entry.options.get(CONF_SHARED_KEY, entry.data.get(CONF_SHARED_KEY))

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
                # 1. Maintain Connection
                if not client._connected or not client.writer:
                    _LOGGER.debug(f"Poll #{poll_num}: Connecting...")
                    if not await client.connect():
                        raise UpdateFailed("Failed to connect to Unii panel")

                # 2. Poll Sections
                section_resp = await client.get_status()
                if not section_resp:
                    _LOGGER.warning(f"Poll #{poll_num}: Section poll failed. Reconnecting next time.")
                    await client.disconnect()
                    raise UpdateFailed("No section response")

                # 3. Poll Inputs
                input_resp = await client.get_input_status()
                # Note: We continue even if input poll fails, to at least return section data?
                # No, standard behavior is strict. If input poll fails, we might have partial state.
                # Let's be strict for now.
                if not input_resp:
                     _LOGGER.warning(f"Poll #{poll_num}: Input poll failed.")
                     raise UpdateFailed("No input response")

                data = {"sections": {}, "inputs": {}}

                # 4. Parse Sections
                if section_resp.get("command") == 0x0117:
                    raw_data = section_resp["data"]
                    offset = 1
                    section_idx = 1
                    while offset + 1 < len(raw_data):
                        data["sections"][section_idx] = raw_data[offset]
                        section_idx += 1
                        offset += 2
                
                # 5. Parse Inputs
                # Command 0x0105: Version(1)|Reserved(1)|[Byte1(Stat)][Byte2(Reserved?)]...
                if input_resp.get("command") == 0x0105:
                    raw_data = input_resp["data"]
                    offset = 2
                    
                    # Iterate over known inputs from arrangement
                    # This is O(N) where N is number of inputs.
                    # Flattened arrangement loop is safer than while loop on raw_data 
                    # because we can enforce input_idx alignment.
                    
                    # However, raw_data is linear.
                    # Input 1 is always at offset 2. Input 2 at offset 4.
                    
                    for input_idx, arr_info in input_arrangement.items():
                        byte_pos = 2 + (input_idx - 1) * 2
                        
                        if byte_pos + 1 >= len(raw_data):
                            break
                            
                        # Status is at byte_pos + 1
                        status_byte = raw_data[byte_pos + 1]
                        
                        # Bit 0 = State (Open/Closed)? No, usually lower nibble.
                        # Based on observation: 00=Closed, 01=Open? 
                        # Let's trust the byte value for "status" attribute.
                        
                        data["inputs"][input_idx] = {
                            "status": status_byte & 0x0F, # Lower nibble as state
                            "bypassed": bool(status_byte & 0x10), # Bit 4
                            "low_battery": bool(status_byte & 0x40), # Bit 6 (Guess)
                            "name": arr_info["name"],
                            "sensor_type": arr_info.get("sensor_type", 0)
                        }

                return data

            except UpdateFailed:
                raise
            except Exception as err:
                _LOGGER.error(f"Poll #{poll_num} error: {err}")
                await client.disconnect()
                raise UpdateFailed(f"Poll error: {err}")

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
    
    _LOGGER.info(f"=== UNii Integration v{VERSION} loaded successfully ===")

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

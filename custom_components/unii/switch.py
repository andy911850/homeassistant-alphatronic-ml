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
"""Switch platform for Unii alarm system bypassing."""
import logging
import asyncio
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Unii switch platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    await coordinator.async_config_entry_first_refresh()
    
    entities = []
    if coordinator.data and "inputs" in coordinator.data:
        for input_id, record in coordinator.data["inputs"].items():
            # Allow bypassing ALL sensor types (including Type 0)
            # stype = record.get("sensor_type")
            # if stype in [1, 15]: 
            entities.append(UniiBypassSwitch(coordinator, input_id))
            
    async_add_entities(entities)

class UniiBypassSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to bypass/unbypass a Unii input."""

    def __init__(self, coordinator, input_id):
        super().__init__(coordinator)
        self._input_id = input_id
        record = coordinator.data.get("inputs", {}).get(input_id, {})
        name = record.get("name", f"Input {input_id}")
        self._attr_name = f"{name} Bypass"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_input_{input_id}_bypass"
        self._attr_icon = "mdi:shield-off"

    @property
    def is_on(self) -> bool:
        """Return true if the input is bypassed."""
        if not self.coordinator.data or "inputs" not in self.coordinator.data:
            return False
        status_record = self.coordinator.data["inputs"].get(self._input_id)
        if not status_record:
            return False
        return status_record.get("bypassed", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Bypass the input."""
        # Check data first (primary storage per config_flow.py)
        code = self.coordinator.config_entry.data.get("user_code")
        if not code:
            code = self.coordinator.config_entry.options.get("user_code")
            
        if not code:
            _LOGGER.warning("No user code configured. Falling back to default '1234'.")
            code = "1234"

        client = self.coordinator.client
        
        # Use shared lock to prevent collision with poll
        async with self.coordinator.operation_lock:
            try:
                if not await client.connect():
                    _LOGGER.error("Could not connect to panel for bypass command")
                    return
                
                resp = await client.bypass_input(self._input_id, code)
                if resp and len(resp) >= 3:
                    result = resp[2]
                    if result == 1:
                        _LOGGER.info(f"Bypass Input {self._input_id} Success")
                    elif result == 2:
                        _LOGGER.error(f"Bypass Input {self._input_id} Failed: Authentication Failed (Check User Code)")
                        return
                    elif result == 3:
                        _LOGGER.error(f"Bypass Input {self._input_id} Failed: Not Allowed")
                        return
                    else:
                        _LOGGER.error(f"Bypass Input {self._input_id} Failed: Result Code {result}")
                        return
                else:
                    _LOGGER.error(f"Bypass Input {self._input_id} Failed: No response or invalid data")
                    return
            except Exception as e:
                _LOGGER.error(f"Failed to bypass input {self._input_id}: {e}")

        # Optimistic Update
        # We assume success means it IS bypassed.
        if self.coordinator.data and "inputs" in self.coordinator.data:
             if self._input_id in self.coordinator.data["inputs"]:
                 self.coordinator.data["inputs"][self._input_id]["bypassed"] = True
                 self.async_write_ha_state()

        # Schedule a refresh to confirm (no delay needed if optimistic)
        self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unbypass the input."""
        # Check data first (primary storage per config_flow.py)
        code = self.coordinator.config_entry.data.get("user_code")
        if not code:
            code = self.coordinator.config_entry.options.get("user_code")
            
        if not code:
            _LOGGER.warning("No user code configured. Falling back to default '1234'.")
            code = "1234"

        client = self.coordinator.client
        
        async with self.coordinator.operation_lock:
            try:
                if not await client.connect():
                    _LOGGER.error("Could not connect to panel for unbypass command")
                    return
                
                resp = await client.unbypass_input(self._input_id, code)
                if resp and len(resp) >= 3:
                    result = resp[2]
                    if result == 1:
                        _LOGGER.info(f"Unbypass Input {self._input_id} Success")
                    elif result == 2:
                        _LOGGER.error(f"Unbypass Input {self._input_id} Failed: Authentication Failed (Check User Code)")
                        return
                    elif result == 3:
                        _LOGGER.error(f"Unbypass Input {self._input_id} Failed: Not Allowed")
                        return
                    else:
                        _LOGGER.error(f"Unbypass Input {self._input_id} Failed: Result Code {result}")
                        return
                else:
                    _LOGGER.error(f"Unbypass Input {self._input_id} Failed: No response or invalid data")
                    return
            except Exception as e:
                _LOGGER.error(f"Failed to unbypass input {self._input_id}: {e}")

        # Optimistic Update
        if self.coordinator.data and "inputs" in self.coordinator.data:
             if self._input_id in self.coordinator.data["inputs"]:
                 self.coordinator.data["inputs"][self._input_id]["bypassed"] = False
                 self.async_write_ha_state()

        self.coordinator.async_request_refresh()

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
            # Only create bypass switches for Burglary (1) or Glassbreak (15)
            stype = record.get("sensor_type")
            if stype in [1, 15]: 
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
        # Use a "dummy" or stored code for bypass if not provided?
        # For now, we'll try to use a common code if available in config, 
        # or we might need the user to provide it via service.
        # UNii typically needs a valid user code.
        # We'll see if the user provides feedback on where to get the code.
        _LOGGER.warning("Bypass requires a user code. Attempting with default if available.")
        # Placeholder for code retrieval
        code = "1234" # Should be configurable
        client = self.coordinator.client
        await client.bypass_input(self._input_id, code)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unbypass the input."""
        code = "1234" # Should be configurable
        client = self.coordinator.client
        await client.unbypass_input(self._input_id, code)
        await self.coordinator.async_request_refresh()

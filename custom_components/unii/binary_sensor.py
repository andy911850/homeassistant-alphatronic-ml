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
"""Binary sensor platform for Unii alarm system inputs."""
import logging
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import EntityCategory

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Unii binary sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    await coordinator.async_config_entry_first_refresh()
    
    entities = []
    if coordinator.data and "inputs" in coordinator.data:
        for input_id, record in coordinator.data["inputs"].items():
            entities.append(UniiInputBinarySensor(coordinator, input_id))
            entities.append(UniiTamperBinarySensor(coordinator, input_id))
            
    async_add_entities(entities)

class UniiInputBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for Unii inputs (Zones)."""

    def __init__(self, coordinator, input_id):
        super().__init__(coordinator)
        self._input_id = input_id
        # Get name from current data or arrangement
        record = coordinator.data.get("inputs", {}).get(input_id, {})
        name = record.get("name", f"Input {input_id}")
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_input_{input_id}"
        self._attr_device_class = BinarySensorDeviceClass.MOTION
        
    @property
    def is_on(self):
        """Return true if the input is open/active."""
        if not self.coordinator.data or "inputs" not in self.coordinator.data:
            return False
        status_record = self.coordinator.data["inputs"].get(self._input_id)
        if not status_record:
            return False
        # Check ANY non-zero status in lower nibble (Alarm, Tamper, Mask, Trouble)
        return (status_record["status"] & 0x0F) > 0

    @property
    def extra_state_attributes(self):
        """Return input attributes."""
        if not self.coordinator.data or "inputs" not in self.coordinator.data:
            return {}
        status_record = self.coordinator.data["inputs"].get(self._input_id)
        if not status_record:
            return {}
        return {
            "bypassed": status_record.get("bypassed", False),
            "tamper": (status_record["status"] & 0x02) == 0x02,
            "masking": (status_record["status"] & 0x04) == 0x04,
            "low_battery": status_record.get("low_battery", False),
        }

class UniiTamperBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for Unii input tamper status."""

    def __init__(self, coordinator, input_id):
        super().__init__(coordinator)
        self._input_id = input_id
        record = coordinator.data.get("inputs", {}).get(input_id, {})
        name = record.get("name", f"Input {input_id}")
        self._attr_name = f"{name} Tamper"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_input_{input_id}_tamper"
        self._attr_device_class = BinarySensorDeviceClass.TAMPER
    @property
    def entity_category(self):
        """Return the category of the entity."""
        return EntityCategory.DIAGNOSTIC

    @property
    def is_on(self):
        """Return true if the input is in tamper."""
        if not self.coordinator.data or "inputs" not in self.coordinator.data:
            return False
        status_record = self.coordinator.data["inputs"].get(self._input_id)
        if not status_record:
            return False
        return (status_record["status"] & 0x02) == 0x02

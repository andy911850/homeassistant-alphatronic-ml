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
"""Support for Unii alarm control panels."""
from __future__ import annotations

import logging
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unii alarm control panel from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    sections = [
        UniiAlarm(coordinator, 1, "Section 1"),
        UniiAlarm(coordinator, 2, "Section 2"),
        UniiMasterAlarm(coordinator, [1, 2], "Master"),
    ]
    
    async_add_entities(sections)


class UniiAlarm(CoordinatorEntity, AlarmControlPanelEntity):
    """Representation of a Unii section alarm."""

    _attr_code_format = CodeFormat.NUMBER
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
    )

    def __init__(self, coordinator, section_id: int, name_suffix: str) -> None:
        """Initialize the alarm."""
        super().__init__(coordinator)
        self.section_id = section_id
        self._attr_name = f"{coordinator.config_entry.title} {name_suffix}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_section_{section_id}"

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the state of the device."""
        if not self.coordinator.data or "sections" not in self.coordinator.data:
            return None
            
        sec_state = self.coordinator.data["sections"].get(self.section_id)
        if sec_state is None:
            return None
            
        # Mapping based on UNiiSectionArmedState
        if sec_state == 1: # ARMED
            return AlarmControlPanelState.ARMED_AWAY
        if sec_state == 2: # DISARMED
            return AlarmControlPanelState.DISARMED
        if sec_state == 7: # ALARM
            return AlarmControlPanelState.TRIGGERED
        if sec_state == 8: # EXIT_TIMER
            return AlarmControlPanelState.ARMING
        if sec_state == 9: # ENTRY_TIMER
            return AlarmControlPanelState.PENDING
            
        return AlarmControlPanelState.DISARMED

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command for this section."""
        if not code:
            return
        client = self.coordinator.client
        await client.disarm_section(self.section_id, code)
        await self.coordinator.async_request_refresh()


    async def async_alarm_disarm(self, code=None) -> None:
        """Send disarm command."""
        # Fallback to stored code
        use_code = code if code else self._user_code
        
        if not use_code:
            _LOGGER.error("No code provided for disarm.")
            return

        if self.is_master:
            # Disarm all known sections
            sections = self.coordinator.data.get("sections", {})
            for s_id in sections.keys():
                await self.coordinator.client.disarm_section(s_id, use_code)
        else:
            await self.coordinator.client.disarm_section(self.index, use_code)

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        # Fallback to stored code
        use_code = code if code else self._user_code
        
        if not use_code:
            _LOGGER.error("No code provided for arm.")
            return

        if self.is_master:
             sections = self.coordinator.data.get("sections", {})
             for s_id in sections.keys():
                await self.coordinator.client.arm_section(s_id, use_code)
        else:
            await self.coordinator.client.arm_section(self.index, use_code)

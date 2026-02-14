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
        client = self.coordinator.update_method.__self__.__dict__['client']
        await client.disarm_section(self.section_id, code)
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command for this section."""
        if not code:
            return
        client = self.coordinator.update_method.__self__.__dict__['client']
        await client.arm_section(self.section_id, code)
        await self.coordinator.async_request_refresh()


class UniiMasterAlarm(CoordinatorEntity, AlarmControlPanelEntity):
    """Representation of a Unii master alarm controlling all sections."""

    _attr_code_format = CodeFormat.NUMBER
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
    )

    def __init__(self, coordinator, section_ids: list[int], name_suffix: str) -> None:
        """Initialize the master alarm."""
        super().__init__(coordinator)
        self.section_ids = section_ids
        self._attr_name = f"{coordinator.config_entry.title} {name_suffix}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_master"

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the composite state of the system."""
        if not self.coordinator.data or "sections" not in self.coordinator.data:
            return None
            
        states = [self.coordinator.data["sections"].get(sid) for sid in self.section_ids]
        states = [s for s in states if s is not None]
        
        if not states:
            return None

        if 7 in states: # ALARM
            return AlarmControlPanelState.TRIGGERED
        if 9 in states: # ENTRY_TIMER
            return AlarmControlPanelState.PENDING
        if 8 in states: # EXIT_TIMER
            return AlarmControlPanelState.ARMING
        if all(s == 1 for s in states): # ARMED
            return AlarmControlPanelState.ARMED_AWAY
        
        return AlarmControlPanelState.DISARMED

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command to all sections."""
        client = self.coordinator.update_method.__self__.__dict__['client']
        for sid in self.section_ids:
            await client.disarm_section(sid, code)
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command to all sections."""
        client = self.coordinator.update_method.__self__.__dict__['client']
        for sid in self.section_ids:
            await client.arm_section(sid, code)
        await self.coordinator.async_request_refresh()


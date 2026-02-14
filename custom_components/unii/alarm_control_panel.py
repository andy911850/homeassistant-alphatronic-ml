"""Support for Unii alarm control panels."""
from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .client import UniiClient

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unii alarm control panel from a config entry."""
    client = hass.data[DOMAIN][entry.entry_id]
    
    # We create Section 1, Section 2, and a Master control
    sections = [
        UniiAlarm(client, entry, 1, "Section 1"),
        UniiAlarm(client, entry, 2, "Section 2"),
        UniiMasterAlarm(client, entry, [1, 2], "Master"),
    ]
    
    async_add_entities(sections, True)


class UniiAlarm(AlarmControlPanelEntity):
    """Representation of a Unii section alarm."""

    _attr_code_format = CodeFormat.NUMBER
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
    )

    def __init__(self, client: UniiClient, entry: ConfigEntry, section_id: int, name_suffix: str) -> None:
        """Initialize the alarm."""
        self.client = client
        self.section_id = section_id
        self._attr_name = f"{entry.title} {name_suffix}"
        self._attr_unique_id = f"{entry.entry_id}_section_{section_id}"
        self._state = None

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the state of the device."""
        return self._state

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command for this section."""
        if not code:
            _LOGGER.error("No code provided for disarm")
            return
            
        self._state = AlarmControlPanelState.DISARMING
        self.async_write_ha_state()
        
        resp = await self.client.disarm_section(self.section_id, code)
        if resp and resp['command'] == 0x0115:
            self._state = AlarmControlPanelState.DISARMED
        else:
             _LOGGER.error(f"Disarm command failed for Section {self.section_id}")

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command for this section."""
        if not code:
            _LOGGER.error("No code provided for arm")
            return

        self._state = AlarmControlPanelState.ARMING
        self.async_write_ha_state()

        resp = await self.client.arm_section(self.section_id, code)
        if resp and resp['command'] == 0x0113:
             self._state = AlarmControlPanelState.ARMED_AWAY
        else:
             _LOGGER.error(f"Arm command failed for Section {self.section_id}")

    async def async_update(self) -> None:
        """Fetch new state data for this alarm."""
        if not self.client._connected:
            if not await self.client.connect():
                self._state = STATE_UNAVAILABLE
                return

        try:
            resp = await self.client.get_status()
            if resp and resp['command'] == 0x0117:
                data = resp['data']
                for i in range(0, len(data), 2):
                    if i+1 >= len(data): break
                    sec_num = data[i]
                    sec_state = data[i+1]
                    
                    if sec_num == self.section_id:
                        if sec_state == 1:
                            self._state = AlarmControlPanelState.ARMED_AWAY
                        elif sec_state == 2:
                            self._state = AlarmControlPanelState.DISARMED
                        elif sec_state == 7:
                             self._state = AlarmControlPanelState.TRIGGERED
                        elif sec_state == 8:
                             self._state = AlarmControlPanelState.ARMING
                        elif sec_state == 9:
                             self._state = AlarmControlPanelState.PENDING
                        else:
                             self._state = AlarmControlPanelState.DISARMED
                        break
        except Exception as e:
            _LOGGER.error(f"Update failed for Section {self.section_id}: {e}")
            self._state = STATE_UNAVAILABLE


class UniiMasterAlarm(AlarmControlPanelEntity):
    """Representation of a Unii master alarm controlling all sections."""

    _attr_code_format = CodeFormat.NUMBER
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
    )

    def __init__(self, client: UniiClient, entry: ConfigEntry, section_ids: list[int], name_suffix: str) -> None:
        """Initialize the master alarm."""
        self.client = client
        self.section_ids = section_ids
        self._attr_name = f"{entry.title} {name_suffix}"
        self._attr_unique_id = f"{entry.entry_id}_master"
        self._state = None

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the composite state of the system."""
        return self._state

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command to all sections."""
        self._state = AlarmControlPanelState.DISARMING
        self.async_write_ha_state()
        
        success = True
        for sid in self.section_ids:
            resp = await self.client.disarm_section(sid, code)
            if not resp or resp['command'] != 0x0115:
                success = False
        
        if success:
            self._state = AlarmControlPanelState.DISARMED

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command to all sections."""
        self._state = AlarmControlPanelState.ARMING
        self.async_write_ha_state()

        success = True
        for sid in self.section_ids:
            resp = await self.client.arm_section(sid, code)
            if not resp or resp['command'] != 0x0113:
                success = False
        
        if success:
            self._state = AlarmControlPanelState.ARMED_AWAY

    async def async_update(self) -> None:
        """Calculate composite state from all sections."""
        if not self.client._connected:
            if not await self.client.connect():
                self._state = STATE_UNAVAILABLE
                return

        try:
            resp = await self.client.get_status()
            if resp and resp['command'] == 0x0117:
                data = resp['data']
                section_states = {}
                
                for i in range(0, len(data), 2):
                    if i+1 >= len(data): break
                    sec_num = data[i]
                    sec_state = data[i+1]
                    if sec_num in self.section_ids:
                        section_states[sec_num] = sec_state
                
                # Composite State Logic
                if any(s == 7 for s in section_states.values()):
                    self._state = AlarmControlPanelState.TRIGGERED
                elif any(s == 9 for s in section_states.values()):
                    self._state = AlarmControlPanelState.PENDING
                elif any(s == 8 for s in section_states.values()):
                    self._state = AlarmControlPanelState.ARMING
                elif all(s == 1 for s in section_states.values()):
                    self._state = AlarmControlPanelState.ARMED_AWAY
                elif all(s == 2 for s in section_states.values()):
                    self._state = AlarmControlPanelState.DISARMED
                else:
                    self._state = AlarmControlPanelState.DISARMED # Mixed/Default
        except Exception:
            self._state = STATE_UNAVAILABLE


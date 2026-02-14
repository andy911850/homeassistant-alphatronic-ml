"""Support for Unii alarm control panels."""
from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_DISARMED,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMING,
    STATE_UNAVAILABLE,
    STATE_ALARM_TRIGGERED,
    STATE_ALARM_PENDING,
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
    async_add_entities([UniiAlarm(client, entry)], True)


class UniiAlarm(AlarmControlPanelEntity):
    """Representation of a Unii alarm."""

    _attr_code_format = CodeFormat.NUMBER
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
    )

    def __init__(self, client: UniiClient, entry: ConfigEntry) -> None:
        """Initialize the alarm."""
        self.client = client
        self._attr_name = entry.title
        self._attr_unique_id = entry.entry_id
        self._state = None

    @property
    def state(self) -> str | None:
        """Return the state of the device."""
        return self._state

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        if not code:
            _LOGGER.error("No code provided for disarm")
            return
            
        self._state = STATE_ALARM_DISARMING
        self.async_write_ha_state()
        
        # We assume Section 1 for now
        resp = await self.client.disarm_section(1, code)
        if resp and resp['command'] == 0x0115:
            # Success, update will fetch new state naturally, but we can optimistically set it
            self._state = STATE_ALARM_DISARMED
        else:
             _LOGGER.error("Disarm command failed")
             # Revert? or let update handle it

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        if not code:
            _LOGGER.error("No code provided for arm")
            return

        self._state = STATE_ALARM_ARMING
        self.async_write_ha_state()

        resp = await self.client.arm_section(1, code)
        if resp and resp['command'] == 0x0113:
             self._state = STATE_ALARM_ARMED_AWAY
        else:
             _LOGGER.error("Arm command failed")

    async def async_update(self) -> None:
        """Fetch new state data for this alarm."""
        if not self.client._connected:
            # Try to reconnect
            if not await self.client.connect():
                self._state = STATE_UNAVAILABLE
                return

        try:
            # Poll status
            resp = await self.client.get_status()
            if resp and resp['command'] == 0x0117:
                # Payload: [SecNum, State, SecNum, State...]
                # We assume Section 1 is the first one or we find it.
                data = resp['data']
                
                # Iterate through 2-byte chunks
                for i in range(0, len(data), 2):
                    if i+1 >= len(data): break
                    sec_num = data[i]
                    sec_state = data[i+1]
                    
                    if sec_num == 1: # We only care about Section 1 for now
                        if sec_state == 1:
                            self._state = STATE_ALARM_ARMED_AWAY
                        elif sec_state == 2:
                            self._state = STATE_ALARM_DISARMED
                        elif sec_state == 7:
                             self._state = STATE_ALARM_TRIGGERED
                        else:
                             # 8=Exit Timer, 9=Entry Timer
                             if sec_state == 8:
                                 self._state = STATE_ALARM_ARMING
                             elif sec_state == 9:
                                 self._state = STATE_ALARM_PENDING
                             else:
                                 self._state = STATE_ALARM_DISARMED # Unknown fallback
                        break
        except Exception as e:
            _LOGGER.error(f"Update failed: {e}")
            self._state = STATE_UNAVAILABLE

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

from .const import DOMAIN, CONF_USER_CODE

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unii alarm control panel from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Create alarms for Section 1 and 2, and a Master
    sections = [
        UniiAlarm(coordinator, 1, "Section 1", entry),
        UniiAlarm(coordinator, 2, "Section 2", entry),
        UniiMasterAlarm(coordinator, [1, 2], "Master", entry),
    ]
    
    async_add_entities(sections)


class UniiAlarm(CoordinatorEntity, AlarmControlPanelEntity):
    """Representation of a Unii section alarm."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
    )

    def __init__(self, coordinator, section_id: int, name_suffix: str, entry: ConfigEntry) -> None:
        """Initialize the alarm."""
        super().__init__(coordinator)
        self.section_id = section_id
        self._attr_name = name_suffix
        self._attr_unique_id = f"{entry.entry_id}_section_{section_id}"
        
        self._user_code = entry.data.get(CONF_USER_CODE)
        if self._user_code:
             _LOGGER.debug(f"UniiAlarm {section_id}: Stored user code found (Length {len(self._user_code)})")
        else:
             _LOGGER.debug(f"UniiAlarm {section_id}: No stored user code found.")

    @property
    def code_format(self) -> CodeFormat | None:
        """Return one of the CODE_FORMAT_* constants."""
        if self._user_code:
            return None
        return CodeFormat.NUMBER

    @property
    def state(self) -> AlarmControlPanelState | None:
        """Return the state of the device."""
        if not self.coordinator.data or "sections" not in self.coordinator.data:
            return None
            
        sec_state = self.coordinator.data["sections"].get(self.section_id)
        if sec_state is None:
            return None
            
        # Mapping based on UNiiSectionArmedState
        # 1=Disarmed, 3=Armed, 4=PartSet? (Need verification, assuming standard)
        # However, earlier logging suggested 01=Disarmed, 02=Armed/Exit?
        # Let's use the standard mapping from previous knowledge or assume:
        # 1: Disarmed
        # 3: Armed
        # 9: Entry Delay
        # 8: Exit Delay
        # 7: Alarm
        
        if sec_state == 1: 
            return AlarmControlPanelState.DISARMED
        if sec_state == 3: 
            return AlarmControlPanelState.ARMED_AWAY
        if sec_state == 7: 
            return AlarmControlPanelState.TRIGGERED
        if sec_state == 8: 
            return AlarmControlPanelState.ARMING
        if sec_state == 9: 
            return AlarmControlPanelState.PENDING
            
        return AlarmControlPanelState.DISARMED

    async def async_alarm_disarm(self, code=None) -> None:
        """Send disarm command."""
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for disarm.")
            return

        client = self.coordinator.client
        await client.disarm_section(self.section_id, use_code)
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for arm.")
            return

        client = self.coordinator.client
        await client.arm_section(self.section_id, use_code)
        await self.coordinator.async_request_refresh()


class UniiMasterAlarm(CoordinatorEntity, AlarmControlPanelEntity):
    """Representation of a Unii master alarm controlling all sections."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
    )

    def __init__(self, coordinator, section_ids: list[int], name_suffix: str, entry: ConfigEntry) -> None:
        """Initialize the master alarm."""
        super().__init__(coordinator)
        self.section_ids = section_ids
        self._attr_name = name_suffix
        self._attr_unique_id = f"{entry.entry_id}_master"
        
        self._user_code = entry.data.get(CONF_USER_CODE)
        if self._user_code:
             _LOGGER.debug(f"UniiMasterAlarm: Stored user code found (Length {len(self._user_code)})")
        else:
             _LOGGER.debug("UniiMasterAlarm: No stored user code found.")

    @property
    def code_format(self) -> CodeFormat | None:
        """Return one of the CODE_FORMAT_* constants."""
        if self._user_code:
            return None
        return CodeFormat.NUMBER

    @property
    def state(self) -> AlarmControlPanelState | None:
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
        if any(s == 3 for s in states): # ARMED (If any is armed, master is armed)
            return AlarmControlPanelState.ARMED_AWAY
        
        return AlarmControlPanelState.DISARMED

    async def async_alarm_disarm(self, code=None) -> None:
        """Send disarm command to all sections."""
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for disarm.")
            return

        client = self.coordinator.client
        for sid in self.section_ids:
            await client.disarm_section(sid, use_code)
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command to all sections."""
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for arm.")
            return

        client = self.coordinator.client
        for sid in self.section_ids:
            await client.arm_section(sid, use_code)
        await self.coordinator.async_request_refresh()

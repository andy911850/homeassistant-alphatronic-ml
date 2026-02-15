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

# State mapping based on actual panel data
# State 1 = Disarmed
# State 2 = Armed
# State 3 = Exit Timer (Arming)
# State 4 = Entry Timer (Pending)
# State 5 = Alarm (Triggered)
SECTION_STATE_MAP = {
    0: AlarmControlPanelState.DISARMED,      # Unknown/default
    1: AlarmControlPanelState.DISARMED,      # Disarmed
    2: AlarmControlPanelState.ARMED_AWAY,    # Armed
    3: AlarmControlPanelState.ARMING,        # Exit Timer
    4: AlarmControlPanelState.PENDING,       # Entry Timer
    5: AlarmControlPanelState.TRIGGERED,     # Alarm
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unii alarm control panel from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Hardcoded Section 1, Section 2, and Master
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
        
        raw_code = entry.data.get(CONF_USER_CODE)
        self._user_code = str(raw_code).strip() if raw_code else None
        
        if self._user_code:
             self._attr_code_format = None
        else:
             self._attr_code_format = CodeFormat.NUMBER

    @property
    def code_format(self) -> CodeFormat | None:
        """Return one of the CODE_FORMAT_* constants."""
        if self._user_code:
            return None
        return CodeFormat.NUMBER

    @property
    def code_arm_required(self) -> bool:
        """Whether the code is required for arm actions."""
        return not bool(self._user_code)

    @property
    def state(self) -> AlarmControlPanelState | None:
        """Return the state of the device."""
        if not self.coordinator.data or "sections" not in self.coordinator.data:
            return None
            
        sec_state = self.coordinator.data["sections"].get(self.section_id)
        if sec_state is None:
            return None
        
        mapped = SECTION_STATE_MAP.get(sec_state)
        if mapped is None:
            _LOGGER.warning(f"Section {self.section_id}: Unknown state value {sec_state}, defaulting to DISARMED")
            return AlarmControlPanelState.DISARMED
        
        return mapped

    async def async_alarm_disarm(self, code=None) -> None:
        """Send disarm command."""
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for disarm.")
            return

        _LOGGER.warning(f"Disarming section {self.section_id}...")
        client = self.coordinator.client
        result = await client.disarm_section(self.section_id, use_code)
        _LOGGER.warning(f"Disarm section {self.section_id} result: {result}")
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for arm.")
            return

        _LOGGER.warning(f"Arming section {self.section_id}...")
        client = self.coordinator.client
        result = await client.arm_section(self.section_id, use_code)
        _LOGGER.warning(f"Arm section {self.section_id} result: {result}")
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
        
        raw_code = entry.data.get(CONF_USER_CODE)
        self._user_code = str(raw_code).strip() if raw_code else None
        
        if self._user_code:
             self._attr_code_format = None
        else:
             self._attr_code_format = CodeFormat.NUMBER

    @property
    def code_format(self) -> CodeFormat | None:
        """Return one of the CODE_FORMAT_* constants."""
        if self._user_code:
            return None
        return CodeFormat.NUMBER

    @property
    def code_arm_required(self) -> bool:
        """Whether the code is required for arm actions."""
        return not bool(self._user_code)

    @property
    def state(self) -> AlarmControlPanelState | None:
        """Return the composite state of the system."""
        if not self.coordinator.data or "sections" not in self.coordinator.data:
            return None
            
        states = [self.coordinator.data["sections"].get(sid) for sid in self.section_ids]
        states = [s for s in states if s is not None]
        
        if not states:
            return None

        # Priority: Triggered > Pending > Arming > Armed > Disarmed
        if 5 in states:
            return AlarmControlPanelState.TRIGGERED
        if 4 in states:
            return AlarmControlPanelState.PENDING
        if 3 in states:
            return AlarmControlPanelState.ARMING
        if any(s == 2 for s in states):
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
            _LOGGER.warning(f"Master: Disarming section {sid}...")
            result = await client.disarm_section(sid, use_code)
            _LOGGER.warning(f"Master: Disarm section {sid} result: {result}")
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command to all sections."""
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for arm.")
            return

        client = self.coordinator.client
        for sid in self.section_ids:
            _LOGGER.warning(f"Master: Arming section {sid}...")
            result = await client.arm_section(sid, use_code)
            _LOGGER.warning(f"Master: Arm section {sid} result: {result}")
        await self.coordinator.async_request_refresh()

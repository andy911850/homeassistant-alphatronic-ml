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

# State mapping based on ACTUAL panel observation:
# When armed via keypad -> poll shows state 1
# When disarmed via keypad -> poll shows state 2
SECTION_STATE_MAP = {
    0: AlarmControlPanelState.DISARMED,      # Unknown/default
    1: AlarmControlPanelState.ARMED_AWAY,    # Armed (confirmed by user)
    2: AlarmControlPanelState.DISARMED,      # Disarmed (confirmed by user)
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
    
    # Log the actual state mapping to verify correct code is loaded
    _LOGGER.warning(f"STATE MAP: 1={SECTION_STATE_MAP[1]}, 2={SECTION_STATE_MAP[2]}")
    
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
        _LOGGER.warning(f">>> DISARM CALLED on entity {self._attr_unique_id} (section {self.section_id})")
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for disarm.")
            return

        # Acquire shared lock so poll can't disconnect during our command
        async with self.coordinator.operation_lock:
            _LOGGER.warning(f"Disarming section {self.section_id}...")
            client = self.coordinator.client
            # Ensure connected
            if not await client.connect():
                _LOGGER.error(f"Cannot disarm section {self.section_id}: not connected")
                return
            result = await client.disarm_section(self.section_id, use_code)
            _LOGGER.warning(f"Disarm section {self.section_id} result: {result}")
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        _LOGGER.warning(f">>> ARM CALLED on entity {self._attr_unique_id} (section {self.section_id})")
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for arm.")
            return

        # Acquire shared lock so poll can't disconnect during our command
        async with self.coordinator.operation_lock:
            _LOGGER.warning(f"Arming section {self.section_id}...")
            client = self.coordinator.client
            # Ensure connected
            if not await client.connect():
                _LOGGER.error(f"Cannot arm section {self.section_id}: not connected")
                return
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
        # Using actual panel values: 1=Armed, 2=Disarmed
        if 5 in states:
            return AlarmControlPanelState.TRIGGERED
        if 4 in states:
            return AlarmControlPanelState.PENDING
        if 3 in states:
            return AlarmControlPanelState.ARMING
        if any(s == 1 for s in states):
            return AlarmControlPanelState.ARMED_AWAY
        
        return AlarmControlPanelState.DISARMED

    async def async_alarm_disarm(self, code=None) -> None:
        """Send disarm command to all sections."""
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for disarm.")
            return

        # Acquire shared lock so poll can't disconnect during our commands
        async with self.coordinator.operation_lock:
            client = self.coordinator.client
            if not await client.connect():
                _LOGGER.error("Cannot disarm: not connected")
                return
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

        # Acquire shared lock so poll can't disconnect during our commands
        async with self.coordinator.operation_lock:
            client = self.coordinator.client
            if not await client.connect():
                _LOGGER.error("Cannot arm: not connected")
                return
            for sid in self.section_ids:
                _LOGGER.warning(f"Master: Arming section {sid}...")
                result = await client.arm_section(sid, use_code)
                _LOGGER.warning(f"Master: Arm section {sid} result: {result}")
        await self.coordinator.async_request_refresh()

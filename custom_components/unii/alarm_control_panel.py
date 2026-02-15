"""Support for Unii alarm control panels."""
from __future__ import annotations

import asyncio
import time
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
# Panel status poll value -> HA state
SECTION_STATE_MAP = {
    0: AlarmControlPanelState.DISARMED,
    1: AlarmControlPanelState.ARMED_AWAY,    # Armed
    2: AlarmControlPanelState.DISARMED,      # Disarmed
    3: AlarmControlPanelState.ARMING,        # Exit Timer
    4: AlarmControlPanelState.PENDING,       # Entry Timer
    5: AlarmControlPanelState.TRIGGERED,     # Alarm
}

# Optimistic state overrides — trust arm/disarm command results
# Format: {section_id: (state_value, timestamp)}
# Overrides are valid for 30 seconds
_state_overrides = {}
_OVERRIDE_TTL = 30  # seconds


def _set_override(section_id: int, state_value: int):
    """Set an optimistic state override for a section."""
    _state_overrides[section_id] = (state_value, time.time())
    _LOGGER.warning(f"Set optimistic override: section {section_id} = {state_value} ({SECTION_STATE_MAP.get(state_value)})")


def _get_effective_state(section_id: int, polled_value: int) -> int:
    """Get effective state, preferring fresh overrides over poll data."""
    if section_id in _state_overrides:
        override_value, override_time = _state_overrides[section_id]
        age = time.time() - override_time
        if age < _OVERRIDE_TTL:
            if override_value != polled_value:
                _LOGGER.debug(f"Section {section_id}: using override {override_value} (age={age:.0f}s) over polled {polled_value}")
            return override_value
        else:
            # Override expired, remove it
            del _state_overrides[section_id]
    return polled_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unii alarm control panel from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    _LOGGER.warning(f"STATE MAP: 1={SECTION_STATE_MAP[1]}, 2={SECTION_STATE_MAP[2]}")
    
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
        if self._user_code:
            return None
        return CodeFormat.NUMBER

    @property
    def code_arm_required(self) -> bool:
        return not bool(self._user_code)

    @property
    def state(self) -> AlarmControlPanelState | None:
        if not self.coordinator.data or "sections" not in self.coordinator.data:
            return None
            
        polled_state = self.coordinator.data["sections"].get(self.section_id)
        if polled_state is None:
            return None
        
        # Use optimistic override if available and fresh
        effective_state = _get_effective_state(self.section_id, polled_state)
        
        mapped = SECTION_STATE_MAP.get(effective_state)
        if mapped is None:
            _LOGGER.warning(f"Section {self.section_id}: Unknown state {effective_state}")
            return AlarmControlPanelState.DISARMED
        
        return mapped

    async def async_alarm_disarm(self, code=None) -> None:
        _LOGGER.warning(f">>> DISARM CALLED on entity {self._attr_unique_id} (section {self.section_id})")
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for disarm.")
            return

        async with self.coordinator.operation_lock:
            client = self.coordinator.client
            if not await client.connect():
                _LOGGER.error(f"Cannot disarm section {self.section_id}: not connected")
                return
            result = await client.disarm_section(self.section_id, use_code)
            _LOGGER.warning(f"Disarm section {self.section_id} result: {result}")
            
            # Check for success (result byte == 0x01)
            if result and result.get("data") and len(result["data"]) >= 2 and result["data"][1] == 0x01:
                _set_override(self.section_id, 2)  # 2 = disarmed
        
        # Force UI update
        self.async_write_ha_state()

    async def async_alarm_arm_away(self, code=None) -> None:
        _LOGGER.warning(f">>> ARM CALLED on entity {self._attr_unique_id} (section {self.section_id})")
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for arm.")
            return

        async with self.coordinator.operation_lock:
            client = self.coordinator.client
            if not await client.connect():
                _LOGGER.error(f"Cannot arm section {self.section_id}: not connected")
                return
            result = await client.arm_section(self.section_id, use_code)
            _LOGGER.warning(f"Arm section {self.section_id} result: {result}")
            
            # Check for success (result byte == 0x01)
            if result and result.get("data") and len(result["data"]) >= 2 and result["data"][1] == 0x01:
                _set_override(self.section_id, 1)  # 1 = armed
        
        # Force UI update
        self.async_write_ha_state()


class UniiMasterAlarm(CoordinatorEntity, AlarmControlPanelEntity):
    """Representation of a Unii master alarm controlling all sections."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
    )

    def __init__(self, coordinator, section_ids: list[int], name_suffix: str, entry: ConfigEntry) -> None:
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
        if self._user_code:
            return None
        return CodeFormat.NUMBER

    @property
    def code_arm_required(self) -> bool:
        return not bool(self._user_code)

    @property
    def state(self) -> AlarmControlPanelState | None:
        if not self.coordinator.data or "sections" not in self.coordinator.data:
            return None
            
        states = []
        for sid in self.section_ids:
            polled = self.coordinator.data["sections"].get(sid)
            if polled is not None:
                effective = _get_effective_state(sid, polled)
                states.append(effective)
        
        if not states:
            return None

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
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for disarm.")
            return

        async with self.coordinator.operation_lock:
            client = self.coordinator.client
            if not await client.connect():
                _LOGGER.error("Cannot disarm: not connected")
                return
            for sid in self.section_ids:
                _LOGGER.warning(f"Master: Disarming section {sid}...")
                result = await client.disarm_section(sid, use_code)
                _LOGGER.warning(f"Master: Disarm section {sid} result: {result}")
                if result and result.get("data") and len(result["data"]) >= 2 and result["data"][1] == 0x01:
                    _set_override(sid, 2)  # 2 = disarmed
        
        self.async_write_ha_state()

    async def async_alarm_arm_away(self, code=None) -> None:
        use_code = code if code else self._user_code
        if not use_code:
            _LOGGER.error("No code provided for arm.")
            return

        async with self.coordinator.operation_lock:
            client = self.coordinator.client
            if not await client.connect():
                _LOGGER.error("Cannot arm: not connected")
                return
            for sid in self.section_ids:
                _LOGGER.warning(f"Master: Arming section {sid}...")
                result = await client.arm_section(sid, use_code)
                _LOGGER.warning(f"Master: Arm section {sid} result: {result}")
                if result and result.get("data") and len(result["data"]) >= 2 and result["data"][1] == 0x01:
                    _set_override(sid, 1)  # 1 = armed
        
        self.async_write_ha_state()

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

if TYPE_CHECKING:
    from .coordinator import S7Coordinator

_LOGGER = logging.getLogger(__name__)


class S7BaseEntity(CoordinatorEntity):
    """Base entity for the S7 PLC integration."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: S7Coordinator,
        *,
        name: str | None = None,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str | None = None,
        address: str | None = None,
        suggested_area_id: str | None = None,
    ) -> None:
        """Initialize S7 base entity.

        Args:
            coordinator: S7 coordinator instance
            name: Optional entity name
            unique_id: Unique identifier for the entity
            device_info: Device information for entity grouping
            topic: Optional topic name for data lookup
            address: Optional PLC address string
            suggested_area_id: Optional area ID suggestion for the entity
        """
        super().__init__(coordinator)
        if name is not None:
            self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info
        self._topic = topic
        self._address = address
        if suggested_area_id:
            self._attr_suggested_area_id = suggested_area_id

    async def _ensure_connected(self) -> None:
        """Ensure PLC connection is active before command execution.

        Raises:
            HomeAssistantError: If PLC is not connected
        """
        if not self.coordinator.is_connected():
            raise HomeAssistantError("PLC not connected: cannot execute command.")

    @property
    def available(self) -> bool:
        if not self.coordinator.is_connected():
            return False
        if self._topic is None:
            return True
        data = self.coordinator.data or {}
        return (self._topic in data) and (data[self._topic] is not None)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return entity state attributes including S7-specific info."""
        attrs: Dict[str, Any] = {}
        if self._address:
            attrs["s7_address"] = self._address.upper()
        if self._topic:
            interval = self.coordinator.get_scan_interval(self._topic)
            attrs["scan_interval"] = f"{interval} s"
            precision = self.coordinator.get_real_precision(self._topic)
            if precision is not None:
                attrs["real_precision"] = precision
            invert_state = getattr(self, "_invert_state", None)
            if invert_state is not None:
                attrs["invert_state"] = invert_state
        return attrs


class S7BoolSyncEntity(S7BaseEntity):
    """Base class for boolean entities with synchronization logic."""

    def __init__(
        self,
        coordinator: S7Coordinator,
        *,
        name: str | None = None,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        state_address: str,
        command_address: str,
        sync_state: bool,
        pulse_command: bool = False,
        pulse_duration: float = 0.5,
        suggested_area_id: str | None = None,
    ) -> None:
        """Initialize boolean sync entity.

        Args:
            coordinator: S7 coordinator instance
            name: Optional entity name
            unique_id: Unique identifier for the entity
            device_info: Device information for entity grouping
            topic: Topic name for state data lookup
            state_address: PLC address to read state from
            command_address: PLC address to write commands to
            sync_state: Whether to sync state changes back to PLC
            pulse_command: Whether to send pulse instead of on/off commands
            pulse_duration: Duration of pulse in seconds
            suggested_area_id: Optional area ID suggestion for the entity
        """
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=state_address,
            suggested_area_id=suggested_area_id,
        )
        self._command_address = command_address
        self._pulse_command = pulse_command
        self._pulse_duration = pulse_duration
        # Pulse and sync are mutually exclusive; pulse takes priority.
        # Sync requires different state/command addresses to be useful.
        self._sync_state = (
            sync_state and not pulse_command and state_address != command_address
        )
        self._last_state: bool | None = None
        self._pending_command: bool | None = None

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._topic)
        return None if val is None else bool(val)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return entity state attributes with command/state address info."""
        attrs: Dict[str, Any] = {}
        if self._address:
            attrs["s7_state_address"] = self._address.upper()
            attrs["s7_command_address"] = self._command_address.upper()
        interval = self.coordinator.get_scan_interval(self._topic)
        attrs["scan_interval"] = f"{interval} s"
        if self._pulse_command:
            attrs.update(
                {
                    "pulse_command": self._pulse_command,
                    "pulse_duration": self._pulse_duration,
                }
            )
        if self._sync_state:
            attrs["sync_state"] = True
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on by writing True to PLC.

        If pulse_command is enabled, sends a pulse instead.

        Raises:
            HomeAssistantError: If write fails or PLC not connected
        """
        if self._pulse_command:
            # Control current state is off, so send pulse to turn on
            if not self.is_on:
                await self._async_pulse()
        else:
            await self._ensure_connected()
            self._pending_command = True
            try:
                await self.coordinator.write_batched(self._command_address, True)
            except HomeAssistantError:
                self._pending_command = None
                raise
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off by writing False to PLC.

        If pulse_command is enabled, sends a pulse instead.

        Raises:
            HomeAssistantError: If write fails or PLC not connected
        """
        if self._pulse_command:
            # Control current state is on, so send pulse to turn off
            if self.is_on:
                await self._async_pulse()
        else:
            await self._ensure_connected()
            self._pending_command = False
            try:
                await self.coordinator.write_batched(self._command_address, False)
            except HomeAssistantError:
                self._pending_command = None
                raise
            await self.coordinator.async_request_refresh()

    async def _async_pulse(self) -> None:
        """Send a pulse to the command address.

        Raises:
            HomeAssistantError: If write fails or PLC not connected
        """
        await self._ensure_connected()
        await self.coordinator.write_batched(self._command_address, True)
        await asyncio.sleep(self._pulse_duration)
        await self.coordinator.write_batched(self._command_address, False)
        await self.coordinator.async_request_refresh()

    @callback
    def async_write_ha_state(self) -> None:
        """Write entity state to Home Assistant with bidirectional sync logic.

        Implements three synchronization scenarios:
        1. Initial state: Store first PLC value without sending commands
        2. HA command echo: Pending command matches PLC response, avoid loop
        3. External change: PLC state changed externally, sync command address
        """
        new_state = self.is_on
        entity_name = getattr(self, "entity_id", self._attr_unique_id)

        # Scenario 1: Initial state from PLC - store without commanding
        if self._last_state is None and new_state is not None:
            self._last_state = new_state
            _LOGGER.debug(
                "%s: Initial state from PLC: %s",
                entity_name,
                new_state,
            )
            super().async_write_ha_state()
            return

        # Scenario 2 & 3: Handle sync logic if enabled and connected
        if (
            self._sync_state
            and new_state is not None
            and self.coordinator.is_connected()
        ):
            # Check for pending command echo from PLC
            if self._pending_command is not None:
                if new_state == self._pending_command:
                    # PLC confirmed our command - clear pending and update
                    _LOGGER.debug(
                        "%s: PLC confirmed command: %s",
                        entity_name,
                        new_state,
                    )
                    self._last_state = new_state
                    self._pending_command = None
                    super().async_write_ha_state()
                    return
                else:
                    # PLC responded with different value - external override
                    _LOGGER.debug(
                        "%s: PLC override: expected %s, got %s",
                        entity_name,
                        self._pending_command,
                        new_state,
                    )
                    self._pending_command = None

            # External state change detected - sync command address
            if new_state != self._last_state:
                _LOGGER.debug(
                    "%s: External change detected: %s -> %s, syncing command address",
                    entity_name,
                    self._last_state,
                    new_state,
                )
                self._last_state = new_state
                # Fire-and-forget batched write to command address
                # Note: Intentionally not awaited to avoid blocking state updates
                self.hass.async_create_background_task(
                    self.coordinator.write_batched(self._command_address, new_state),
                    name=f"s7plc_sync_write_{self._attr_unique_id}",
                )

        super().async_write_ha_state()

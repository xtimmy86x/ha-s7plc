from __future__ import annotations

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
    ) -> None:
        """Initialize S7 base entity.

        Args:
            coordinator: S7 coordinator instance
            name: Optional entity name
            unique_id: Unique identifier for the entity
            device_info: Device information for entity grouping
            topic: Optional topic name for data lookup
            address: Optional PLC address string
        """
        super().__init__(coordinator)
        self._coord: S7Coordinator = coordinator
        if name is not None:
            self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info
        self._topic = topic
        self._address = address

    async def _ensure_connected(self) -> None:
        """Ensure PLC connection is active before command execution.

        Raises:
            HomeAssistantError: If PLC is not connected
        """
        if not self._coord.is_connected():
            raise HomeAssistantError("PLC not connected: cannot execute command.")

    @property
    def available(self) -> bool:
        if not self._coord.is_connected():
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
        interval = self._coord._item_scan_intervals.get(
            self._topic, self._coord._default_scan_interval
        )
        attrs["scan_interval"] = f"{interval} s"
        item_real_precisions = getattr(self._coord, "_item_real_precisions", {})
        precision = item_real_precisions.get(self._topic)
        if precision is not None:
            attrs["real_precision"] = precision
        return attrs

    async def _async_write_bool(
        self, address: str, value: bool, *, error_msg: str | None = None
    ) -> None:
        """Write boolean value to PLC with error handling.

        Args:
            address: PLC address to write to
            value: Boolean value to write
            error_msg: Custom error message (defaults to generic message)

        Raises:
            HomeAssistantError: If write fails
        """
        success = await self.hass.async_add_executor_job(
            self._coord.write_bool, address, value
        )
        if not success:
            if error_msg is None:
                error_msg = f"Failed to write {value} to PLC address {address}"
            _LOGGER.error("%s", error_msg)
            raise HomeAssistantError(f"Failed to send command to PLC: {address}.")

    async def _async_write_number(
        self, address: str, value: float, *, error_msg: str | None = None
    ) -> None:
        """Write numeric value to PLC with error handling.

        Args:
            address: PLC address to write to
            value: Numeric value to write
            error_msg: Custom error message (defaults to generic message)

        Raises:
            HomeAssistantError: If write fails
        """
        success = await self.hass.async_add_executor_job(
            self._coord.write_number, address, value
        )
        if not success:
            if error_msg is None:
                error_msg = f"Failed to write {value} to PLC address {address}"
            _LOGGER.error("%s", error_msg)
            raise HomeAssistantError(f"Failed to send command to PLC: {address}.")


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
        """
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=state_address,
        )
        self._command_address = command_address
        self._sync_state = sync_state
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
        interval = self._coord._item_scan_intervals.get(
            self._topic, self._coord._default_scan_interval
        )
        attrs["scan_interval"] = f"{interval} s"
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on by writing True to PLC.

        Raises:
            HomeAssistantError: If write fails or PLC not connected
        """
        await self._ensure_connected()
        self._pending_command = True
        try:
            await self._async_write_bool(
                self._command_address,
                True,
                error_msg=(
                    f"Failed to write True to PLC address {self._command_address}"
                ),
            )
        except HomeAssistantError:
            self._pending_command = None
            raise
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off by writing False to PLC.

        Raises:
            HomeAssistantError: If write fails or PLC not connected
        """
        await self._ensure_connected()
        self._pending_command = False
        try:
            await self._async_write_bool(
                self._command_address,
                False,
                error_msg=(
                    f"Failed to write False to PLC address {self._command_address}"
                ),
            )
        except HomeAssistantError:
            self._pending_command = None
            raise
        await self.coordinator.async_request_refresh()

    @callback
    def async_write_ha_state(self) -> None:
        new_state = self.is_on

        # Store the initial state without sending commands to the PLC
        if self._last_state is None and new_state is not None:
            self._last_state = new_state
            super().async_write_ha_state()
            return

        # If the state change comes from HA (pending) and matches the PLC
        # response, do not send the command again (avoid echo)
        if self._sync_state and new_state is not None and self._coord.is_connected():
            if self._pending_command is not None:
                if new_state == self._pending_command:
                    # Internal change completed -> update registers and clear
                    self._last_state = new_state
                    self._pending_command = None
                    super().async_write_ha_state()
                    return
                else:
                    # PLC responded differently; clear pending and let logic decide
                    self._pending_command = None

            # External change or mismatch: sync the PLC
            if new_state != self._last_state:
                self._last_state = new_state
                # `async_add_executor_job` schedules work in the executor and
                # returns a Future. It is already scheduled to run, so creating
                # an additional task around it leads to a ``TypeError`` in recent
                # Python versions. We just call it directly to fire-and-forget.
                self.hass.async_add_executor_job(
                    self._coord.write_bool, self._command_address, new_state
                )

        super().async_write_ha_state()

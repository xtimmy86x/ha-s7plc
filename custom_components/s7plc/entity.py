from __future__ import annotations

import logging

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_LOGGER = logging.getLogger(__name__)


class S7BaseEntity(CoordinatorEntity):
    """Base entity for the S7 PLC integration."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        *,
        name: str | None = None,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str | None = None,
        address: str | None = None,
    ):
        super().__init__(coordinator)
        self._coord = coordinator
        if name is not None:
            self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info
        self._topic = topic
        self._address = address

    async def _ensure_connected(self):
        if not self.available:
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
    def extra_state_attributes(self):
        attrs = {}
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


class S7BoolSyncEntity(S7BaseEntity):
    """Base class for boolean entities with synchronization logic."""

    def __init__(
        self,
        coordinator,
        *,
        name: str | None = None,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        state_address: str,
        command_address: str,
        sync_state: bool,
    ):
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
    def extra_state_attributes(self):
        attrs = {}
        if self._address:
            attrs["s7_state_address"] = self._address.upper()
            attrs["s7_command_address"] = self._command_address.upper()
        interval = self._coord._item_scan_intervals.get(
            self._topic, self._coord._default_scan_interval
        )
        attrs["scan_interval"] = interval
        return attrs

    async def _ensure_connected(self):
        if not self.available:
            raise HomeAssistantError("PLC not connected: cannot execute command.")

    async def async_turn_on(self, **kwargs):
        await self._ensure_connected()
        self._pending_command = True
        success = await self.hass.async_add_executor_job(
            self._coord.write_bool, self._command_address, True
        )
        if not success:
            _LOGGER.error(
                "Failed to write True to PLC address %s", self._command_address
            )
            self._pending_command = None
            raise HomeAssistantError(
                f"Failed to send command to PLC: {self._command_address}."
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._ensure_connected()
        self._pending_command = False
        success = await self.hass.async_add_executor_job(
            self._coord.write_bool, self._command_address, False
        )
        if not success:
            _LOGGER.error(
                "Failed to write False to PLC address %s", self._command_address
            )
            self._pending_command = None
            raise HomeAssistantError(
                f"Failed to send command to PLC: {self._command_address}."
            )
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
        if self._sync_state and new_state is not None and self.available:
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

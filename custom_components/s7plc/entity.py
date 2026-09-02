from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .address import normalize_address
from .const import (
    AVAILABILITY_MODE_ALWAYS,
    AVAILABILITY_MODE_BIT,
    AVAILABILITY_MODE_CONNECTION,
    CONF_AVAILABILITY_ADDRESS,
    CONF_AVAILABILITY_MODE,
    CONF_UID,
    SYNC_COMMAND_SETTLE_TIME,
)

if TYPE_CHECKING:
    from .coordinator import S7Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_configure_entity_availability(
    entities: list[S7BaseEntity], items: list[dict[str, Any]]
) -> None:
    """Apply availability options to constructed user entities by permanent UID."""
    by_uid = {item.get(CONF_UID): item for item in items}
    for entity in entities:
        item = by_uid.get(entity._attr_unique_id)
        if item is not None:
            await entity.async_configure_availability(item, item.get("scan_interval"))


class S7BaseEntity(CoordinatorEntity):
    """Base entity for the S7 PLC integration."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _address_attr_name: str = "s7_address"

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
        self._availability_mode = AVAILABILITY_MODE_CONNECTION
        self._availability_topic: str | None = None
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
        if self._availability_mode == AVAILABILITY_MODE_ALWAYS:
            return True
        if not self.coordinator.is_connected():
            return False
        if not self._entity_data_available():
            return False
        if self._availability_mode == AVAILABILITY_MODE_BIT:
            return self._availability_bit_value() is True
        return True

    def _entity_data_available(self) -> bool:
        """Return whether all normal state data required by this entity is valid."""
        if self._topic is None:
            return True
        data = self.coordinator.data or {}
        return (self._topic in data) and (data[self._topic] is not None)

    def _availability_bit_value(self) -> Any:
        if self._availability_topic is None:
            return None
        return (self.coordinator.data or {}).get(self._availability_topic)

    async def async_configure_availability(
        self, item: dict[str, Any], scan_interval: float | None = None
    ) -> None:
        """Apply an entity policy and register its optional internal BIT topic."""
        self._availability_mode = item.get(
            CONF_AVAILABILITY_MODE, AVAILABILITY_MODE_CONNECTION
        )
        address = item.get(CONF_AVAILABILITY_ADDRESS)
        if self._availability_mode == AVAILABILITY_MODE_BIT and address:
            # UID is permanent, unlike an entity's position in the options list.
            self._availability_topic = f"availability:{item[CONF_UID]}"
            await self.coordinator.add_item(
                self._availability_topic, address, scan_interval
            )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity state attributes including S7-specific info."""
        attrs: dict[str, Any] = {}
        if self._address:
            attrs[self._address_attr_name] = self._address.upper()
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


class S7SyncEntity(S7BaseEntity):
    """Base class for entities that synchronize PLC state to a command address."""

    _address_attr_name = "s7_state_address"

    def _initialize_sync(
        self,
        state_address: str,
        command_address: str | None,
        sync_state: bool,
    ) -> None:
        """Initialize synchronization without imposing a value type on subclasses."""
        self._command_address = command_address
        self._sync_state = bool(
            sync_state
            and command_address
            and normalize_address(state_address) != normalize_address(command_address)
        )
        self._last_state: Any = None
        self._pending_command: Any = None
        self._pending_command_time: float | None = None
        self._external_candidate: Any = None
        self._external_candidate_generation: int | None = None
        self._external_candidate_count = 0
        self._plc_update_generation = 0

    def _clear_external_candidate(self) -> None:
        """Discard unconfirmed external feedback."""
        self._external_candidate = None
        self._external_candidate_generation = None
        self._external_candidate_count = 0

    def _set_pending_command(self, value: Any) -> None:
        """Track a new HA command and discard mismatch evidence for an older one."""
        self._clear_external_candidate()
        self._pending_command = value
        self._pending_command_time = time.monotonic()

    def _mark_pending_command_written(self) -> None:
        """Start a full settle window after the command write has completed."""
        if self._pending_command is not None:
            self._pending_command_time = time.monotonic()

    def _clear_pending_command(self) -> None:
        """Clear a completed command and its mismatch evidence."""
        self._pending_command = None
        self._pending_command_time = None
        self._clear_external_candidate()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Record exactly one generation for each real coordinator update."""
        self._plc_update_generation += 1
        super()._handle_coordinator_update()

    def _sync_value(self) -> Any:
        """Return the valid, canonical value to track, or None when unavailable."""
        raise NotImplementedError

    def _sync_payload(self, value: Any) -> Any:
        """Convert a canonical state value to its command-address representation."""
        return value

    @callback
    def async_write_ha_state(self) -> None:
        """Write HA state and synchronize external PLC changes safely."""
        new_state = self._sync_value()
        entity_name = getattr(self, "entity_id", self._attr_unique_id)
        force_ha_update = False
        previous_state = self._last_state
        rejected_command = False

        if self._last_state is None and new_state is not None:
            self._last_state = new_state
            _LOGGER.debug("%s: Initial state from PLC: %s", entity_name, new_state)
            super().async_write_ha_state()
            return

        if (
            self._sync_state
            and new_state is not None
            and self.coordinator.is_connected()
        ):
            if self._pending_command is not None:
                if new_state == self._pending_command:
                    _LOGGER.debug(
                        "%s: PLC confirmed command: %s", entity_name, new_state
                    )
                    self._last_state = new_state
                    self._clear_pending_command()
                    super().async_write_ha_state()
                    return
                command_age = (
                    0.0
                    if self._pending_command_time is None
                    else time.monotonic() - self._pending_command_time
                )
                if command_age < SYNC_COMMAND_SETTLE_TIME:
                    _LOGGER.debug(
                        "%s: HA command not yet confirmed: expected %s, got PLC "
                        "feedback %s after %.3fs; waiting for settle window",
                        entity_name,
                        self._pending_command,
                        new_state,
                        command_age,
                    )
                    # Do not publish a possibly stale sample over HA's command
                    # result until either confirmation or rejection is stable.
                    return
                _LOGGER.debug(
                    "%s: HA command not confirmed: expected %s, got PLC feedback "
                    "%s; realigning command address",
                    entity_name,
                    self._pending_command,
                    new_state,
                )
                self._clear_pending_command()
                # The feedback is authoritative.  This is deliberately handled
                # independently of _last_state: when a command is rejected the
                # PLC often keeps reporting the state HA had already seen.
                self._last_state = new_state
                force_ha_update = True
                rejected_command = True
                should_sync = True
            else:
                should_sync = False
                if new_state == self._last_state:
                    self._clear_external_candidate()
                elif self._external_candidate != new_state:
                    self._external_candidate = new_state
                    self._external_candidate_generation = self._plc_update_generation
                    self._external_candidate_count = 1
                    _LOGGER.debug(
                        "%s: External change candidate: %s -> %s",
                        entity_name,
                        self._last_state,
                        new_state,
                    )
                    return
                elif self._external_candidate_generation != self._plc_update_generation:
                    self._external_candidate_generation = self._plc_update_generation
                    self._external_candidate_count += 1
                    if self._external_candidate_count >= 2:
                        should_sync = True
                        self._clear_external_candidate()
                if not should_sync and new_state != self._last_state:
                    # Repeated HA state writes for one coordinator sample cannot
                    # turn a candidate into accepted PLC feedback.
                    return

            if should_sync:
                if not rejected_command:
                    _LOGGER.debug(
                        "%s: External change detected: %s -> %s, "
                        "syncing command address",
                        entity_name,
                        previous_state,
                        new_state,
                    )
                self._last_state = new_state
                sync_reason = (
                    "rejected HA command" if rejected_command else "external change"
                )

                async def _async_sync_command_write() -> None:
                    try:
                        await self.coordinator.write_batched(
                            self._command_address, self._sync_payload(new_state)
                        )
                    except (HomeAssistantError, TypeError, ValueError) as err:
                        _LOGGER.warning(
                            "%s: Failed to sync command address after %s: %s",
                            entity_name,
                            sync_reason,
                            err,
                        )

                self.hass.async_create_background_task(
                    _async_sync_command_write(),
                    name=f"s7plc_sync_write_{self._attr_unique_id}",
                )

        if force_ha_update:
            # HA's frontend may optimistically display the requested value. If
            # the real value did not change, Entity would normally suppress the
            # identical state event, so force exactly this corrective update.
            previous_force_update = getattr(self, "_attr_force_update", False)
            self._attr_force_update = True
            try:
                super().async_write_ha_state()
            finally:
                self._attr_force_update = previous_force_update
            return

        super().async_write_ha_state()


class S7BoolSyncEntity(S7SyncEntity):
    """Boolean entity using the shared synchronization state machine."""

    _address_attr_name = "s7_state_address"

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
        self._pulse_command = pulse_command
        self._pulse_duration = pulse_duration
        # Pulse and sync are mutually exclusive; pulse takes priority.
        # Sync requires different state/command addresses to be useful.
        self._initialize_sync(
            state_address, command_address, sync_state and not pulse_command
        )

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._topic)
        return None if val is None else bool(val)

    def _sync_value(self) -> bool | None:
        return self.is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity state attributes with command/state address info."""
        attrs = super().extra_state_attributes
        if self._address:
            attrs["s7_command_address"] = self._command_address.upper()
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
            self._set_pending_command(True)
            try:
                await self.coordinator.write_batched(self._command_address, True)
            except HomeAssistantError:
                self._clear_pending_command()
                raise
            self._mark_pending_command_written()
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
            self._set_pending_command(False)
            try:
                await self.coordinator.write_batched(self._command_address, False)
            except HomeAssistantError:
                self._clear_pending_command()
                raise
            self._mark_pending_command_written()
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

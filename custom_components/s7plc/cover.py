from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_AREA,
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COVER_CLOSING_ADDRESS,
    CONF_COVER_OPENING_ADDRESS,
    CONF_COVER_STATUS_ADDRESS,
    CONF_COVER_STATUS_CLOSED_VALUES,
    CONF_COVER_STATUS_CLOSING_VALUES,
    CONF_COVER_STATUS_OPEN_VALUES,
    CONF_COVER_STATUS_OPENING_VALUES,
    CONF_COVER_STATUS_STOPPED_VALUES,
    CONF_COVER_STOPPED_ADDRESS,
    CONF_COVERS,
    CONF_DEVICE_CLASS,
    CONF_INVERT_POSITION,
    CONF_INVERT_TILT,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_OPERATE_TIME,
    CONF_POSITION_COMMAND_ADDRESS,
    CONF_POSITION_STATE_ADDRESS,
    CONF_SCAN_INTERVAL,
    CONF_STOP_COMMAND_ADDRESS,
    CONF_STOP_PULSE_DURATION,
    CONF_TILT_COMMAND_ADDRESS,
    CONF_TILT_STATE_ADDRESS,
    CONF_UID,
    CONF_USE_STATE_TOPICS,
    DEFAULT_COVER_STATUS_CLOSED_VALUES,
    DEFAULT_COVER_STATUS_CLOSING_VALUES,
    DEFAULT_COVER_STATUS_OPEN_VALUES,
    DEFAULT_COVER_STATUS_OPENING_VALUES,
    DEFAULT_COVER_STATUS_STOPPED_VALUES,
    DEFAULT_OPERATE_TIME,
    DEFAULT_PULSE_DURATION,
)
from .entity import S7BaseEntity
from .helpers import (
    default_entity_name,
    get_coordinator_and_device_info,
    parse_mode_values,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, _ = get_coordinator_and_device_info(entry)

    entities: list[S7Cover | S7PositionCover] = []

    for item in entry.options.get(CONF_COVERS, []):
        # Check if this is a position-based cover
        position_state = item.get(CONF_POSITION_STATE_ADDRESS)
        area = item.get(CONF_AREA)

        if position_state:
            # Position-based cover (0-100)
            position_command = item.get(CONF_POSITION_COMMAND_ADDRESS)
            scan_interval = item.get(CONF_SCAN_INTERVAL)
            invert_position = item.get(CONF_INVERT_POSITION, False)
            stop_command = item.get(CONF_STOP_COMMAND_ADDRESS)
            stop_pulse = item.get(CONF_STOP_PULSE_DURATION, DEFAULT_PULSE_DURATION)

            position_topic = f"cover:position:{position_state}"
            await coord.add_item(position_topic, position_state, scan_interval)

            # Optional: tilt control, symmetric to position above.
            tilt_state = item.get(CONF_TILT_STATE_ADDRESS)
            tilt_command = None
            if tilt_state:
                tilt_command = item.get(CONF_TILT_COMMAND_ADDRESS)
                tilt_topic = f"cover:tilt:{tilt_state}"
                await coord.add_item(tilt_topic, tilt_state, scan_interval)

            invert_tilt = item.get(CONF_INVERT_TILT, False)

            # Optional: real-time movement status, same climate-style single
            # status address + per-status value mapping as
            # hvac_status_address. Without it, is_opening/is_closing can
            # only ever be False here, since a raw position alone can't
            # tell HA whether the cover is actively moving.
            cover_status_address = item.get(CONF_COVER_STATUS_ADDRESS)
            cover_status_topic = None
            if cover_status_address:
                cover_status_topic = f"cover:status:{cover_status_address}"
                await coord.add_item(
                    cover_status_topic, cover_status_address, scan_interval
                )

            cover_status_open_values = item.get(
                CONF_COVER_STATUS_OPEN_VALUES, DEFAULT_COVER_STATUS_OPEN_VALUES
            )
            cover_status_closed_values = item.get(
                CONF_COVER_STATUS_CLOSED_VALUES, DEFAULT_COVER_STATUS_CLOSED_VALUES
            )
            cover_status_opening_values = item.get(
                CONF_COVER_STATUS_OPENING_VALUES, DEFAULT_COVER_STATUS_OPENING_VALUES
            )
            cover_status_closing_values = item.get(
                CONF_COVER_STATUS_CLOSING_VALUES, DEFAULT_COVER_STATUS_CLOSING_VALUES
            )
            cover_status_stopped_values = item.get(
                CONF_COVER_STATUS_STOPPED_VALUES, DEFAULT_COVER_STATUS_STOPPED_VALUES
            )

            name = item.get(CONF_NAME) or default_entity_name(position_state)
            unique_id = item[CONF_UID]
            device_class = item.get(CONF_DEVICE_CLASS)

            entities.append(
                S7PositionCover(
                    coord,
                    name,
                    unique_id,
                    device_info,
                    position_state,
                    position_command,
                    invert_position,
                    device_class,
                    area,
                    stop_command,
                    stop_pulse,
                    tilt_state_address=tilt_state,
                    tilt_command_address=tilt_command,
                    invert_tilt=invert_tilt,
                    cover_status_topic=cover_status_topic,
                    cover_status_address=cover_status_address,
                    cover_status_open_values=cover_status_open_values,
                    cover_status_closed_values=cover_status_closed_values,
                    cover_status_opening_values=cover_status_opening_values,
                    cover_status_closing_values=cover_status_closing_values,
                    cover_status_stopped_values=cover_status_stopped_values,
                )
            )
            continue

        # Traditional open/close cover.
        open_command = item.get(CONF_OPEN_COMMAND_ADDRESS)
        close_command = item.get(CONF_CLOSE_COMMAND_ADDRESS)

        if not open_command:
            _LOGGER.debug("Skipping cover with missing open command address")
            continue

        if not close_command:
            _LOGGER.debug("Skipping cover with missing close command address")
            continue

        # State addresses are for end-stop sensors (optional)
        # If not provided, we use operate_time logic
        opened_state = item.get(CONF_OPENING_STATE_ADDRESS)  # Finecorsa aperto
        closed_state = item.get(CONF_CLOSING_STATE_ADDRESS)  # Finecorsa chiuso
        scan_interval = item.get(CONF_SCAN_INTERVAL)

        opened_topic = None
        closed_topic = None

        if opened_state:
            opened_topic = f"cover:opened:{opened_state}"
            await coord.add_item(opened_topic, opened_state, scan_interval)

        if closed_state:
            closed_topic = f"cover:closed:{closed_state}"
            await coord.add_item(closed_topic, closed_state, scan_interval)

        # Optional: real-time movement status, read independently of the
        # opened/closed end-stops above. Each is a separate boolean address,
        # not a multi-value status word.
        cover_opening_address = item.get(CONF_COVER_OPENING_ADDRESS)
        cover_closing_address = item.get(CONF_COVER_CLOSING_ADDRESS)
        cover_stopped_address = item.get(CONF_COVER_STOPPED_ADDRESS)

        cover_opening_topic = None
        cover_closing_topic = None
        cover_stopped_topic = None

        if cover_opening_address:
            cover_opening_topic = f"cover:opening:{cover_opening_address}"
            await coord.add_item(
                cover_opening_topic, cover_opening_address, scan_interval
            )

        if cover_closing_address:
            cover_closing_topic = f"cover:closing:{cover_closing_address}"
            await coord.add_item(
                cover_closing_topic, cover_closing_address, scan_interval
            )

        if cover_stopped_address:
            cover_stopped_topic = f"cover:stopped:{cover_stopped_address}"
            await coord.add_item(
                cover_stopped_topic, cover_stopped_address, scan_interval
            )

        # Optional alternative to the 3 boolean addresses above: a single
        # climate-style status address + per-status value mapping, same as
        # the Position cover's cover_status_address. Takes priority over
        # the boolean addresses when configured.
        cover_status_address = item.get(CONF_COVER_STATUS_ADDRESS)
        cover_status_topic = None
        if cover_status_address:
            cover_status_topic = f"cover:status:{cover_status_address}"
            await coord.add_item(
                cover_status_topic, cover_status_address, scan_interval
            )

        cover_status_open_values = item.get(
            CONF_COVER_STATUS_OPEN_VALUES, DEFAULT_COVER_STATUS_OPEN_VALUES
        )
        cover_status_closed_values = item.get(
            CONF_COVER_STATUS_CLOSED_VALUES, DEFAULT_COVER_STATUS_CLOSED_VALUES
        )
        cover_status_opening_values = item.get(
            CONF_COVER_STATUS_OPENING_VALUES, DEFAULT_COVER_STATUS_OPENING_VALUES
        )
        cover_status_closing_values = item.get(
            CONF_COVER_STATUS_CLOSING_VALUES, DEFAULT_COVER_STATUS_CLOSING_VALUES
        )
        cover_status_stopped_values = item.get(
            CONF_COVER_STATUS_STOPPED_VALUES, DEFAULT_COVER_STATUS_STOPPED_VALUES
        )

        name = item.get(CONF_NAME) or default_entity_name(open_command)
        unique_id = item[CONF_UID]
        device_class = item.get(CONF_DEVICE_CLASS)

        raw_operate_time = item.get(CONF_OPERATE_TIME, DEFAULT_OPERATE_TIME)
        try:
            operate_time = float(raw_operate_time)
        except (TypeError, ValueError):
            operate_time = float(DEFAULT_OPERATE_TIME)
        else:
            if operate_time < 0:
                operate_time = float(DEFAULT_OPERATE_TIME)

        use_state_topics = bool(item.get(CONF_USE_STATE_TOPICS, False))

        entities.append(
            S7Cover(
                coord,
                name,
                unique_id,
                device_info,
                open_command,
                close_command,
                opened_state,
                closed_state,
                opened_topic,
                closed_topic,
                operate_time,
                use_state_topics,
                device_class,
                area,
                cover_opening_address=cover_opening_address,
                cover_closing_address=cover_closing_address,
                cover_stopped_address=cover_stopped_address,
                cover_opening_topic=cover_opening_topic,
                cover_closing_topic=cover_closing_topic,
                cover_stopped_topic=cover_stopped_topic,
                cover_status_topic=cover_status_topic,
                cover_status_address=cover_status_address,
                cover_status_open_values=cover_status_open_values,
                cover_status_closed_values=cover_status_closed_values,
                cover_status_opening_values=cover_status_opening_values,
                cover_status_closing_values=cover_status_closing_values,
                cover_status_stopped_values=cover_status_stopped_values,
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Cover(S7BaseEntity, CoverEntity):
    """Representation of an S7 cover entity."""

    _attr_assumed_state = True

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        open_command: str,
        close_command: str,
        opened_state: str | None,
        closed_state: str | None,
        opened_topic: str | None,
        closed_topic: str | None,
        operate_time: float,
        use_state_topics: bool,
        device_class: str | None = None,
        suggested_area_id: str | None = None,
        cover_opening_address: str | None = None,
        cover_closing_address: str | None = None,
        cover_stopped_address: str | None = None,
        cover_opening_topic: str | None = None,
        cover_closing_topic: str | None = None,
        cover_stopped_topic: str | None = None,
        cover_status_topic: str | None = None,
        cover_status_address: str | None = None,
        cover_status_open_values: str = DEFAULT_COVER_STATUS_OPEN_VALUES,
        cover_status_closed_values: str = DEFAULT_COVER_STATUS_CLOSED_VALUES,
        cover_status_opening_values: str = DEFAULT_COVER_STATUS_OPENING_VALUES,
        cover_status_closing_values: str = DEFAULT_COVER_STATUS_CLOSING_VALUES,
        cover_status_stopped_values: str = DEFAULT_COVER_STATUS_STOPPED_VALUES,
    ) -> None:
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=opened_topic or closed_topic,
            suggested_area_id=suggested_area_id,
        )
        self._open_command_address = open_command
        self._close_command_address = close_command
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )
        self._opened_state_address = opened_state  # Finecorsa aperto
        self._closed_state_address = closed_state  # Finecorsa chiuso
        self._opened_topic = opened_topic
        self._closed_topic = closed_topic
        self._operate_time = max(float(operate_time), 0.0)
        self._use_state_topics = use_state_topics
        self._reset_handles: dict[str, Callable[[], None]] = {}
        self._is_opening = False
        self._is_closing = False
        self._assumed_closed: bool = (
            False  # Assume open by default when using operate_time
        )
        # Optional real-time movement status: overrides the internal timer
        # flags above for display when configured. Independent of
        # is_closed, which always comes from opened_state/closed_state,
        # unless cover_status_address (below) matches open/closed.
        self._cover_opening_address = cover_opening_address
        self._cover_closing_address = cover_closing_address
        self._cover_stopped_address = cover_stopped_address
        self._cover_opening_topic = cover_opening_topic
        self._cover_closing_topic = cover_closing_topic
        self._cover_stopped_topic = cover_stopped_topic

        # Optional alternative to the 3 boolean addresses above: a single
        # climate-style status address + per-status value mapping (same
        # mechanism as the Position cover's cover_status_address), for PLCs
        # that expose movement as one status word instead of separate bits.
        # Takes priority over the boolean addresses when configured.
        self._cover_status_address = cover_status_address
        self._cover_status_topic = cover_status_topic
        self._cover_status_values: dict[str, list[int]] = {
            "open": parse_mode_values(cover_status_open_values),
            "closed": parse_mode_values(cover_status_closed_values),
            "opening": parse_mode_values(cover_status_opening_values),
            "closing": parse_mode_values(cover_status_closing_values),
            "stopped": parse_mode_values(cover_status_stopped_values),
        }
        if device_class:
            try:
                self._attr_device_class = CoverDeviceClass(device_class)
            except ValueError:
                _LOGGER.warning("Invalid device class %s", device_class)

    def _get_topic_state(self, topic: str | None) -> bool | None:
        if topic is None:
            return None
        data = self.coordinator.data or {}
        if topic not in data:
            return None
        value = data.get(topic)
        if value is None:
            return None
        return bool(value)

    def _get_movement_status(self) -> str | None:
        """Return "open"/"closed"/"opening"/"closing"/"stopped", or None if
        unmatched/unset."""
        if not self._cover_status_address:
            return None
        data = self.coordinator.data or {}
        status = data.get(self._cover_status_topic)
        if status is None:
            return None
        try:
            status = int(status)
        except (TypeError, ValueError):
            return None
        for movement, values in self._cover_status_values.items():
            if status in values:
                return movement
        return None

    def _get_effective_movement(self) -> str | None:
        """Return movement from the highest-priority usable source."""
        status = self._get_movement_status()
        if status is not None:
            return status

        if self._cover_stopped_address and self._get_topic_state(
            self._cover_stopped_topic
        ):
            return "stopped"

        opening_state = (
            self._get_topic_state(self._cover_opening_topic)
            if self._cover_opening_address
            else None
        )
        closing_state = (
            self._get_topic_state(self._cover_closing_topic)
            if self._cover_closing_address
            else None
        )
        if opening_state is True:
            return "opening"
        if closing_state is True:
            return "closing"
        if opening_state is not None or closing_state is not None:
            return "stopped"

        if self._is_opening:
            return "opening"
        if self._is_closing:
            return "closing"
        return None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # If using state topics (limit switches), check if movement should stop
        if self._use_state_topics:
            opened_state = self._get_topic_state(self._opened_topic)
            closed_state = self._get_topic_state(self._closed_topic)

            # If opening and reached open position, stop
            if self._is_opening and opened_state is True:
                _LOGGER.debug("Cover %s reached open position, stopping", self.name)
                self.hass.async_create_task(self._complete_operation("open"))

            # If closing and reached closed position, stop
            elif self._is_closing and closed_state is True:
                _LOGGER.debug("Cover %s reached closed position, stopping", self.name)
                self.hass.async_create_task(self._complete_operation("close"))

        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        if not self.coordinator.is_connected():
            return False
        topics = [t for t in (self._opened_topic, self._closed_topic) if t]
        if not topics:
            return True
        data = self.coordinator.data or {}
        return all((topic in data and data[topic] is not None) for topic in topics)

    @property
    def is_opening(self) -> bool:
        """Return True when the effective movement is opening."""
        return self._get_effective_movement() == "opening"

    @property
    def is_closing(self) -> bool:
        """Return True when the effective movement is closing."""
        return self._get_effective_movement() == "closing"

    @property
    def is_closed(self) -> bool | None:
        if self._cover_status_address:
            movement = self._get_movement_status()
            if movement == "closed":
                return True
            if movement == "open":
                return False
        if self._use_state_topics:
            # Use state topics for position feedback
            closed_state = self._get_topic_state(self._closed_topic)
            opened_state = self._get_topic_state(self._opened_topic)

            # Closed topic is True → cover is closed
            if closed_state is True and opened_state is not True:
                return True

            # Opened topic is True → cover is open (not closed)
            if opened_state is True and closed_state is not True:
                return False

            # Both are False or None → unknown state (cover is between positions)
            return None
        else:
            # Use operate time logic - assume cover reaches position after operate_time
            if self._is_opening:
                return False  # Opening, so not closed
            if self._is_closing:
                return False  # Closing but not yet closed
            # Return last known/assumed position
            return self._assumed_closed

    async def async_open_cover(self, **kwargs) -> None:
        await self._ensure_connected()
        await self._stop_operation("close")
        await self.coordinator.write_batched(self._open_command_address, True)
        self._is_opening = True
        self._is_closing = False
        if not self._use_state_topics:
            self._assumed_closed = False  # Assume open when opening starts
        self._schedule_reset("open")
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs) -> None:
        await self._ensure_connected()
        await self._stop_operation("open")
        await self.coordinator.write_batched(self._close_command_address, True)
        self._is_opening = False
        self._is_closing = True
        if not self._use_state_topics:
            self._assumed_closed = True  # Assume closed when closing starts
        self._schedule_reset("close")
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop the cover movement."""
        await self._ensure_connected()

        await self._stop_operation("open")
        await self._stop_operation("close")
        self._is_opening = False
        self._is_closing = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self._open_command_address:
            attrs["s7_open_command_address"] = self._open_command_address.upper()
        if self._close_command_address:
            attrs["s7_close_command_address"] = self._close_command_address.upper()
        if self._use_state_topics:
            if self._opened_state_address:
                attrs["s7_opened_state_address"] = self._opened_state_address.upper()
            if self._closed_state_address:
                attrs["s7_closed_state_address"] = self._closed_state_address.upper()
            attrs["state_topics_used"] = True
        else:
            attrs["state_topics_used"] = False
        if self._opened_topic:
            interval = self.coordinator.get_scan_interval(self._opened_topic)
            attrs["opened_scan_interval"] = f"{interval} s"
        if self._closed_topic:
            interval = self.coordinator.get_scan_interval(self._closed_topic)
            attrs["closed_scan_interval"] = f"{interval} s"
        attrs["operate_time"] = f"{self._operate_time:.1f} s"
        attrs["cover_type"] = "open/close"
        if self._cover_opening_address:
            attrs["s7_cover_opening_address"] = self._cover_opening_address.upper()
        if self._cover_closing_address:
            attrs["s7_cover_closing_address"] = self._cover_closing_address.upper()
        if self._cover_stopped_address:
            attrs["s7_cover_stopped_address"] = self._cover_stopped_address.upper()
        if self._cover_status_address:
            attrs["s7_cover_status_address"] = self._cover_status_address.upper()
            attrs["s7_cover_status_values"] = self._cover_status_values

        return attrs

    def _cancel_reset(self, direction: str) -> None:
        handle = self._reset_handles.pop(direction, None)
        if handle:
            handle()

    def _schedule_reset(self, direction: str) -> None:
        self._cancel_reset(direction)

        async def _async_reset() -> None:
            await self._complete_operation(direction)

        if self._operate_time <= 0:
            self.hass.async_create_task(_async_reset())
            return

        @callback
        def _callback(_now) -> None:
            self._reset_handles.pop(direction, None)
            self.hass.async_create_task(_async_reset())

        self._reset_handles[direction] = async_call_later(
            self.hass, self._operate_time, _callback
        )

    async def _stop_operation(self, direction: str) -> None:
        self._cancel_reset(direction)
        address = (
            self._open_command_address
            if direction == "open"
            else self._close_command_address
        )
        success = True
        if address:
            try:
                await self.coordinator.write_batched(address, False)
            except HomeAssistantError:
                success = False

        if direction == "open":
            self._is_opening = False
        else:
            self._is_closing = False

        # When stopped, maintain last known position
        # No change to _assumed_closed - it keeps the last state

        self.async_write_ha_state()
        if not success:
            await self.coordinator.async_request_refresh()

    async def _complete_operation(self, direction: str) -> None:
        address = (
            self._open_command_address
            if direction == "open"
            else self._close_command_address
        )
        if address:
            try:
                await self.coordinator.write_batched(address, False)
            except HomeAssistantError:
                pass  # Non-critical, already logged
        self._is_opening = False
        self._is_closing = False

        # _assumed_closed is already set when operation starts

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_will_remove_from_hass(self) -> None:
        for cancel in list(self._reset_handles.values()):
            cancel()
        self._reset_handles.clear()
        await super().async_will_remove_from_hass()


class S7PositionCover(S7BaseEntity, CoverEntity):
    """Representation of an S7 cover with position control (0-100).

    Optionally also supports tilt control (current_cover_tilt_position,
    open/close/set/stop_cover_tilt) when tilt_state_address is configured,
    symmetric to the position control above.
    """

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        position_state: str,
        position_command: str | None,
        invert_position: bool = False,
        device_class: str | None = None,
        suggested_area_id: str | None = None,
        stop_command: str | None = None,
        stop_pulse_duration: float = DEFAULT_PULSE_DURATION,
        tilt_state_address: str | None = None,
        tilt_command_address: str | None = None,
        invert_tilt: bool = False,
        cover_status_topic: str | None = None,
        cover_status_address: str | None = None,
        cover_status_open_values: str = DEFAULT_COVER_STATUS_OPEN_VALUES,
        cover_status_closed_values: str = DEFAULT_COVER_STATUS_CLOSED_VALUES,
        cover_status_opening_values: str = DEFAULT_COVER_STATUS_OPENING_VALUES,
        cover_status_closing_values: str = DEFAULT_COVER_STATUS_CLOSING_VALUES,
        cover_status_stopped_values: str = DEFAULT_COVER_STATUS_STOPPED_VALUES,
    ) -> None:
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=f"cover:position:{position_state}",
            suggested_area_id=suggested_area_id,
        )
        self._position_state_address = position_state
        self._position_command_address = position_command or position_state
        self._position_topic = f"cover:position:{position_state}"
        self._invert_position = invert_position
        self._stop_command_address = stop_command
        self._stop_pulse_duration = float(stop_pulse_duration)

        self._tilt_state_address = tilt_state_address
        self._tilt_command_address = tilt_command_address or tilt_state_address
        self._tilt_topic = (
            f"cover:tilt:{tilt_state_address}" if tilt_state_address else None
        )
        self._invert_tilt = invert_tilt

        # Optional real-time movement status: a raw position alone can't
        # tell HA whether the cover is actively moving, so is_opening/
        # is_closing stay False unless this is configured.
        self._cover_status_address = cover_status_address
        self._cover_status_topic = cover_status_topic
        self._cover_status_values: dict[str, list[int]] = {
            "open": parse_mode_values(cover_status_open_values),
            "closed": parse_mode_values(cover_status_closed_values),
            "opening": parse_mode_values(cover_status_opening_values),
            "closing": parse_mode_values(cover_status_closing_values),
            "stopped": parse_mode_values(cover_status_stopped_values),
        }

        features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.STOP
        )
        if tilt_state_address:
            features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.SET_TILT_POSITION
                | CoverEntityFeature.STOP_TILT
            )
        self._attr_supported_features = features

        if device_class:
            try:
                self._attr_device_class = CoverDeviceClass(device_class)
            except ValueError:
                _LOGGER.warning("Invalid device class %s", device_class)

    @staticmethod
    def _clamp_percent(value: Any, invert: bool) -> int | None:
        """Clamp to 0-100 and invert a raw PLC value.

        Shared by position and tilt, which both read/write a 0-100
        percentage with an optional invert flag.
        """
        try:
            pct = int(value)
        except (TypeError, ValueError):
            return None
        pct = max(0, min(100, pct))
        if invert:
            pct = 100 - pct
        return pct

    def _get_position_value(self) -> int | None:
        """Get the current position value from coordinator data."""
        data = self.coordinator.data or {}
        if self._position_topic not in data:
            return None
        value = data.get(self._position_topic)
        if value is None:
            return None
        return self._clamp_percent(value, self._invert_position)

    def _get_tilt_value(self) -> int | None:
        """Get the current tilt value from coordinator data."""
        if self._tilt_topic is None:
            return None
        data = self.coordinator.data or {}
        if self._tilt_topic not in data:
            return None
        value = data.get(self._tilt_topic)
        if value is None:
            return None
        return self._clamp_percent(value, self._invert_tilt)

    @property
    def available(self) -> bool:
        if not self.coordinator.is_connected():
            return False
        data = self.coordinator.data or {}
        return self._position_topic in data and data[self._position_topic] is not None

    @property
    def current_cover_position(self) -> int | None:
        """Return current position (0=closed, 100=open)."""
        return self._get_position_value()

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return current tilt position (0=closed, 100=open), if configured."""
        return self._get_tilt_value()

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed.

        If cover_status_address is configured and the status matches
        cover_status_open_values/cover_status_closed_values, that's
        authoritative. Otherwise (unconfigured, or the status currently
        reads "opening"/"closing"/"stopped"/unmatched) falls back to the
        position value (closed when position == 0).
        """
        if self._cover_status_address:
            movement = self._get_movement_status()
            if movement == "closed":
                return True
            if movement == "open":
                return False
        pos = self._get_position_value()
        if pos is None:
            return None
        return pos == 0

    def _get_movement_status(self) -> str | None:
        """Return "open"/"closed"/"opening"/"closing"/"stopped", or None if
        unmatched/unset."""
        if not self._cover_status_address:
            return None
        data = self.coordinator.data or {}
        status = data.get(self._cover_status_topic)
        if status is None:
            return None
        try:
            status = int(status)
        except (TypeError, ValueError):
            return None
        for movement, values in self._cover_status_values.items():
            if status in values:
                return movement
        return None

    @property
    def is_opening(self) -> bool:
        """Return True when cover_status_address reports "opening".

        Without cover_status_address, position alone can't distinguish
        "moving" from "stopped mid-travel", so this stays False.
        """
        if self._cover_status_address:
            return self._get_movement_status() == "opening"
        return False

    @property
    def is_closing(self) -> bool:
        """Return True when cover_status_address reports "closing". See
        is_opening."""
        if self._cover_status_address:
            return self._get_movement_status() == "closing"
        return False

    async def async_open_cover(self, **kwargs) -> None:
        """Open the cover (set position to 100)."""
        await self.async_set_cover_position(position=100)

    async def async_close_cover(self, **kwargs) -> None:
        """Close the cover (set position to 0)."""
        await self.async_set_cover_position(position=0)

    async def async_set_cover_position(self, **kwargs) -> None:
        """Set cover position (0-100)."""
        await self._ensure_connected()

        position = kwargs.get("position")
        if position is None:
            _LOGGER.error("No position provided for set_cover_position")
            return

        # Clamp to 0-100
        position = max(0, min(100, int(position)))

        # Invert if needed: when user wants 0=open/100=closed,
        # we need to write the inverted value to the PLC
        plc_value = (100 - position) if self._invert_position else position

        await self.coordinator.write_batched(self._position_command_address, plc_value)

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop the cover.

        If a stop command address is configured, pulse it for the configured
        duration.  Otherwise fall back to writing the current position back
        to the command address.
        """
        await self._ensure_connected()

        if self._stop_command_address:
            # Pulse the stop address: set True, wait, set False
            await self.coordinator.write_batched(self._stop_command_address, True)
            await asyncio.sleep(self._stop_pulse_duration)
            await self.coordinator.write_batched(self._stop_command_address, False)
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            actual_position = self._get_position_value()
            if actual_position is not None:
                await self.coordinator.write_batched(
                    self._position_command_address, actual_position
                )
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
            else:
                cover_name = self._attr_name or self.unique_id
                _LOGGER.error(
                    "Cannot stop cover %s because current position is unknown",
                    cover_name,
                )

    async def async_open_cover_tilt(self, **kwargs) -> None:
        """Open the tilt (set tilt position to 100)."""
        await self.async_set_cover_tilt_position(tilt_position=100)

    async def async_close_cover_tilt(self, **kwargs) -> None:
        """Close the tilt (set tilt position to 0)."""
        await self.async_set_cover_tilt_position(tilt_position=0)

    async def async_set_cover_tilt_position(self, **kwargs) -> None:
        """Set tilt position (0-100)."""
        if not self._tilt_command_address:
            _LOGGER.error("Tilt is not configured for this cover")
            return
        await self._ensure_connected()

        tilt_position = kwargs.get("tilt_position")
        if tilt_position is None:
            _LOGGER.error("No tilt_position provided for set_cover_tilt_position")
            return

        tilt_position = max(0, min(100, int(tilt_position)))
        plc_value = (100 - tilt_position) if self._invert_tilt else tilt_position

        await self.coordinator.write_batched(self._tilt_command_address, plc_value)

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_stop_cover_tilt(self, **kwargs) -> None:
        """Stop the tilt.

        Tilt and lift share the same physical stop output (one motor per
        cover), so this reuses stop_command_address exactly like
        async_stop_cover. Without one, falls back to writing the current
        tilt position back, same trick async_stop_cover uses for position.
        """
        if not self._tilt_command_address:
            _LOGGER.error("Tilt is not configured for this cover")
            return
        await self._ensure_connected()

        if self._stop_command_address:
            await self.coordinator.write_batched(self._stop_command_address, True)
            await asyncio.sleep(self._stop_pulse_duration)
            await self.coordinator.write_batched(self._stop_command_address, False)
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            actual_tilt = self._get_tilt_value()
            if actual_tilt is not None:
                await self.async_set_cover_tilt_position(tilt_position=actual_tilt)
            else:
                cover_name = self._attr_name or self.unique_id
                _LOGGER.error(
                    "Cannot stop cover %s tilt because current tilt is unknown",
                    cover_name,
                )

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self._position_state_address:
            attrs["s7_position_state_address"] = self._position_state_address.upper()
        if self._position_command_address:
            attrs["s7_position_command_address"] = (
                self._position_command_address.upper()
            )
        if self._stop_command_address:
            attrs["s7_stop_command_address"] = self._stop_command_address.upper()
            attrs["stop_pulse_duration"] = f"{self._stop_pulse_duration} s"
        if self._tilt_state_address:
            attrs["s7_tilt_state_address"] = self._tilt_state_address.upper()
        if self._tilt_command_address:
            attrs["s7_tilt_command_address"] = self._tilt_command_address.upper()
        if self._cover_status_address:
            attrs["s7_cover_status_address"] = self._cover_status_address.upper()
            attrs["s7_cover_status_values"] = self._cover_status_values
        interval = self.coordinator.get_scan_interval(self._position_topic)
        attrs["closed_scan_interval"] = f"{interval} s"
        attrs["cover_type"] = "position"
        return attrs

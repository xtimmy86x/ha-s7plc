from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_AREA,
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COVERS,
    CONF_DEVICE_CLASS,
    CONF_INVERT_POSITION,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_OPERATE_TIME,
    CONF_POSITION_COMMAND_ADDRESS,
    CONF_POSITION_STATE_ADDRESS,
    CONF_SCAN_INTERVAL,
    CONF_USE_STATE_TOPICS,
    DEFAULT_OPERATE_TIME,
)
from .entity import S7BaseEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

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

            position_topic = f"cover:position:{position_state}"
            await coord.add_item(position_topic, position_state, scan_interval)

            name = item.get(CONF_NAME) or default_entity_name(
                device_info.get("name"), position_state
            )
            unique_id = f"{device_id}:{position_topic}"
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
                )
            )
            continue

        # Traditional open/close cover
        open_command = item.get(CONF_OPEN_COMMAND_ADDRESS)
        close_command = item.get(CONF_CLOSE_COMMAND_ADDRESS)

        if not open_command or not close_command:
            _LOGGER.debug(
                "Skipping cover with missing command addresses: open=%s close=%s",
                open_command,
                close_command,
            )
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

        name = item.get(CONF_NAME) or default_entity_name(
            device_info.get("name"), open_command
        )
        unique_topic = opened_topic or closed_topic or f"cover:command:{open_command}"
        unique_id = f"{device_id}:{unique_topic}"
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
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Cover(S7BaseEntity, CoverEntity):
    """Representation of an S7 cover entity."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )
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

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # If using state topics (limit switches), check if movement should stop
        if self._use_state_topics:
            opened_state = self._get_topic_state(self._opened_topic)
            closed_state = self._get_topic_state(self._closed_topic)

            # If opening and reached open position, stop
            if self._is_opening and opened_state is True:
                _LOGGER.debug("Cover %s reached open position, stopping", self.name)
                self.hass.create_task(self._complete_operation("open"))

            # If closing and reached closed position, stop
            elif self._is_closing and closed_state is True:
                _LOGGER.debug("Cover %s reached closed position, stopping", self.name)
                self.hass.create_task(self._complete_operation("close"))

        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        if not self._coord.is_connected():
            return False
        topics = [t for t in (self._opened_topic, self._closed_topic) if t]
        if not topics:
            return True
        data = self.coordinator.data or {}
        return all((topic in data and data[topic] is not None) for topic in topics)

    @property
    def is_opening(self) -> bool:
        """Return True when the open command output is active."""
        return self._is_opening

    @property
    def is_closing(self) -> bool:
        """Return True when the close command output is active."""
        return self._is_closing

    @property
    def is_closed(self) -> bool | None:
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
        await self._async_write(
            self._open_command_address,
            True,
            error_msg=(
                f"Failed to write True to PLC address {self._open_command_address}"
            ),
        )
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
        await self._async_write(
            self._close_command_address,
            True,
            error_msg=(
                f"Failed to write True to PLC address {self._close_command_address}"
            ),
        )
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

        # Stop both operations
        errors = []

        if self._is_opening:
            try:
                await self._stop_operation("open")
            except Exception as err:
                # Catch any error during stop operation (PLC write failures,
                # communication errors, etc.) and collect for error reporting
                errors.append(f"open: {err}")

        if self._is_closing:
            try:
                await self._stop_operation("close")
            except Exception as err:
                # Catch any error during stop operation to ensure both
                # open and close operations are attempted
                errors.append(f"close: {err}")

        if errors:
            _LOGGER.error("Failed to stop cover: %s", "; ".join(errors))
            raise HomeAssistantError(
                f"Failed to stop cover movement: {'; '.join(errors)}"
            )

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
            interval = self._coord._item_scan_intervals.get(
                self._opened_topic, self._coord._default_scan_interval
            )
            attrs["opened_scan_interval"] = f"{interval} s"
        if self._closed_topic:
            interval = self._coord._item_scan_intervals.get(
                self._closed_topic, self._coord._default_scan_interval
            )
            attrs["closed_scan_interval"] = f"{interval} s"
        attrs["operate_time"] = f"{self._operate_time:.1f} s"
        attrs["cover_type"] = "open/close"

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
            self.hass.create_task(_async_reset())
            return

        def _callback(_now) -> None:
            self._reset_handles.pop(direction, None)
            self.hass.create_task(_async_reset())

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
                await self._async_write(
                    address,
                    False,
                    error_msg=(
                        f"Failed to reset PLC address {address} "
                        f"while stopping {direction} command"
                    ),
                )
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
                await self._async_write(
                    address,
                    False,
                    error_msg=(
                        f"Failed to reset PLC address {address} "
                        f"after {direction} operation"
                    ),
                )
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
    """Representation of an S7 cover with position control (0-100)."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.STOP
    )

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
        if device_class:
            try:
                self._attr_device_class = CoverDeviceClass(device_class)
            except ValueError:
                _LOGGER.warning("Invalid device class %s", device_class)

    def _get_position_value(self) -> int | None:
        """Get the current position value from coordinator data."""
        data = self.coordinator.data or {}
        if self._position_topic not in data:
            return None
        value = data.get(self._position_topic)
        if value is None:
            return None
        try:
            pos = int(value)
            # Clamp to 0-100
            pos = max(0, min(100, pos))
            # Invert if needed: 0 becomes 100, 100 becomes 0
            if self._invert_position:
                pos = 100 - pos
            return pos
        except (TypeError, ValueError):
            return None

    @property
    def available(self) -> bool:
        if not self._coord.is_connected():
            return False
        data = self.coordinator.data or {}
        return self._position_topic in data and data[self._position_topic] is not None

    @property
    def current_cover_position(self) -> int | None:
        """Return current position (0=closed, 100=open)."""
        return self._get_position_value()

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed (position == 0)."""
        pos = self._get_position_value()
        if pos is None:
            return None
        return pos == 0

    @property
    def is_opening(self) -> bool:
        """Return False as we don't track opening state for position covers."""
        return False

    @property
    def is_closing(self) -> bool:
        """Return False as we don't track closing state for position covers."""
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

        await self._async_write(
            self._position_command_address,
            plc_value,
            error_msg=(
                f"Failed to write position {plc_value} to PLC address "
                f"{self._position_command_address}"
            ),
        )

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop the cover (not implemented for position-based covers)."""
        _LOGGER.warning(
            "Stop command not supported for position-based cover %s", self.name
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
        interval = self._coord._item_scan_intervals.get(
            self._position_topic, self._coord._default_scan_interval
        )
        attrs["closed_scan_interval"] = f"{interval} s"
        attrs["cover_type"] = "position"
        return attrs

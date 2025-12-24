from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COVERS,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_OPERATE_TIME,
    CONF_SCAN_INTERVAL,
    DEFAULT_OPERATE_TIME,
    DOMAIN,
)
from .entity import S7BaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]
    device_id = data["device_id"]
    device_name = data["name"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_name,
        manufacturer="Siemens",
        model="S7 PLC",
    )

    entities: list[S7Cover] = []

    for item in entry.options.get(CONF_COVERS, []):
        open_command = item.get(CONF_OPEN_COMMAND_ADDRESS)
        close_command = item.get(CONF_CLOSE_COMMAND_ADDRESS)

        if not open_command or not close_command:
            _LOGGER.debug(
                "Skipping cover with missing command addresses: open=%s close=%s",
                open_command,
                close_command,
            )
            continue

        opening_state = item.get(CONF_OPENING_STATE_ADDRESS) or open_command
        closing_state = item.get(CONF_CLOSING_STATE_ADDRESS) or close_command
        scan_interval = item.get(CONF_SCAN_INTERVAL)

        opening_topic = None
        closing_topic = None

        if opening_state:
            opening_topic = f"cover:opening:{opening_state}"
            await hass.async_add_executor_job(
                coord.add_item, opening_topic, opening_state, scan_interval
            )

        if closing_state:
            closing_topic = f"cover:closing:{closing_state}"
            await hass.async_add_executor_job(
                coord.add_item, closing_topic, closing_state, scan_interval
            )

        name = item.get(CONF_NAME, "S7 Cover")
        unique_topic = opening_topic or closing_topic or f"cover:command:{open_command}"
        unique_id = f"{device_id}:{unique_topic}"

        raw_operate_time = item.get(CONF_OPERATE_TIME, DEFAULT_OPERATE_TIME)
        try:
            operate_time = float(raw_operate_time)
        except (TypeError, ValueError):
            operate_time = float(DEFAULT_OPERATE_TIME)
        else:
            if operate_time < 0:
                operate_time = float(DEFAULT_OPERATE_TIME)

        entities.append(
            S7Cover(
                coord,
                name,
                unique_id,
                device_info,
                open_command,
                close_command,
                opening_state,
                closing_state,
                opening_topic,
                closing_topic,
                operate_time,
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Cover(S7BaseEntity, CoverEntity):
    """Representation of an S7 cover entity."""

    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
    _attr_assumed_state = True

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        open_command: str,
        close_command: str,
        opening_state: str | None,
        closing_state: str | None,
        opening_topic: str | None,
        closing_topic: str | None,
        operate_time: float,
    ) -> None:
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=opening_topic or closing_topic,
        )
        self._open_command_address = open_command
        self._close_command_address = close_command
        self._opening_state_address = opening_state
        self._closing_state_address = closing_state
        self._opening_topic = opening_topic
        self._closing_topic = closing_topic
        self._operate_time = max(float(operate_time), 0.0)
        self._reset_handles: dict[str, Callable[[], None]] = {}

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

    @property
    def available(self) -> bool:
        if not self._coord.is_connected():
            return False
        topics = [t for t in (self._opening_topic, self._closing_topic) if t]
        if not topics:
            return True
        data = self.coordinator.data or {}
        return all((topic in data and data[topic] is not None) for topic in topics)

    @property
    def is_opening(self) -> bool | None:
        return self._get_topic_state(self._opening_topic)

    @property
    def is_closing(self) -> bool | None:
        return self._get_topic_state(self._closing_topic)

    @property
    def is_closed(self) -> bool | None:
        return None

    async def async_open_cover(self, **kwargs) -> None:
        await self._ensure_connected()
        await self._stop_operation("close")
        success = await self.hass.async_add_executor_job(
            self._coord.write_bool, self._open_command_address, True
        )
        if not success:
            _LOGGER.error(
                "Failed to write True to PLC address %s", self._open_command_address
            )
            raise HomeAssistantError(
                f"Failed to send open command to PLC: {self._open_command_address}."
            )
        self._apply_state_updates(opening=True, closing=False)
        self._schedule_reset("open")
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs) -> None:
        await self._ensure_connected()
        await self._stop_operation("open")
        success = await self.hass.async_add_executor_job(
            self._coord.write_bool, self._close_command_address, True
        )
        if not success:
            _LOGGER.error(
                "Failed to write True to PLC address %s", self._close_command_address
            )
            raise HomeAssistantError(
                f"Failed to send close command to PLC: {self._close_command_address}."
            )
        self._apply_state_updates(opening=False, closing=True)
        self._schedule_reset("close")
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self._open_command_address:
            attrs["s7_open_command_address"] = self._open_command_address.upper()
        if self._close_command_address:
            attrs["s7_close_command_address"] = self._close_command_address.upper()
        if self._opening_state_address:
            attrs["s7_opening_state_address"] = self._opening_state_address.upper()
        if self._closing_state_address:
            attrs["s7_closing_state_address"] = self._closing_state_address.upper()

        if self._opening_topic:
            attrs["opening_scan_interval"] = self._coord._item_scan_intervals.get(
                self._opening_topic, self._coord._default_scan_interval
            )
        if self._closing_topic:
            attrs["closing_scan_interval"] = self._coord._item_scan_intervals.get(
                self._closing_topic, self._coord._default_scan_interval
            )
        attrs["operate_time"] = f"{self._operate_time:.1f} s"

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
            success = await self.hass.async_add_executor_job(
                self._coord.write_bool, address, False
            )
            if not success:
                _LOGGER.error(
                    "Failed to reset PLC address %s while stopping %s command",
                    address,
                    direction,
                )

        if direction == "open":
            self._apply_state_updates(opening=False)
        else:
            self._apply_state_updates(closing=False)

        if not success:
            await self.coordinator.async_request_refresh()

    async def _complete_operation(self, direction: str) -> None:
        address = (
            self._open_command_address
            if direction == "open"
            else self._close_command_address
        )
        if address:
            success = await self.hass.async_add_executor_job(
                self._coord.write_bool, address, False
            )
            if not success:
                _LOGGER.error(
                    "Failed to reset PLC address %s after %s operation",
                    address,
                    direction,
                )
        self._apply_state_updates(opening=False, closing=False)
        await self.coordinator.async_request_refresh()

    def _apply_state_updates(
        self, *, opening: bool | None = None, closing: bool | None = None
    ) -> None:
        updates: dict[str, bool] = {}
        if opening is not None and self._opening_topic:
            updates[self._opening_topic] = opening
        if closing is not None and self._closing_topic:
            updates[self._closing_topic] = closing
        if not updates:
            return

        current = dict(self.coordinator.data or {})
        current.update(updates)
        self.coordinator.async_set_updated_data(current)

    async def async_will_remove_from_hass(self) -> None:
        for cancel in list(self._reset_handles.values()):
            cancel()
        self._reset_handles.clear()
        await super().async_will_remove_from_hass()

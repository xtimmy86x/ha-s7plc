from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_ADDRESS,
    CONF_AREA,
    CONF_COMMAND_ADDRESS,
    CONF_OPTIONS_MAP,
    CONF_SCAN_INTERVAL,
    CONF_SELECTS,
    CONF_UID,
)
from .entity import S7BaseEntity, async_configure_entity_availability
from .helpers import default_entity_name, get_coordinator_and_device_info

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


def parse_options_map(raw: str | None) -> dict[int, str] | None:
    """Parse an ``options_map`` string into ``{value: label}``.

    The accepted format is ``value:label`` pairs separated by ``;`` or
    newlines, e.g. ``"0:Off; 1:Pump A; 2:Pump B"``. Labels keep their
    internal characters (including ``:``) because only the first colon of
    each pair is significant. Returns ``None`` when the string is invalid:
    a malformed pair, a non-integer value, an empty label, or a duplicate
    value or label.
    """
    if not raw or not isinstance(raw, str):
        return None
    result: dict[int, str] = {}
    labels: set[str] = set()
    for chunk in raw.replace("\n", ";").split(";"):
        pair = chunk.strip()
        if not pair:
            continue
        value_str, sep, label = pair.partition(":")
        if not sep:
            return None
        label = label.strip()
        if not label:
            return None
        try:
            value = int(value_str.strip())
        except ValueError:
            return None
        if value in result or label in labels:
            return None
        result[value] = label
        labels.add(label)
    return result or None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, _ = get_coordinator_and_device_info(entry)

    entities: list[S7Select] = []
    for item in entry.options.get(CONF_SELECTS, []):
        address = item.get(CONF_ADDRESS)
        options_map = parse_options_map(item.get(CONF_OPTIONS_MAP))
        if not address or not options_map:
            continue
        name = item.get(CONF_NAME) or default_entity_name(address)
        area = item.get(CONF_AREA)
        topic = f"select:{address}"
        unique_id = item[CONF_UID]
        command_address = item.get(CONF_COMMAND_ADDRESS) or address

        scan_interval = item.get(CONF_SCAN_INTERVAL)
        await coord.add_item(topic, address, scan_interval)
        entities.append(
            S7Select(
                coord,
                name,
                unique_id,
                device_info,
                topic,
                address,
                command_address,
                options_map,
                area,
            )
        )

    if entities:
        await async_configure_entity_availability(
            entities, entry.options.get(CONF_SELECTS, [])
        )
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Select(S7BaseEntity, SelectEntity):
    """Select entity mapping labeled options onto a numeric PLC address."""

    _address_attr_name = "s7_state_address"

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        address: str,
        command_address: str | None,
        options_map: dict[int, str],
        suggested_area_id: str | None = None,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
            suggested_area_id=suggested_area_id,
        )
        self._command_address = command_address
        # value -> label as configured; label -> value for writes.
        self._value_to_label = dict(options_map)
        self._label_to_value = {label: value for value, label in options_map.items()}
        self._attr_options = list(options_map.values())

    @property
    def current_option(self) -> str | None:
        value = (self.coordinator.data or {}).get(self._topic)
        if value is None:
            return None
        try:
            value = int(value)
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Non-integer PLC value for select %s: %r", self._topic, value
            )
            return None
        label = self._value_to_label.get(value)
        if label is None:
            _LOGGER.debug("Unmapped PLC value %s for select %s", value, self._topic)
        return label

    async def async_select_option(self, option: str) -> None:
        await self._ensure_connected()
        if not self._command_address:
            raise HomeAssistantError("No command address configured for this entity.")
        value = self._label_to_value.get(option)
        if value is None:
            raise HomeAssistantError(f"Unknown option: {option}")
        await self.coordinator.write_batched(self._command_address, value)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self._command_address:
            attrs["s7_command_address"] = self._command_address.upper()
        attrs["options_map"] = {
            str(value): label for value, label in self._value_to_label.items()
        }
        return attrs

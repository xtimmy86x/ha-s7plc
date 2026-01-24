from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from pyS7.constants import DataType

from .address import parse_tag
from .const import (
    CONF_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_PATTERN,
    CONF_SCAN_INTERVAL,
    CONF_TEXTS,
)
from .entity import S7BaseEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
):
    """Set up text entities from config entry."""
    coordinator, device_info, device_id = get_coordinator_and_device_info(hass, entry)

    config = entry.options or entry.data
    texts = config.get(CONF_TEXTS, [])

    entities = []
    for text_config in texts:
        name = text_config.get(CONF_NAME)
        address = text_config[CONF_ADDRESS]
        command_address = text_config.get(CONF_COMMAND_ADDRESS) or address
        scan_interval = text_config.get(CONF_SCAN_INTERVAL)
        pattern = text_config.get(CONF_PATTERN)

        # Parse tag to get data type and validate
        try:
            tag = parse_tag(address)
            if tag.data_type not in (DataType.STRING, DataType.WSTRING):
                _LOGGER.warning(
                    "Text entity %s uses address %s with unsupported data type %s. "
                    "Only STRING and WSTRING are supported.",
                    name or address,
                    address,
                    tag.data_type,
                )
                continue
        except (RuntimeError, ValueError) as err:
            _LOGGER.error(
                "Failed to parse address %s for text entity %s: %s",
                address,
                name or address,
                err,
            )
            continue

        # Use PLC tag length for limits: min=0, max=tag.length
        # This prevents configuration errors and matches PLC declaration
        min_length = 0
        max_length = tag.length if tag.length is not None else 254

        topic = f"text:{address}"
        unique_id = f"{device_id}:{topic}"
        await coordinator.add_item(topic, address, scan_interval, None)

        entity_name = default_entity_name(name, address)

        entities.append(
            S7Text(
                coordinator=coordinator,
                name=entity_name,
                unique_id=unique_id,
                device_info=device_info,
                topic=topic,
                address=address,
                command_address=command_address,
                min_length=min_length,
                max_length=max_length,
                pattern=pattern,
            )
        )

    async_add_entities(entities)


class S7Text(S7BaseEntity, TextEntity):
    """Representation of a S7 PLC text entity."""

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        address: str,
        command_address: str | None,
        min_length: int,
        max_length: int,
        pattern: str | None,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
        )
        self._command_address = command_address
        self._attr_native_min = min_length
        self._attr_native_max = max_length
        if pattern:
            self._attr_pattern = pattern

    @property
    def native_value(self) -> str | None:
        """Return the current text value."""
        value = (self.coordinator.data or {}).get(self._topic)
        if value is None:
            return None
        return str(value)

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        await self._ensure_connected()

        await self._async_write(
            self._command_address,
            value,
            error_msg=f"Failed to write text to PLC address {self._command_address}",
        )
        await self.coordinator.async_request_refresh()

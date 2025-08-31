from __future__ import annotations
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

class S7BaseEntity(CoordinatorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        *,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str | None = None,
        address: str | None = None,
    ):
        super().__init__(coordinator)
        self._coord = coordinator
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info
        self._topic = topic
        self._address = address

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
            attrs["s7_address"] = self._address
        if self._topic:
            attrs["s7_topic"] = self._topic
        return attrs

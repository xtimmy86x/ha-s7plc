"""Shared state for the two entities belonging to an alarm group."""

from .alarms import AlarmRange, active_alarms
from .entity import S7BaseEntity


class S7AlarmEntity(S7BaseEntity):
    """Consume a shared block sample without creating entities for individual bits."""

    def __init__(self, coordinator, item, device_info, *, presence=False):
        self._alarm_item = item
        self._alarm_presence = presence
        self._alarm_blocks = AlarmRange.parse(
            item["start_address"], item["end_address"]
        ).blocks(item["uid"])
        super().__init__(
            coordinator,
            name=item.get("name") or item["start_address"],
            unique_id=item["uid"] + (":active" if presence else ""),
            device_info=device_info,
            topic=self._alarm_blocks[0][0],
            suggested_area_id=item.get("area"),
        )

    @property
    def _restorable_topics(self):
        return {topic for topic, _ in self._alarm_blocks}

    def _entity_data_available(self):
        return (
            getattr(self.coordinator, "last_update_success", True)
            and active_alarms(self._alarm_item, self.coordinator.data or {}) is not None
        )

    @property
    def alarms(self):
        return active_alarms(self._alarm_item, self._state_data)

    @property
    def extra_state_attributes(self):
        attributes = {
            **super().extra_state_attributes,
            "start_address": self._alarm_item["start_address"],
            "end_address": self._alarm_item["end_address"],
        }
        if not self._alarm_presence:
            attributes["active_alarms"] = self.alarms
        return attributes

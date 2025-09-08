from __future__ import annotations

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity


class S7BaseEntity(CoordinatorEntity):
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

    async def _ensure_connected(self):
        if not self.available:
            raise HomeAssistantError(
                "PLC non connesso: impossibile eseguire il comando."
            )

    async def async_turn_on(self, **kwargs):
        await self._ensure_connected()
        self._pending_command = True
        await self.hass.async_add_executor_job(
            self._coord.write_bool, self._command_address, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._ensure_connected()
        self._pending_command = False
        await self.hass.async_add_executor_job(
            self._coord.write_bool, self._command_address, False
        )
        await self.coordinator.async_request_refresh()

    @callback
    def async_write_ha_state(self) -> None:
        new_state = self.is_on

        # Memorizza lo stato iniziale senza inviare comandi al PLC
        if self._last_state is None and new_state is not None:
            self._last_state = new_state
            super().async_write_ha_state()
            return

        # Se il cambio stato arriva da HA (pending) e ciò che leggo dal PLC
        # coincide con quanto comandato, NON rimando il comando (evito eco).
        if self._sync_state and new_state is not None and self.available:
            if self._pending_command is not None:
                if new_state == self._pending_command:
                    # cambio interno completato -> aggiorno solo i registri interni
                    # e pulisco
                    self._last_state = new_state
                    self._pending_command = None
                    super().async_write_ha_state()
                    return
                else:
                    # il PLC ha risposto diversamente da quanto atteso:
                    # non reinviare subito; azzera il pending e lascia alla logica
                    # sottostante decidere se risincronizzare.
                    self._pending_command = None

            # Qui arrivano SOLO cambi esterni (o mismatch): sincronizzo il PLC
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

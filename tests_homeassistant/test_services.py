"""Validate and dispatch integration services through HA's service registry."""

import pytest
import voluptuous as vol

from custom_components.s7plc.const import DOMAIN
from custom_components.s7plc.plc.address import parse_tag


async def test_services_reach_plc(hass, loaded_entry, plc_client):
    """Both registered handlers execute the real coordinator path."""
    await hass.services.async_call(
        DOMAIN, "health_check", {"entry_id": loaded_entry.entry_id}, blocking=True
    )
    plc_client.get_cpu_info.assert_awaited_once()
    assert loaded_entry.runtime_data.coordinator.last_health_ok is True

    await hass.services.async_call(
        DOMAIN,
        "write_multi",
        {
            "entry_id": loaded_entry.entry_id,
            "writes": [{"address": "DB1,INT2", "value": 42}],
        },
        blocking=True,
    )
    plc_client.write.assert_awaited_once_with([parse_tag("DB1,INT2")], [42])


@pytest.mark.parametrize(
    ("service", "payload"),
    [
        ("health_check", {}),
        ("health_check", {"entry_id": 123}),
        ("write_multi", {"writes": [{"address": "DB1,INT2"}]}),
        ("write_multi", {"writes": [{"address": 123, "value": 42}]}),
    ],
)
async def test_invalid_service_payload_never_reaches_plc(
    hass, loaded_entry, plc_client, service, payload
):
    """HA applies required fields and nested schemas before calling handlers."""
    if service == "write_multi":
        payload = {"entry_id": loaded_entry.entry_id, **payload}
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, service, payload, blocking=True)
    plc_client.write.assert_not_awaited()
    plc_client.get_cpu_info.assert_not_awaited()

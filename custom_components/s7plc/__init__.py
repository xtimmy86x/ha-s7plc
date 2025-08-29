"""S7 PLC integration for Home Assistant.

This module exposes a small helper :func:`get_plc` used by the platforms to
retrieve a shared :class:`~custom_component.s7plc.plc_client.PlcClient`
instance.  Creating a single client per PLC avoids establishing multiple
connections when several entities (sensors, lights, switches) interact with the
same device.
"""

from __future__ import annotations

from typing import Dict, Tuple

from .plc_client import PlcClient

DOMAIN = "s7plc"


def _config_key(config: dict) -> Tuple[str | None, int, int, int]:
    """Return a hashable key for a PLC configuration."""

    return (
        config.get("host"),
        config.get("rack", 0),
        config.get("slot", 2),
        config.get("port", 102),
    )


def get_plc(hass, config: dict) -> PlcClient:
    """Return a shared :class:`PlcClient` for the given configuration.

    The first call for a particular set of connection parameters creates the
    client and stores it inside ``hass.data``.  Subsequent calls reuse the same
    instance, ensuring that Home Assistant keeps only one TCP connection open
    towards the PLC regardless of the number of entities using it.
    """

    hass.data.setdefault(DOMAIN, {})
    key = _config_key(config)
    clients: Dict[Tuple[str | None, int, int, int], PlcClient] = hass.data[DOMAIN]
    if key not in clients:
        clients[key] = PlcClient(config)
    return clients[key]


async def async_setup(hass, config) -> bool:
    """Set up the integration (placeholder for compatibility)."""

    hass.data.setdefault(DOMAIN, {})
    return True
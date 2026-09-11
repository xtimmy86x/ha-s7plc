"""Dashboard assets loaded independently of the administration panel."""

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, VERSION

SCHEDULE_CARD_BUILD = "20260911.3"
SCHEDULE_CARD_PATH = "/s7plc_static/s7plc-schedule-card.js"
SCHEDULE_CARD_MODULE = f"{SCHEDULE_CARD_PATH}?v={VERSION}&build={SCHEDULE_CARD_BUILD}"
_REGISTERED = "_schedule_card_registered"
_RESOURCE_REGISTERED = "_schedule_card_resource_registered"
_LOGGER = logging.getLogger(__name__)


async def async_setup_dashboard(hass: HomeAssistant) -> None:
    """Serve and load the card once, for both storage and YAML dashboards."""
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig
    from homeassistant.components.lovelace import LOVELACE_DATA
    from homeassistant.components.lovelace.resources import ResourceStorageCollection

    data = hass.data.setdefault(DOMAIN, {})
    if not data.get(_REGISTERED):
        asset = Path(__file__).parent / "www" / "s7plc-schedule-card.js"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(SCHEDULE_CARD_PATH, str(asset), cache_headers=False)]
        )
        # Keep the extra module for YAML-managed resources and connected clients.
        # A matching Lovelace module URL is safe: browsers import it only once.
        add_extra_js_url(hass, SCHEDULE_CARD_MODULE)
        data[_REGISTERED] = True

    if data.get(_RESOURCE_REGISTERED):
        return

    # The Lovelace dependency makes its collection available during setup.
    lovelace = hass.data[LOVELACE_DATA]
    resources = (
        lovelace["resources"] if isinstance(lovelace, dict) else lovelace.resources
    )
    if not isinstance(resources, ResourceStorageCollection):
        # YAML resources remain user-managed; the extra module still loads.
        return

    try:
        # Loads persisted items before looking for an existing version, also on
        # older HA versions whose async_create_item does not ensure loading.
        await resources.async_get_info()
        matches = [
            item
            for item in resources.async_items()
            if item["url"].split("?", 1)[0].split("#", 1)[0] == SCHEDULE_CARD_PATH
        ]
        resource = {"url": SCHEDULE_CARD_MODULE, "res_type": "module"}
        if not matches:
            await resources.async_create_item(resource)
        for item in matches:
            if item["url"] != SCHEDULE_CARD_MODULE or item["type"] != "module":
                await resources.async_update_item(item["id"], resource)
    except (HomeAssistantError, OSError) as err:
        # A resource-storage failure must not prevent PLC setup. Leave the flag
        # unset so a later setup call can retry without registering HTTP twice.
        _LOGGER.warning(
            "Could not register schedule card in Lovelace resources: %s", err
        )
        return
    data[_RESOURCE_REGISTERED] = True

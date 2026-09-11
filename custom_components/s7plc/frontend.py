"""Dashboard assets loaded independently of the administration panel."""

from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

SCHEDULE_CARD_BUILD = "20260911.1"
SCHEDULE_CARD_PATH = "/s7plc_static/s7plc-schedule-card.js"
SCHEDULE_CARD_MODULE = f"{SCHEDULE_CARD_PATH}?v={VERSION}&build={SCHEDULE_CARD_BUILD}"
_REGISTERED = "_schedule_card_registered"


async def async_setup_dashboard(hass: HomeAssistant) -> None:
    """Serve and load the card once, for both storage and YAML dashboards."""
    if hass.data.setdefault(DOMAIN, {}).get(_REGISTERED):
        return

    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    asset = Path(__file__).parent / "www" / "s7plc-schedule-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(SCHEDULE_CARD_PATH, str(asset), cache_headers=False)]
    )
    # The frontend dependency initializes this API before integration setup.
    # It also notifies connected browsers; no Lovelace storage mutation is needed.
    add_extra_js_url(hass, SCHEDULE_CARD_MODULE)
    hass.data[DOMAIN][_REGISTERED] = True

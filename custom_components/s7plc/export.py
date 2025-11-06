from __future__ import annotations

import json
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Dict

try:  # pragma: no cover - imported lazily during tests without Home Assistant
    from homeassistant.components.http import HomeAssistantView
    from homeassistant.core import HomeAssistant
    from homeassistant.util import slugify
except ImportError:  # pragma: no cover - fallback for static analysis/tests without HA
    HomeAssistantView = object  # type: ignore[assignment]

    class HomeAssistant:  # type: ignore[override]
        pass

    def slugify(value: str | None) -> str:
        return ""

from .const import DOMAIN, OPTION_KEYS

DOWNLOAD_TTL = 300


def build_export_payload(options: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    payload: dict[str, list[dict[str, Any]]] = {}
    for key in OPTION_KEYS:
        items: list[dict[str, Any]] = []
        raw_items = options.get(key)
        if isinstance(raw_items, list):
            for item in raw_items:
                if isinstance(item, dict):
                    items.append(dict(item))
        payload[key] = items
    return payload


def build_export_json(options: Mapping[str, Any]) -> str:
    return json.dumps(
        build_export_payload(options),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


@dataclass
class ExportDownloadLink:
    url: str
    filename: str


@dataclass
class _QueuedDownload:
    filename: str
    data: str
    created: float


class _ExportView(HomeAssistantView):
    url = "/api/s7plc/export/{token}"
    name = "api:s7plc:export"
    requires_auth = True

    def __init__(self, manager: "ExportManager") -> None:
        self._manager = manager

    async def get(self, request, token: str):
        from aiohttp import web

        download = self._manager.consume(token)
        if download is None:
            raise web.HTTPNotFound()

        headers: Dict[str, str] = {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Disposition": f'attachment; filename="{download.filename}"',
        }
        return web.Response(body=download.data, headers=headers)


class ExportManager:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._downloads: dict[str, _QueuedDownload] = {}
        self._view_registered = False

    def create_download(
        self, entry_title: str | None, entry_name: str | None, data: str
    ) -> ExportDownloadLink:
        self._ensure_view()
        filename_slug = slugify(entry_title or entry_name or DOMAIN)
        if not filename_slug:
            filename_slug = DOMAIN
        filename = f"{filename_slug}-config.json"
        token = secrets.token_urlsafe(12)
        self._downloads[token] = _QueuedDownload(
            filename=filename,
            data=data,
            created=time.time(),
        )
        return ExportDownloadLink(url=f"/api/s7plc/export/{token}", filename=filename)

    def consume(self, token: str) -> _QueuedDownload | None:
        download = self._downloads.pop(token, None)
        if download is None:
            return None
        if time.time() - download.created > DOWNLOAD_TTL:
            return None
        return download

    def _ensure_view(self) -> None:
        if self._view_registered:
            return
        self._hass.http.register_view(_ExportView(self))
        self._view_registered = True


def get_export_manager(hass: HomeAssistant) -> ExportManager:
    domain_data = hass.data.setdefault(DOMAIN, {})
    manager = domain_data.get("export_manager")
    if manager is None:
        manager = ExportManager(hass)
        domain_data["export_manager"] = manager
    return manager


def register_export_download(
    hass: HomeAssistant, entry_title: str | None, entry_name: str | None, data: str
) -> ExportDownloadLink:
    manager = get_export_manager(hass)
    return manager.create_download(entry_title, entry_name, data)
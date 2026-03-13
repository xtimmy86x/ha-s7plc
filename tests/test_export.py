from __future__ import annotations

from custom_components.s7plc import export


class _FakeHTTP:
    def __init__(self) -> None:
        self.views = []

    def register_view(self, view) -> None:
        self.views.append(view)


class _FakeHass:
    def __init__(self) -> None:
        self.data = {}
        self.http = _FakeHTTP()


def test_create_download_purges_expired_tokens(monkeypatch):
    hass = _FakeHass()
    manager = export.ExportManager(hass)
    now = {"value": 1000.0}

    monkeypatch.setattr(
        export,
        "slugify",
        lambda value: str(value).lower().replace(" ", "-") if value else "",
    )
    monkeypatch.setattr(export.time, "time", lambda: now["value"])
    tokens = iter(("token_1", "token_2"))
    monkeypatch.setattr(export.secrets, "token_urlsafe", lambda _: next(tokens))

    manager.create_download("PLC One", "PLC One", '{"a": 1}')
    assert len(manager._downloads) == 1

    now["value"] += export.DOWNLOAD_TTL + 1
    manager.create_download("PLC Two", "PLC Two", '{"b": 2}')

    assert len(manager._downloads) == 1
    assert "token_2" in manager._downloads


def test_consume_purges_other_expired_tokens(monkeypatch):
    hass = _FakeHass()
    manager = export.ExportManager(hass)
    now = {"value": 2000.0}

    monkeypatch.setattr(
        export,
        "slugify",
        lambda value: str(value).lower().replace(" ", "-") if value else "",
    )
    monkeypatch.setattr(export.time, "time", lambda: now["value"])
    tokens = iter(("token_old", "token_fresh"))
    monkeypatch.setattr(export.secrets, "token_urlsafe", lambda _: next(tokens))

    manager.create_download("Old", "Old", '{"old": true}')
    now["value"] += export.DOWNLOAD_TTL - 10
    manager.create_download("Fresh", "Fresh", '{"fresh": true}')
    assert len(manager._downloads) == 2

    now["value"] += 11
    download = manager.consume("token_fresh")

    assert download is not None
    assert download.filename == "fresh-config.json"
    assert manager._downloads == {}

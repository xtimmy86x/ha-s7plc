from __future__ import annotations
import logging, re, threading
from datetime import timedelta
from typing import Dict, Optional, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

try:
    import pyS7
    from pyS7.address_parser import map_address_to_tag
    from pyS7.constants import DataType, MemoryArea
    from pyS7.tag import S7Tag
except Exception as err:
    _LOGGER.error("Impossibile importare pyS7: %s", err, exc_info=True)
    pyS7 = None

STRING_ADDR_RE = re.compile(
    r"^DB(?P<db>\d+)\.(?:DBS|S)(?P<byte>\d+)$", re.IGNORECASE
)

def _tag_from_address(address: str) -> S7Tag:
    """Convert integration address format to pyS7 S7Tag."""
    if pyS7 is None:  # pragma: no cover - safety guard
        raise RuntimeError("pyS7 non disponibile")
    addr = address.replace(" ", "").upper()
    addr = re.sub(r"^DB(\d+)\.", r"DB\\1,", addr)
    return map_address_to_tag(addr)


class S7Coordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator che gestisce connessione Snap7, polling e scritture."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        rack: int = 0,
        slot: int = 1,
        port: int = 102,
        scan_interval: float = 0.5,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="s7plc_coordinator",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._host = host
        self._rack = rack
        self._slot = slot
        self._port = port
        self._lock = threading.RLock()
        self._client: Optional[pyS7.S7Client] = None
        self._items: Dict[str, str] = {}  # topic -> address
        self._connected = False

    def connect(self):
        """Establish connection if needed."""
        with self._lock:
            self._ensure_connected()

    def disconnect(self):
        """Close connection to PLC."""
        with self._lock:
            self._drop_connection()

    def _drop_connection(self):
        """Mark current client as disconnected and close socket."""
        if self._client:
            try:
                self._client.disconnect()
            except Exception as err:
                _LOGGER.debug("Errore durante la disconnessione: %s", err)
        self._connected = False

    def _ensure_connected(self):
        if self._client is None:
            self._client = pyS7.S7Client(self._host, self._rack, self._slot, port=self._port)
        if not self._connected or self._client.socket is None:
            try:
                self._client.connect()
            except Exception as err:
                self._connected = False
                raise RuntimeError(f"Connessione al PLC {self._host} fallita: {err}")
            self._connected = True
            _LOGGER.info(
                "Connesso a PLC S7 %s (rack=%s slot=%s)",
                self._host,
                self._rack,
                self._slot,
            )

    def is_connected(self) -> bool:
        with self._lock:
            return bool(self._client and self._client.socket)

    def add_item(self, topic: str, address: str):
        with self._lock:
            self._items[topic] = address

    async def _async_update_data(self) -> Dict[str, Any]:
        return await self.hass.async_add_executor_job(self._read_all)

    def _read_all(self) -> Dict[str, Any]:
        with self._lock:
            try:
                self._ensure_connected()
            except Exception as e:
                _LOGGER.error("Connessione fallita: %s", e)
                return {}
            items = dict(self._items)

        results: Dict[str, Any] = {}
        with self._lock:
            for topic, addr in items.items():
                try:
                    results[topic] = self._read_one(addr)
                except Exception as e:
                    _LOGGER.error("Errore lettura %s: %s", addr, e)
                    results[topic] = None
                    self._drop_connection()
                    break
        return results

    def _read_one(self, address: str) -> Any:
        m = STRING_ADDR_RE.match(address.replace(" ", ""))
        if m:
            db = int(m.group("db"))
            byte = int(m.group("byte"))
            hdr_tag = S7Tag(
                memory_area=MemoryArea.DB,
                db_number=db,
                data_type=DataType.BYTE,
                start=byte,
                bit_offset=0,
                length=2,
            )
            max_len, cur_len = self._client.read([hdr_tag], optimize=False)[0]
            data = b""
            if max_len > 0:
                data_tag = S7Tag(
                    memory_area=MemoryArea.DB,
                    db_number=db,
                    data_type=DataType.BYTE,
                    start=byte + 2,
                    bit_offset=0,
                    length=max_len,
                )
                data_vals = self._client.read([data_tag], optimize=False)[0]
                data = bytes(data_vals)
            cur_len = min(cur_len, len(data))
            return data[:cur_len].decode("latin-1", errors="ignore")
        

        tag = _tag_from_address(address)
        return self._client.read([tag], optimize=False)[0]

    def write_bool(self, address: str, value: bool):
        tag = _tag_from_address(address)
        if tag.data_type != DataType.BIT:
            raise ValueError("write_bool supporta solo indirizzi bit")
        with self._lock:
            try:
                self._ensure_connected()
                self._client.write([tag], [value])
                return True
            except Exception as err:
                _LOGGER.error("Errore scrittura %s: %s", address, err)
                self._drop_connection()
                return False

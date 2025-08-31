from __future__ import annotations
import logging, re, threading
from datetime import timedelta
from enum import IntEnum
from typing import Dict, Optional, Tuple, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

try:
    import snap7
    from snap7.util import get_bool, get_byte, get_word, get_dword, get_int, get_dint, get_real
    try:
        from snap7.common import Area as Areas  # snap7 v2
    except Exception:
        try:
            from snap7.types import Areas  # snap7 v1
        except Exception:
            class Areas(IntEnum):
                PE = 0x81
                PA = 0x82
                MK = 0x83
                DB = 0x84
                CT = 0x1C
                TM = 0x1D
except Exception as err:
    _LOGGER.error("Impossibile importare snap7: %s", err, exc_info=True)
    snap7 = None

TYPE_BIT = "bit"
TYPE_BYTE = "byte"
TYPE_WORD = "word"
TYPE_DWORD = "dword"
TYPE_INT16 = "int16"
TYPE_INT32 = "int32"
TYPE_REAL = "real"

_ADDR_RE = re.compile(
    r"^DB(?P<db>\d+)\.(?P<tok>[A-Za-z]+)(?P<byte>\d+)(?:\.(?P<bit>\d+))?$"
)

def _norm_token(tok: str) -> str:
    t = tok.upper()
    if t in ("DBX", "X", "BOOL", "BIT"):
        return TYPE_BIT
    if t in ("DBB", "B", "BYTE"):
        return TYPE_BYTE
    if t in ("DBW", "W", "WORD"):
        return TYPE_WORD
    if t in ("DBD", "D", "DWORD"):
        return TYPE_DWORD
    if t in ("INT", "I"):
        return TYPE_INT16
    if t in ("DINT", "DI"):
        return TYPE_INT32
    if t in ("REAL", "FLOAT", "R", "F"):
        return TYPE_REAL
    raise ValueError(f"Token tipo non valido: {tok}")

def parse_address(addr: str) -> Tuple[int, int, Optional[int], str]:
    m = _ADDR_RE.match(addr.replace(" ", ""))
    if not m:
        raise ValueError(f"Indirizzo non valido: {addr}")
    db = int(m.group("db"))
    byte = int(m.group("byte"))
    bit = int(m.group("bit")) if m.group("bit") is not None else None
    ty = _norm_token(m.group("tok"))
    return db, byte, bit, ty

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
        self._client: Optional[snap7.client.Client] = None
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
            self._client = snap7.client.Client()
        if not self._connected or not self._client.get_connected():
            try:
                self._client.connect(self._host, self._rack, self._slot, self._port)
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
            if not self._client:
                return False
            try:
                return self._client.get_connected()
            except Exception:
                return False

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
        db, byte, bit, ty = parse_address(address)
        size = 1
        if ty in (TYPE_WORD, TYPE_INT16):
            size = 2
        elif ty in (TYPE_DWORD, TYPE_INT32, TYPE_REAL):
            size = 4

        raw = self._client.read_area(Areas.DB, db, byte, size)

        if ty == TYPE_BIT:
            return bool(get_bool(raw, 0, bit or 0))
        if ty == TYPE_BYTE:
            return int(get_byte(raw, 0))
        if ty == TYPE_WORD:
            return int(get_word(raw, 0))
        if ty == TYPE_INT16:
            return int(get_int(raw, 0))
        if ty == TYPE_DWORD:
            return int(get_dword(raw, 0))
        if ty == TYPE_INT32:
            return int(get_dint(raw, 0))
        if ty == TYPE_REAL:
            return float(get_real(raw, 0))
        return int.from_bytes(raw, "big")

    def write_bool(self, address: str, value: bool):
        db, byte, bit, ty = parse_address(address)
        if ty != TYPE_BIT:
            raise ValueError("write_bool supporta solo indirizzi bit")
        with self._lock:
            try:
                self._ensure_connected()
                raw = self._client.read_area(Areas.DB, db, byte, 1)
                b = bytearray(raw)
                mask = 1 << (bit or 0)
                if value:
                    b[0] |= mask
                else:
                    b[0] &= (~mask) & 0xFF
                self._client.write_area(Areas.DB, db, byte, bytes(b))
                return True
            except Exception as err:
                _LOGGER.error("Errore scrittura %s: %s", address, err)
                self._drop_connection()
                return False

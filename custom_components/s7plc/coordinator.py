from __future__ import annotations
import logging, re, threading
from datetime import timedelta
from typing import Dict, Optional, Tuple, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

try:
    import pyS7
    from pyS7.constants import DataType, MemoryArea
    from pyS7.tag import S7Tag
except Exception as err:
    _LOGGER.error("Impossibile importare pyS7: %s", err, exc_info=True)
    pyS7 = None

TYPE_BIT = "bit"
TYPE_BYTE = "byte"
TYPE_WORD = "word"
TYPE_DWORD = "dword"
TYPE_INT16 = "int16"
TYPE_INT32 = "int32"
TYPE_REAL = "real"
TYPE_STRING = "string"

if pyS7 is not None:
    _DATATYPE_MAP = {
        TYPE_BIT: DataType.BIT,
        TYPE_BYTE: DataType.BYTE,
        TYPE_WORD: DataType.WORD,
        TYPE_DWORD: DataType.DWORD,
        TYPE_INT16: DataType.INT,
        TYPE_INT32: DataType.DINT,
        TYPE_REAL: DataType.REAL,
    }
else:
    _DATATYPE_MAP = {}


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
    if t in ("S", "DBS", "STR", "STRING"):
        return TYPE_STRING
    raise ValueError(f"Token tipo non valido: {tok}")

def parse_address(addr: str) -> Tuple[int, int, Optional[int], str]:
    m = _ADDR_RE.match(addr.replace(" ", ""))
    if not m:
        raise ValueError(f"Indirizzo non valido: {addr}")
    db = int(m.group("db"))
    byte = int(m.group("byte"))
    bit = int(m.group("bit")) if m.group("bit") is not None else None
    ty = _norm_token(m.group("tok"))
    if ty == TYPE_BIT and (bit is None or bit < 0 or bit > 7):
        raise ValueError(f"Indice bit non valido: {bit}")
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
        db, byte, bit, ty = parse_address(address)
        if ty == TYPE_STRING:
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
                _LOGGER.error("Scrittura %s: %s", data_tag, data_vals)
                data = bytes(data_vals)
            cur_len = min(cur_len, len(data))
            return data[:cur_len].decode("latin-1", errors="ignore")
        

        dt = _DATATYPE_MAP.get(ty)
        if dt is None:
            raise ValueError(f"Tipo non supportato: {ty}")
        bit_offset = 0
        if dt == DataType.BIT:
            if bit is None:
                raise ValueError("Indirizzo bit mancante dell'indice")
            bit_offset = 7 - bit
        
        tag = S7Tag(
            memory_area=MemoryArea.DB,
            db_number=db,
            data_type=dt,
            start=byte,
            bit_offset=bit_offset,
            length=1,
        )
        value = self._client.read([tag], optimize=False)[0]
        return round(value, 1) if dt == DataType.REAL else value

    def write_bool(self, address: str, value: bool):
        db, byte, bit, ty = parse_address(address)
        if ty != TYPE_BIT:
            raise ValueError("write_bool supporta solo indirizzi bit")
        with self._lock:
            try:
                self._ensure_connected()
                if bit is None:
                    raise ValueError("Indirizzo bit mancante dell'indice")
                tag = S7Tag(
                    memory_area=MemoryArea.DB,
                    db_number=db,
                    data_type=DataType.BIT,
                    start=byte,
                    bit_offset=7 - bit,
                    length=1,
                )
                self._client.write([tag], [value])
                return True
            except Exception as err:
                _LOGGER.error("Errore scrittura %s: %s", address, err)
                self._drop_connection()
                return False

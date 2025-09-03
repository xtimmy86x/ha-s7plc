from __future__ import annotations
import logging, re, threading
from datetime import timedelta
from dataclasses import dataclass
from types import SimpleNamespace
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

@dataclass(frozen=True)
class ParsedAddress:
    db: int
    byte: int
    bit: Optional[int]
    ty: str

@dataclass
class TagPlan:
    topic: str
    tag: S7Tag
    postprocess: Optional[Any] = None  # es. lambda v: round(v, 1)

@dataclass
class StringPlan:
    topic: str
    db: int
    start: int  # byte offset della stringa (punto iniziale del header)

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

def parse_address(addr: str) -> ParsedAddress:
    m = _ADDR_RE.match(addr.replace(" ", ""))
    if not m:
        raise ValueError(f"Indirizzo non valido: {addr}")
    db = int(m.group("db"))
    byte = int(m.group("byte"))
    bit = int(m.group("bit")) if m.group("bit") is not None else None
    ty = _norm_token(m.group("tok"))
    if ty == TYPE_BIT and (bit is None or bit < 0 or bit > 7):
        raise ValueError(f"Indice bit non valido: {bit}")
    return ParsedAddress(db, byte, bit, ty)

def map_address_to_tag(address: str) -> Optional[S7Tag]:
    """Return an S7Tag for the given address if it can be batched.

    ``None`` is returned for string or unsupported types which must be
    read individually.
    """
    db, byte, bit, ty = parse_address(address)
    if ty == TYPE_STRING:
        return None
    dt = _DATATYPE_MAP.get(ty)
    if dt is None:
        raise ValueError(f"Tipo non supportato: {ty}")
    bit_offset = 0
    if dt == DataType.BIT:
        if bit is None:
            raise ValueError("Indirizzo bit mancante dell'indice")
        bit_offset = 7 - bit
    return S7Tag(
        memory_area=MemoryArea.DB,
        db_number=db,
        data_type=dt,
        start=byte,
        bit_offset=bit_offset,
        length=1,
    )

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
        self._plc_config = SimpleNamespace(addresses=self._items)
        self._tags: Dict[str, S7Tag] = {}
        self._string_addrs: Dict[str, str] = {}
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
            # Invalidate cache so it will be rebuilt on next update
            self._tags.clear()
            self._string_addrs.clear()

    def _build_tag_cache(self) -> None:
        """Costruisce una volta sola i piani di lettura."""
        self._tags.clear()
        self._string_addrs.clear()
        self._plans_batch: list[TagPlan] = []
        self._plans_str: list[StringPlan] = []

        for topic, addr in self._plc_config.addresses.items():
            try:
                pa = parse_address(addr)
            except Exception:
                _LOGGER.warning("Indirizzo non parsabile %s: %s", topic, addr)
                continue

            if pa.ty == TYPE_STRING:
                # Per le stringhe, salviamo DB e start per header (max_len/cur_len)
                self._string_addrs[topic] = addr  # mantieni se ti serve altrove
                self._plans_str.append(StringPlan(topic, pa.db, pa.byte))
                continue

            # Mappa tipo → DataType
            dt = _DATATYPE_MAP.get(pa.ty)
            if dt is None:
                _LOGGER.warning("Tipo non supportato %s per %s", pa.ty, addr)
                continue

            bit_offset = 0
            if dt == DataType.BIT:
                if pa.bit is None:
                    _LOGGER.error("Bit mancante in %s", addr)
                    continue
                bit_offset = 7 - pa.bit  # mantieni la convenzione usata

            tag = S7Tag(
                memory_area=MemoryArea.DB,
                db_number=pa.db,
                data_type=dt,
                start=pa.byte,
                bit_offset=bit_offset,
                length=1,
            )

            post = (lambda v: round(v, 1)) if dt == DataType.REAL else None
            self._tags[topic] = tag  # se ti serve compatibilità
            self._plans_batch.append(TagPlan(topic, tag, post))

    async def _async_update_data(self) -> Dict[str, Any]:
        if not self._tags and not self._string_addrs:
            with self._lock:
                self._build_tag_cache()
        return await self.hass.async_add_executor_job(self._read_all)

    def _read_all(self) -> Dict[str, Any]:
        with self._lock:
            try:
                self._ensure_connected()
            except Exception as e:
                _LOGGER.error("Connessione fallita: %s", e)
                return {}
            plans_batch = list(self._plans_batch)
            plans_str = list(self._plans_str)

        results: Dict[str, Any] = {}
        try:
            # 1) Letture batchabili
            if plans_batch:
                values = self._client.read([p.tag for p in plans_batch])
                for plan, val in zip(plans_batch, values):
                    results[plan.topic] = plan.postprocess(val) if plan.postprocess else val

            # 2) Letture stringhe (individuali ma ottimizzate)
            for plan in plans_str:
                results[plan.topic] = self._read_string(plan.db, plan.start)

        except Exception as e:
            _LOGGER.error("Errore lettura: %s", e)
            for plan in plans_batch:
                results.setdefault(plan.topic, None)
            for plan in plans_str:
                results.setdefault(plan.topic, None)
            self._drop_connection()

        return results

    def _read_string(self, db: int, start: int) -> str:
        # Header: max_len, cur_len
        hdr_tag = S7Tag(
            memory_area=MemoryArea.DB,
            db_number=db,
            data_type=DataType.BYTE,
            start=start,
            bit_offset=0,
            length=2,
        )
        max_len, cur_len = self._client.read([hdr_tag], optimize=False)[0]
        target_len = max(0, min(max_len, cur_len))
        if target_len == 0:
            return ""

        data = bytearray()
        pdu_size = getattr(self._client, "pdu_length", getattr(self._client, "pdu_size", 240))
        pdu_limit = max(1, pdu_size - 30)

        offset = 0
        while offset < target_len:
            chunk_len = min(target_len - offset, pdu_limit)
            data_tag = S7Tag(
                memory_area=MemoryArea.DB,
                db_number=db,
                data_type=DataType.BYTE,
                start=start + 2 + offset,
                bit_offset=0,
                length=chunk_len,
            )
            chunk = self._client.read([data_tag], optimize=False)[0]
            data.extend(chunk)
            offset += chunk_len

        return bytes(data).decode("latin-1", errors="ignore")

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
            data = bytearray()
            if max_len > 0:
                pdu_size = getattr(
                    self._client, "pdu_length", getattr(self._client, "pdu_size", max_len)
                )
                # The payload of a read request must be smaller than the
                # negotiated PDU size to leave room for protocol headers
                # (Snap7 reserves 18 bytes).
                pdu_limit = max(1, pdu_size - 30)
                offset = 0
                while offset < max_len:
                    chunk_len = min(max_len - offset, pdu_limit)
                    data_tag = S7Tag(
                        memory_area=MemoryArea.DB,
                        db_number=db,
                        data_type=DataType.BYTE,
                        start=byte + 2 + offset,
                        bit_offset=0,
                        length=chunk_len,
                    )
                    chunk_vals = self._client.read([data_tag], optimize=False)[0]
                    data.extend(chunk_vals)
                    offset += chunk_len
            data = bytes(data)
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
        # Prova a riusare la cache se l’indirizzo è già stato aggiunto:
        tag: Optional[S7Tag] = None
        with self._lock:
            for plan in getattr(self, "_plans_batch", []):
                if plan.tag.data_type == DataType.BIT:
                    # ricostruisci stringa "DB{db}.DBX{start}.{bit}" solo se serve confrontare
                    # altrimenti parsalo una volta qui sotto
                    pass

        # Se non trovato in cache, parse una volta sola:
        pa = parse_address(address)
        if pa.ty != TYPE_BIT:
            raise ValueError("write_bool supporta solo indirizzi bit")
        bit_offset = 7 - pa.bit
        tag = S7Tag(
            memory_area=MemoryArea.DB,
            db_number=pa.db,
            data_type=DataType.BIT,
            start=pa.byte,
            bit_offset=bit_offset,
            length=1,
        )

        with self._lock:
            try:
                self._ensure_connected()
                self._client.write([tag], [value])
                return True
            except Exception as err:
                _LOGGER.error("Errore scrittura %s: %s", address, err)
                self._drop_connection()
                return False

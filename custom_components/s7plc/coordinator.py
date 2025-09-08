from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Tipi forward-friendly quando pyS7 non è disponibile
try:
    import pyS7  # type: ignore
    from pyS7.constants import DataType, MemoryArea  # type: ignore
    from pyS7.tag import S7Tag  # type: ignore

    S7ClientT = "pyS7.S7Client"  # per chiarezza nei commenti
except Exception as err:  # pragma: no cover
    _LOGGER.error("Impossibile importare pyS7: %s", err, exc_info=True)
    pyS7 = None  # type: ignore
    DataType = SimpleNamespace(
        BIT=0, BYTE=1, WORD=2, DWORD=3, INT=4, DINT=5, REAL=6
    )  # sentinel
    MemoryArea = SimpleNamespace(DB=0)
    S7Tag = Any  # fallback typing

# -----------------------------
# Costanti & parsing indirizzi
# -----------------------------
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
    _DATATYPE_MAP: Dict[str, Any] = {}

_ADDR_RE = re.compile(
    r"^DB(?P<db>\d+)\.(?P<tok>[A-Za-z]+)(?P<byte>\d+)(?:\.(?P<bit>\d+))?$"
)


@dataclass(frozen=True)
class ParsedAddress:
    db: int
    byte: int
    bit: Optional[int]
    ty: str


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


# -----------------------------
# Piani di lettura
# -----------------------------
@dataclass
class TagPlan:
    topic: str
    tag: S7Tag
    postprocess: Optional[Any] = None  # es. lambda v: round(v, 1)


@dataclass
class StringPlan:
    topic: str
    db: int
    start: int  # byte offset della stringa (inizio header)


# -----------------------------
# Helper interni
# -----------------------------
class _Helpers:
    @staticmethod
    def bit_offset(bit: int) -> int:
        if not 0 <= bit <= 7:
            raise ValueError(f"Indice bit non valido: {bit}")
        return 7 - bit

    @staticmethod
    def make_tag(pa: ParsedAddress) -> S7Tag:
        dt = _DATATYPE_MAP.get(pa.ty)
        if dt is None:
            raise ValueError(f"Tipo non supportato: {pa.ty}")
        bit_off = _Helpers.bit_offset(pa.bit) if dt == DataType.BIT else 0
        return S7Tag(
            memory_area=MemoryArea.DB,
            db_number=pa.db,
            data_type=dt,
            start=pa.byte,
            bit_offset=bit_off,
            length=1,
        )

    @staticmethod
    def apply_postprocess(dt, value):
        # Nota: tieni la presentazione fuori dal trasporto se preferisci
        return round(value, 1) if dt == DataType.REAL else value


# -----------------------------
# API opzionale: mapping indirizzo→tag (riusabile fuori)
# -----------------------------
def map_address_to_tag(address: str) -> Optional[S7Tag]:
    """Ritorna un S7Tag per indirizzi *non-stringa* batchabili.

    None per STRING o tipi non supportati.
    """
    pa = parse_address(address)
    if pa.ty == TYPE_STRING:
        return None
    try:
        return _Helpers.make_tag(pa)
    except Exception:
        return None


# -----------------------------
# Coordinator
# -----------------------------
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
        # Timeout/Retry config
        op_timeout: float = 5.0,  # tempo massimo per un ciclo di lettura/scrittura
        max_retries: int = 3,  # numero di ritenti per singola operazione
        backoff_initial: float = 0.5,  # backoff iniziale
        backoff_max: float = 2.0,  # backoff massimo per attesa tra ritenti
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

        # Config timeout/ritenti
        self._op_timeout = float(op_timeout)
        self._max_retries = int(max_retries)
        self._backoff_initial = float(backoff_initial)
        self._backoff_max = float(backoff_max)

        self._lock = threading.RLock()
        self._client: Optional[Any] = None  # S7Client quando disponibile

        # Config indirizzi: topic -> address string
        self._items: Dict[str, str] = {}

        # Cache piani di lettura (sempre inizializzate)
        self._plans_batch: list[TagPlan] = []
        self._plans_str: list[StringPlan] = []

    # -------------------------
    # Connessione
    # -------------------------
    def _drop_connection(self) -> None:
        if self._client:
            try:
                self._client.disconnect()
            except Exception as err:  # pragma: no cover
                _LOGGER.debug("Errore durante la disconnessione: %s", err)
        # non azzeriamo l'istanza, solo il socket verrà riconnesso

    def _ensure_connected(self) -> None:
        if self._client is None:
            if pyS7 is None:
                raise RuntimeError("pyS7 non disponibile")
            self._client = pyS7.S7Client(
                self._host, self._rack, self._slot, port=self._port
            )
        if not getattr(self._client, "socket", None):
            try:
                self._client.connect()
                _LOGGER.info(
                    "Connesso a PLC S7 %s (rack=%s slot=%s)",
                    self._host,
                    self._rack,
                    self._slot,
                )
            except Exception as err:
                raise RuntimeError(f"Connessione al PLC {self._host} fallita: {err}")

    def is_connected(self) -> bool:
        with self._lock:
            return bool(self._client and getattr(self._client, "socket", None))

    # Metodi pubblici di connessione esplicita (ripristinati)
    def connect(self) -> None:
        """Stabilisce la connessione se necessaria (thread-safe)."""
        with self._lock:
            self._ensure_connected()

    def disconnect(self) -> None:
        """Chiude la connessione al PLC (thread-safe)."""
        with self._lock:
            self._drop_connection()

    # -------------------------
    # Gestione indirizzi
    # -------------------------
    def add_item(self, topic: str, address: str) -> None:
        """Aggiunge/mappa un topic ad un indirizzo PLC e invalida le cache."""
        with self._lock:
            self._items[topic] = address
            self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        self._plans_batch.clear()
        self._plans_str.clear()

    def _build_tag_cache(self) -> None:
        """Costruisce i piani di lettura batch (scalari) e stringhe."""
        self._invalidate_cache()
        for topic, addr in self._items.items():
            try:
                pa = parse_address(addr)
            except Exception:
                _LOGGER.warning("Indirizzo non parsabile %s: %s", topic, addr)
                continue

            if pa.ty == TYPE_STRING:
                self._plans_str.append(StringPlan(topic, pa.db, pa.byte))
                continue

            try:
                tag = _Helpers.make_tag(pa)
            except Exception:
                continue

            # postprocess legato al tipo dati
            def _mk_post(dt):
                return lambda v: _Helpers.apply_postprocess(dt, v)

            self._plans_batch.append(TagPlan(topic, tag, _mk_post(tag.data_type)))

    # -------------------------
    # Retry/timeout helpers
    # -------------------------
    def _sleep(self, seconds: float) -> None:
        try:
            time.sleep(max(0.0, seconds))
        except Exception:
            pass

    def _retry(self, func, *args, **kwargs):
        """Esegue func con ritenti esplicitando un backoff esponenziale.
        Riconnette al PLC tra i tentativi in caso di errore.
        """
        attempt = 0
        last_exc = None
        while attempt <= self._max_retries:
            try:
                # Garantisce connessione prima di ogni tentativo
                self._ensure_connected()
                return func(*args, **kwargs)
            except Exception as e:  # log, droppa connessione e ritenta
                last_exc = e
                _LOGGER.debug("Tentativo %s fallito: %s", attempt + 1, e)
                self._drop_connection()
                if attempt == self._max_retries:
                    break
                backoff = min(self._backoff_initial * (2**attempt), self._backoff_max)
                self._sleep(backoff)
                attempt += 1
        # esauriti i tentativi
        raise (
            last_exc
            if last_exc
            else RuntimeError("Operazione fallita senza eccezione specifica")
        )

    # -------------------------
    # Update loop
    # -------------------------
    async def _async_update_data(self) -> Dict[str, Any]:
        if not self._plans_batch and not self._plans_str:
            with self._lock:
                self._build_tag_cache()
        return await self.hass.async_add_executor_job(self._read_all)

    def _get_pdu_limit(self) -> int:
        # payload < PDU per lasciare spazio agli header (snap7 riserva ~18B)
        size = getattr(
            self._client, "pdu_length", getattr(self._client, "pdu_size", 240)
        )
        return max(1, int(size) - 30)

    def _read_s7_string(self, db: int, start: int) -> str:
        # Header: max_len, cur_len
        hdr_tag = S7Tag(MemoryArea.DB, db, DataType.BYTE, start, 0, 2)
        max_len, cur_len = self._client.read([hdr_tag], optimize=False)[0]
        # Sicurezza sui tipi
        max_len = int(max_len)
        cur_len = int(cur_len)
        target = max(0, min(max_len, cur_len))
        if target == 0:
            return ""

        data = bytearray()
        pdu_limit = self._get_pdu_limit()
        offset = 0
        while offset < target:
            chunk_len = min(target - offset, pdu_limit)
            data_tag = S7Tag(
                MemoryArea.DB, db, DataType.BYTE, start + 2 + offset, 0, chunk_len
            )
            chunk = self._retry(lambda: self._client.read([data_tag], optimize=False))[
                0
            ]
            data.extend(chunk)
            offset += chunk_len

        return bytes(data).decode("latin-1", errors="ignore")

    def _tag_key(self, tag) -> tuple:
        return (
            tag.memory_area,
            tag.db_number,
            tag.data_type,
            tag.start,
            tag.bit_offset,
            tag.length,
        )

    def _read_all(self) -> Dict[str, Any]:
        with self._lock:
            try:
                self._ensure_connected()
            except Exception as e:
                _LOGGER.error("Connessione fallita: %s", e)
                return {}
            plans_batch = list(self._plans_batch)
            plans_str = list(self._plans_str)

        start_ts = time.monotonic()
        deadline = start_ts + self._op_timeout

        results: Dict[str, Any] = {}  # 👈 inizializza PRIMA del try

        try:
            # ===== 1) Batch scalari con dedup & optimize=False =====
            if plans_batch:
                groups: dict[tuple, list[TagPlan]] = {}
                order: list[tuple] = []
                for p in plans_batch:
                    k = self._tag_key(p.tag)  # @staticmethod o con self in firma
                    if k not in groups:
                        groups[k] = []
                        order.append(k)
                    groups[k].append(p)

                try:
                    tags = [groups[k][0].tag for k in order]
                    values = self._retry(
                        lambda: self._client.read(tags, optimize=False)
                    )
                    for k, v in zip(order, values):
                        for plan in groups[k]:
                            results[plan.topic] = (
                                plan.postprocess(v) if plan.postprocess else v
                            )
                except Exception:
                    _LOGGER.exception("Errore batch read")
                    for plan in plans_batch:
                        results.setdefault(plan.topic, None)

            # ===== 2) Check timeout dopo il batch =====
            if time.monotonic() > deadline:
                _LOGGER.warning(
                    "Timeout lettura batch raggiunto (%.2fs)", self._op_timeout
                )
                for plan in plans_str:
                    results.setdefault(plan.topic, None)
                return results

            # ===== 3) Stringhe (con deadline) =====
            for plan in plans_str:
                if time.monotonic() > deadline:
                    _LOGGER.warning(
                        "Timeout lettura stringhe raggiunto (%.2fs)", self._op_timeout
                    )
                    results.setdefault(plan.topic, None)
                    continue
                try:
                    results[plan.topic] = self._read_s7_string(plan.db, plan.start)
                except Exception:
                    _LOGGER.exception("Errore lettura stringa %s", plan.topic)
                    results.setdefault(plan.topic, None)

        except Exception:
            _LOGGER.exception("Errore lettura")
            # qui results esiste già ⇒ niente UnboundLocalError
            for plan in plans_batch:
                results.setdefault(plan.topic, None)
            for plan in plans_str:
                results.setdefault(plan.topic, None)
            self._drop_connection()

        return results

    # -------------------------
    # Letture/scritture ad hoc
    # -------------------------
    def _read_one(self, address: str) -> Any:
        pa = parse_address(address)
        if pa.ty == TYPE_STRING:
            return self._read_s7_string(pa.db, pa.byte)

        tag = _Helpers.make_tag(pa)
        value = self._retry(lambda: self._client.read([tag], optimize=False))[0]
        return _Helpers.apply_postprocess(tag.data_type, value)

    def write_bool(self, address: str, value: bool) -> bool:
        pa = parse_address(address)
        if pa.ty != TYPE_BIT:
            raise ValueError("write_bool supporta solo indirizzi bit")

        tag = _Helpers.make_tag(pa)
        with self._lock:
            try:
                self._ensure_connected()
                self._retry(lambda: self._client.write([tag], [bool(value)]))
                return True
            except Exception:
                _LOGGER.exception("Errore scrittura %s", address)
                self._drop_connection()
                return False

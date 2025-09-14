from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

try:
    import pyS7
    from pyS7.address_parser import S7AddressError
    from pyS7.address_parser import (
        map_address_to_tag as s7_address_parser,
    )
    from pyS7.constants import DataType, MemoryArea
    from pyS7.tag import S7Tag

    S7ClientT = "pyS7.S7Client"
except Exception as err:  # pragma: no cover
    _LOGGER.error("Impossibile importare pyS7: %s", err, exc_info=True)
    pyS7 = None
    DataType = SimpleNamespace(
        BIT=0, BYTE=1, WORD=2, DWORD=3, INT=4, DINT=5, REAL=6, CHAR=7
    )
    MemoryArea = SimpleNamespace(DB=0)
    S7Tag = Any
    s7_address_parser = None
    S7AddressError = Exception


# -----------------------------
# Piani di lettura
# -----------------------------
@dataclass
class TagPlan:
    topic: str
    tag: S7Tag
    postprocess: Optional[Any] = None


@dataclass
class StringPlan:
    topic: str
    db: int
    start: int


# -----------------------------
# Helper interni
# -----------------------------
class _Helpers:
    @staticmethod
    def apply_postprocess(dt, value):
        return round(value, 1) if dt == DataType.REAL else value


def _remap_bit_tag_free(tag: S7Tag) -> S7Tag:
    """Ritorna un nuovo S7Tag con bit_offset rimappato
    (7 - bit) se BIT, altrimenti l'originale."""
    try:
        if getattr(tag, "data_type", None) != DataType.BIT or not hasattr(
            tag, "bit_offset"
        ):
            return tag
        new_bit = 7 - int(tag.bit_offset)
        return S7Tag(
            tag.memory_area,
            tag.db_number,
            tag.data_type,
            tag.start,
            new_bit,
            tag.length,
        )
    except Exception:
        # In caso di errore, non interrompere il flusso
        return tag


# -----------------------------
# API opzionale: mapping indirizzo→tag (riusabile fuori)
# -----------------------------
def map_address_to_tag(address: str) -> Optional[S7Tag]:
    """Ritorna un S7Tag per indirizzi *non-stringa* batchabili.

    None per STRING o se il parser non è disponibile.

    Nota: applica l'inversione del bit (7 - bit) ricreando il tag se necessario.
    """

    if s7_address_parser is None:
        return None

    try:
        tag = s7_address_parser(address)
    except S7AddressError:
        return None

    # Rimappa senza mutare l'istanza originale (S7Tag è frozen)
    tag = _remap_bit_tag_free(tag)

    # CHAR di lunghezza > 1 sono stringhe S7 (header + dati) -> gestite separatamente
    if (
        getattr(tag, "data_type", None) == DataType.CHAR
        and getattr(tag, "length", 1) > 1
    ):
        return None

    return tag


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

    @property
    def host(self) -> str:
        """IP/hostname del PLC associato."""
        return self._host

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

    def connect(self) -> None:
        """Stabilisce la connessione se necessaria (thread-safe)."""
        with self._lock:
            self._ensure_connected()

    def disconnect(self) -> None:
        """Chiude la connessione al PLC (thread-safe)."""
        with self._lock:
            self._drop_connection()

    # -------------------------
    # Parser centralizzato per i tag (inversione bit inclusa)
    # -------------------------
    def _remap_bit_tag(self, tag: S7Tag) -> S7Tag:
        """Come _remap_bit_tag_free, ma come metodo d'istanza."""
        try:
            if tag.data_type != DataType.BIT or not hasattr(tag, "bit_offset"):
                return tag
            new_bit = 7 - int(tag.bit_offset)
            return S7Tag(
                tag.memory_area,
                tag.db_number,
                tag.data_type,
                tag.start,
                new_bit,
                tag.length,
            )
        except Exception:
            return tag

    def _parse_tag(self, address: str) -> S7Tag:
        if s7_address_parser is None:
            raise RuntimeError("Parser indirizzi S7 non disponibile")
        try:
            tag = s7_address_parser(address)
        except S7AddressError as err:
            raise ValueError(f"Indirizzo non valido: {address}") from err

        # Rimappa senza mutare (S7Tag è frozen)
        return self._remap_bit_tag(tag)

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
                tag = self._parse_tag(addr)
            except ValueError:
                _LOGGER.warning("Indirizzo non parsabile %s: %s", topic, addr)
                continue

            # STRING S7 (CHAR con length > 1): gestite separatamente
            if tag.data_type == DataType.CHAR and getattr(tag, "length", 1) > 1:
                self._plans_str.append(StringPlan(topic, tag.db_number, tag.start))
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

    def _read_batch(self, plans_batch: list[TagPlan]) -> Dict[str, Any]:
        """Legge in batch i tag scalari gestendo dedup e postprocess."""
        results: Dict[str, Any] = {}
        if not plans_batch:
            return results

        groups: dict[tuple, list[TagPlan]] = {}
        order: list[tuple] = []
        for plan in plans_batch:
            k = self._tag_key(plan.tag)
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(plan)

        try:
            tags = [groups[k][0].tag for k in order]
            values = self._retry(lambda: self._client.read(tags, optimize=False))
            for k, v in zip(order, values):
                for plan in groups[k]:
                    results[plan.topic] = (
                        plan.postprocess(v) if plan.postprocess else v
                    )
        except Exception:
            _LOGGER.exception("Errore batch read")
            for plan in plans_batch:
                results.setdefault(plan.topic, None)
        return results

    def _read_strings(
        self, plans_str: list[StringPlan], deadline: float
    ) -> Dict[str, Any]:
        """Legge stringhe rispettando una deadline assoluta."""
        results: Dict[str, Any] = {}
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
        return results

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

        results: Dict[str, Any] = {}

        try:
            # ===== 1) Batch scalari con dedup & optimize=False =====
            if plans_batch:
                results.update(self._read_batch(plans_batch))

            # ===== 2) Stringhe (con deadline) =====
            if plans_str:
                results.update(self._read_strings(plans_str, deadline))

            # ===== 3) Check timeout dopo il batch =====
            if time.monotonic() > deadline:
                _LOGGER.warning(
                    "Timeout lettura batch raggiunto (%.2fs)", self._op_timeout
                )
                for plan in plans_str:
                    results.setdefault(plan.topic, None)
                return results


        except Exception:
            _LOGGER.exception("Errore lettura")
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
        tag = self._parse_tag(address)
        if tag.data_type == DataType.CHAR and getattr(tag, "length", 1) > 1:
            return self._read_s7_string(tag.db_number, tag.start)

        value = self._retry(lambda: self._client.read([tag], optimize=False))[0]
        # Normalizza BIT a bool
        if tag.data_type == DataType.BIT:
            return bool(value)
        return _Helpers.apply_postprocess(tag.data_type, value)

    def write_bool(self, address: str, value: bool) -> bool:
        tag = self._parse_tag(address)
        if tag.data_type != DataType.BIT:
            raise ValueError("write_bool supporta solo indirizzi bit")
        with self._lock:
            try:
                self._ensure_connected()
                self._retry(lambda: self._client.write([tag], [bool(value)]))
                return True
            except Exception:
                _LOGGER.exception("Errore scrittura %s", address)
                self._drop_connection()
                return False

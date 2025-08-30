from __future__ import annotations
import re
import threading
import logging
from enum import IntEnum
from typing import Dict, Tuple, Optional

_LOGGER = logging.getLogger(__name__)

# --- Import compatibile con python-snap7 1.x e 2.x
try:
    import snap7
    # util ok su 1.x e 2.x
    from snap7.util import get_bool, get_int, get_dint, get_real, get_byte, get_word, get_dword
    try:
        # python-snap7 2.x: Area sta in snap7.common
        from snap7.common import Area as Areas  # type: ignore[attr-defined]
    except Exception:
        try:
            # python-snap7 1.x: Areas sta in snap7.types
            from snap7.types import Areas  # type: ignore[attr-defined]
        except Exception:
            # Fallback: definiamo una IntEnum compatibile (ha .name)
            class Areas(IntEnum):  # type: ignore[no-redef]
                PE = 0x81
                PA = 0x82
                MK = 0x83
                DB = 0x84
                CT = 0x1C
                TM = 0x1D
            _LOGGER.info("Areas non trovato in snap7: uso fallback IntEnum (compat).")
except Exception as err:
    _LOGGER.error("Import snap7 fallito: %s", err, exc_info=True)
    snap7 = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

# --- tipi supportati
TYPE_BIT   = "bit"     # BOOL
TYPE_BYTE  = "byte"    # 8-bit unsigned
TYPE_WORD  = "word"    # 16-bit unsigned
TYPE_DWORD = "dword"   # 32-bit unsigned
TYPE_INT16 = "int16"   # 16-bit signed (INT)
TYPE_INT32 = "int32"   # 32-bit signed (DINT)
TYPE_REAL  = "real"    # 32-bit float (REAL)

# Accetta: DBX/DBB/DBW/DBD, X/B/W/D, BOOL/BYTE/WORD/DWORD, INT/I, DINT/DI, REAL/FLOAT/R/F
_ADDR_RE = re.compile(
    r"""
    ^
    DB(?P<db>\d+)
    \.
    (?P<tok>[A-Za-z]+)
    (?P<byte>\d+)
    (?:\.(?P<bit>\d+))?
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

def _norm_token(tok: str) -> str:
    t = tok.upper()
    # long form
    if t in ("DBX", "X", "BOOL", "BIT"):
        return TYPE_BIT
    if t in ("DBB", "B", "BYTE"):
        return TYPE_BYTE
    if t in ("DBW", "W", "WORD"):
        return TYPE_WORD
    if t in ("DBD", "D", "DWORD"):
        return TYPE_DWORD
    # explicit signed integers
    if t in ("INT", "I"):
        return TYPE_INT16
    if t in ("DINT", "DI"):
        return TYPE_INT32
    # floats
    if t in ("REAL", "FLOAT", "R", "F"):
        return TYPE_REAL
    # fallback: prova a interpretare come le long form note
    raise ValueError(f"Token tipo non valido: {tok}")

class PlcClient:
    def __init__(self, host: str, rack: int = 0, slot: int = 1, port: int = 102):
        self._host = host
        self._rack = rack
        self._slot = slot
        self._port = port
        self._client = None
        self._lock = threading.RLock()
        self._items: Dict[str, Dict] = {}   # topic -> {"address": "...", "last": value}
        self._connected = False

    # -------- Connessione
    def connect(self):
        if snap7 is None:
            raise RuntimeError("python-snap7 non è installato")
        with self._lock:
            if self._client is None:
                self._client = snap7.client.Client()
            if not self._connected:
                self._client.connect(self._host, self._rack, self._slot, self._port)
                self._connected = True
                _LOGGER.info("S7 client connected to %s rack=%s slot=%s", self._host, self._rack, self._slot)

    def _ensure(self):
        if not self._connected or self._client is None or not self._client.get_connected():
            _LOGGER.warning("S7 reconnecting...")
            self.connect()

    # -------- Registrazione item (opzionale: usato se vuoi popolare da entità)
    def add_item(self, topic: str, address: str):
        with self._lock:
            self._items[topic] = {"address": address, "last": None}

    # -------- Parsing indirizzi
    def _parse(self, address: str) -> Tuple[int, int, Optional[int], str]:
        """
        Ritorna: (db, byte_index, bit_index_or_None, type)
        Esempi validi:
        DB58.DBX2.3 / DB58.X2.3 / DB58.BOOL2.3      -> bit
        DB60.DBB0 / DB60.B0 / DB60.BYTE0            -> byte
        DB60.DBW0 / DB60.W0 / DB60.WORD0            -> word (u16)
        DB60.DBD0 / DB60.D0 / DB60.DWORD0           -> dword (u32)
        DB60.INT0 / DB60.I0                          -> int16 (s16)
        DB60.DINT0 / DB60.DI0                        -> int32 (s32)
        DB60.REAL0 / DB60.FLOAT0 / DB60.R0 / DB60.F0 -> real (f32)
        """
        m = _ADDR_RE.match(address.replace(" ", ""))
        if not m:
            raise ValueError(f"Indirizzo non valido: {address}")
        db = int(m.group("db"))
        byte = int(m.group("byte"))
        bit = int(m.group("bit")) if m.group("bit") is not None else None
        ty = _norm_token(m.group("tok"))
        return db, byte, bit, ty
    
    # -------- Letture
    def read_all(self) -> Dict[str, object]:
        """Legge tutti gli item registrati in modo atomico e restituisce un dict topic->value."""
        with self._lock:
            self._ensure()
            items = list(self._items.items())

        results: Dict[str, object] = {}

        with self._lock:
            for topic, meta in items:
                addr = meta["address"]
                try:
                    val = self._read_one(addr)
                    results[topic] = val
                    self._items[topic]["last"] = val
                except Exception as e:
                    _LOGGER.error("Failed to read address %s", addr, exc_info=True)
                    results[topic] = meta.get("last")

        return results

    def _read_one(self, address: str):
        db, byte, bit, ty = self._parse(address)
        area = Areas.DB

        # calcola size
        if ty == TYPE_BIT:
            size = 1
        elif ty in (TYPE_BYTE,):
            size = 1
        elif ty in (TYPE_WORD, TYPE_INT16):
            size = 2
        elif ty in (TYPE_DWORD, TYPE_INT32, TYPE_REAL):
            size = 4
        else:
            size = 1

        start = byte
        raw = self._client.read_area(area, db, start, size)

        if ty == TYPE_BIT:
            bi = 0 if bit is None else bit
            val = bool(get_bool(raw, 0, bi))
            _LOGGER.debug("Read %s -> raw=%s bit=%s val=%s", address, list(raw), bi, val)
            return val
        if ty == TYPE_BYTE:
            return int(get_byte(raw, 0))
        if ty == TYPE_WORD:
            return int(get_word(raw, 0))          # u16
        if ty == TYPE_INT16:
            return int(get_int(raw, 0))           # s16
        if ty == TYPE_DWORD:
            return int(get_dword(raw, 0))         # u32
        if ty == TYPE_INT32:
            return int(get_dint(raw, 0))          # s32
        if ty == TYPE_REAL:
            return float(get_real(raw, 0))        # f32

        # fallback difensivo (non dovremmo arrivarci)
        return int.from_bytes(raw, "big")

    # -------- Scritture
    def write_bool(self, address: str, value: bool):
        db, byte, bit, ty = self._parse(address)
        if ty != TYPE_BIT:
            raise ValueError(f"write_bool su {address}: non è un bit")
        with self._lock:
            self._ensure()
            # leggere il byte, modificare il bit, scrivere il byte
            raw = self._client.read_area(Areas.DB, db, byte, 1)
            b = bytearray(raw)
            mask = 1 << (bit or 0)
            if value:
                b[0] |= mask
            else:
                b[0] &= (~mask) & 0xFF
            self._client.write_area(Areas.DB, db, byte, bytes(b))
            # aggiorna cache se presente
            for t, meta in self._items.items():
                if meta["address"].strip().upper() == address.strip().upper():
                    meta["last"] = bool(value)

    # helper generico (se serve in futuro)
    def write_byte(self, address: str, value: int):
        db, byte, bit, ty = self._parse(address)
        if ty != TYPE_BYTE:
            raise ValueError("Non è un byte")
        value = max(0, min(255, int(value)))
        with self._lock:
            self._ensure()
            self._client.write_area(Areas.DB, db, byte, value.to_bytes(1, "big"))

    def is_connected(self) -> bool:
        with self._lock:
            if not self._client:
                return False
            try:
                return self._client.get_connected()
            except Exception:
                return False
            
from __future__ import annotations
import re
import threading
import logging
from typing import Dict, Tuple, Optional

try:
    import snap7
    from snap7.util import get_bool, get_int, get_dint, get_real, get_byte, get_word, get_dword
    from snap7.types import Areas
    import logging; logging.getLogger(__name__).warning("Snap7 import OK, version=%s", getattr(snap7, "__version__", "?"))
except Exception:  # pragma: no cover
    import logging; logging.getLogger(__name__).error("Snap7 import FAIL: %s", e, exc_info=True)
    snap7 = None
    Areas = None

_LOGGER = logging.getLogger(__name__)

_ADDR_RE = re.compile(
    r"""
    ^
    DB(?P<db>\d+)
    \.
    (?:
        (?P<long>(?:DBX|DBB|DBW|DBD))(?P<long_byte>\d+)(?:\.(?P<long_bit>\d))?
        |
        (?P<short>[IBWD])(?P<short_byte>\d+)(?:\.(?P<short_bit>\d))?
    )
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

TYPE_BIT = "bit"
TYPE_BYTE = "byte"
TYPE_WORD = "word"
TYPE_DWORD = "dword"
TYPE_REAL = "real"  # alias dword come float


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
        Supporta:
          - DB58.DBX2.3 (bit)
          - DB58.DBB2    (byte)
          - DB58.DBW2    (word)
          - DB58.DBD2    (dword/real)
          - DB58.I2[.3]  (bit, compat: "I" ~ X)
          - DB58.B2      (byte), DB58.W2 (word), DB58.D2 (dword)
        """
        m = _ADDR_RE.match(address.replace(" ", ""))
        if not m:
            raise ValueError(f"Indirizzo non valido: {address}")

        db = int(m.group("db"))
        ty = None
        byte = None
        bit = None

        if m.group("long"):
            long_t = m.group("long").upper()
            byte = int(m.group("long_byte"))
            bit = int(m.group("long_bit")) if m.group("long_bit") else None
            if long_t == "DBX":
                ty = TYPE_BIT
            elif long_t == "DBB":
                ty = TYPE_BYTE
            elif long_t == "DBW":
                ty = TYPE_WORD
            elif long_t == "DBD":
                ty = TYPE_DWORD
        else:
            s = m.group("short").upper()
            byte = int(m.group("short_byte"))
            bit = int(m.group("short_bit")) if m.group("short_bit") else None
            if s == "I":
                ty = TYPE_BIT
            elif s == "B":
                ty = TYPE_BYTE
            elif s == "W":
                ty = TYPE_WORD
            elif s == "D":
                ty = TYPE_DWORD

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
        # calcolo size in bytes per read_area
        size = 1
        if ty == TYPE_BYTE:
            size = 1
        elif ty == TYPE_WORD:
            size = 2
        elif ty in (TYPE_DWORD, TYPE_REAL):
            size = 4
        elif ty == TYPE_BIT:
            size = 1
        start = byte

        # una sola read alla volta (protetta dal lock a monte)
        raw = self._client.read_area(area, db, start, size)

        if ty == TYPE_BIT:
            bit_index = 0 if bit is None else bit
            return bool(get_bool(raw, 0, bit_index))
        if ty == TYPE_BYTE:
            return int(get_byte(raw, 0))
        if ty == TYPE_WORD:
            return int(get_word(raw, 0))
        if ty == TYPE_DWORD:
            return int(get_dword(raw, 0))
        # opzionale: real
        try:
            return float(get_real(raw, 0))
        except Exception:
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

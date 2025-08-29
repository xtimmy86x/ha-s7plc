import re

class Utils:

    def _parse_address(self, address: str) -> tuple[int, str, int, int]:
            """Parse an S7 DB address.

            Returns a tuple of ``(db_number, data_type, byte_offset, bit_offset)``.
            ``bit_offset`` is zero when not used.

            Tipi supportati (e alias):
            X   (bit)                       -> DBX
            B   (byte)                      -> DBB
            W/I (word/int16 signed)         -> DBW / DBI
            D   (dword uint32)              -> DBD / D BW alias DW
            R   (real float32)              -> DBR / DR
            """

            m = re.fullmatch(
                r"DB(\d+)\.(?:DB)?(X|B|W|DW|D|I|DI|R|DR)(\d+)(?:\.(\d+))?",
                address.upper()
            )
            if not m:
                raise ValueError(f"Unsupported address format: {address}")

            db = int(m.group(1))
            dtype = m.group(2)
            byte = int(m.group(3))
            bit = int(m.group(4) or 0)

            # Normalizza alias
            if dtype in {"DW"}:
                dtype = "D"
            elif dtype in {"DI"}:
                dtype = "I"
            elif dtype in {"DR"}:
                dtype = "R"

            return db, dtype, byte, bit
    

import os
import struct
import sys
import unittest

# Ensure the integration package is importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import custom_components.s7plc.plc_client as pc
pc.snap7 = None

from custom_components.s7plc.plc_client import PlcClient


class FakeSnap7Client:
    def __init__(self, data_map, raise_on=None):
        self.data_map = data_map
        self.raise_on = raise_on

    def read_area(self, area, dbnumber, start, size):
        key = (dbnumber, start, size)
        if self.raise_on == key:
            raise RuntimeError("read error")
        return self.data_map[key]


class FakeSnap7WriteClient:
    def __init__(self):
        self.calls = []

    def write_area(self, area, dbnumber, start, data):  # pragma: no cover - simple recorder
        self.calls.append((area, dbnumber, start, data))


class PlcClientReadAllTest(unittest.TestCase):
    def test_read_all_parses_and_converts(self):
        data_map = {
            (1, 0, 1): bytes([0b00000001]),
            (1, 2, 2): (123).to_bytes(2, "big", signed=True),
            (1, 4, 4): struct.pack(">f", 3.14),
        }
        client = FakeSnap7Client(data_map)
        plc = PlcClient({}, client=client)
        plc.add_item("bool/topic", "DB1.DBX0.0")
        plc.add_item("int/topic", "DB1.DBW2")
        plc.add_item("float/topic", "DB1.DBR4")
        result = plc.read_all()
        self.assertTrue(result["bool/topic"])
        self.assertEqual(result["int/topic"], 123)
        self.assertAlmostEqual(result["float/topic"], 3.14, places=5)

    def test_connection_error_logged_and_skipped(self):
        client = FakeSnap7Client({}, raise_on=(1, 0, 1))
        plc = PlcClient({}, client=client)
        plc.add_item("bad/topic", "DB1.DBX0.0")
        with self.assertLogs(level="ERROR") as cm:
            result = plc.read_all()
        self.assertNotIn("bad/topic", result)
        self.assertTrue(any("Failed to read address" in msg for msg in cm.output))


class PlcClientWriteItemTest(unittest.TestCase):
    def test_write_item_translates_and_encodes(self):
        import custom_components.s7plc.plc_client as pc

        expected_area = pc.snap7.type.Areas.DB if pc.snap7 is not None else 0
        cases = [
            ("DB1.DBX0.0", True, 0, bytes([1])),
            ("DB1.DBB1", 7, 1, bytes([7])),
            ("DB1.DBW2", 123, 2, (123).to_bytes(2, "big", signed=True)),
            ("DB1.DBD4", 3.14, 4, struct.pack(">f", 3.14)),
        ]
        for address, value, start, data in cases:
            with self.subTest(address=address):
                client = FakeSnap7WriteClient()
                plc = PlcClient({}, client=client)
                plc.add_item("topic", address)
                plc.write_item("topic", value)
                self.assertEqual(client.calls[0], (expected_area, 1, start, data))

    def test_write_item_stores_when_no_client(self):
        plc = PlcClient({}, client=None)
        plc.add_item("topic", "DB1.DBW0")
        plc.write_item("topic", 42)
        self.assertEqual(plc.read_all()["topic"], 42)

class PlcClientDirectAccessTest(unittest.TestCase):
    def test_write_and_read_address(self):
        import custom_components.s7plc.plc_client as pc

        expected_area = pc.snap7.type.Areas.DB if pc.snap7 is not None else 0
        client = FakeSnap7WriteClient()
        plc = PlcClient({}, client=client)
        plc.write_address("DB1.DBX0.0", True)
        self.assertEqual(client.calls[0], (expected_area, 1, 0, bytes([1])))

        # now test read
        data_map = {(1, 0, 1): bytes([0b00000001])}
        read_plc = PlcClient({}, client=FakeSnap7Client(data_map))
        value = read_plc.read_address("DB1.DBX0.0")
        self.assertTrue(value)

if __name__ == "__main__":
    unittest.main()
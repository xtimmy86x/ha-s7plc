"""Tests for the pyS7 metrics integration."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from custom_components.s7plc.sensor import (
    METRICS_DEFINITIONS,
    MetricDefinition,
    S7MetricsSensor,
)


# ---------------------------------------------------------------------------
# Helper: fake pyS7 metrics object
# ---------------------------------------------------------------------------


class FakePyS7Metrics:
    """Mimics the pyS7 client.metrics object for testing."""

    def __init__(self, **overrides):
        defaults = {
            "connected": True,
            "connection_start_time": 1000.0,
            "connection_count": 3,
            "disconnection_count": 2,
            "connection_uptime": 120.5,
            "read_count": 500,
            "write_count": 100,
            "total_operations": 600,
            "read_errors": 5,
            "write_errors": 2,
            "timeout_errors": 1,
            "total_errors": 8,
            "last_read_duration": 0.012,
            "last_write_duration": 0.008,
            "avg_read_duration": 0.015,
            "avg_write_duration": 0.010,
            "operations_per_minute": 45.3,
            "total_bytes_read": 25600,
            "total_bytes_written": 4096,
            "avg_bytes_per_read": 51.2,
            "avg_bytes_per_write": 40.96,
            "error_rate": 1.33,
            "success_rate": 98.67,
        }
        defaults.update(overrides)
        for k, v in defaults.items():
            setattr(self, k, v)

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def reset(self):
        pass


# ---------------------------------------------------------------------------
# MetricDefinition
# ---------------------------------------------------------------------------


class TestMetricDefinition:
    """Tests for MetricDefinition dataclass."""

    def test_definitions_tuple_not_empty(self):
        assert len(METRICS_DEFINITIONS) > 0

    def test_all_definitions_have_unique_keys(self):
        keys = [d.key for d in METRICS_DEFINITIONS]
        assert len(keys) == len(set(keys)), "Duplicate metric keys found"

    def test_all_definitions_have_required_fields(self):
        for defn in METRICS_DEFINITIONS:
            assert defn.key, f"Missing key in {defn}"
            assert defn.name, f"Missing name in {defn}"
            assert defn.icon, f"Missing icon in {defn}"

    def test_factor_defaults_to_one(self):
        defn = MetricDefinition(key="test", name="Test", icon="mdi:test")
        assert defn.factor == 1.0

    def test_duration_metrics_use_factor_1000(self):
        duration_keys = {"avg_read_duration", "avg_write_duration"}
        for defn in METRICS_DEFINITIONS:
            if defn.key in duration_keys:
                assert defn.factor == 1000.0, f"{defn.key} should convert s→ms"

    def test_all_keys_exist_on_fake_metrics(self):
        """Every metric key must map to an attribute on the pyS7 metrics object."""
        fake = FakePyS7Metrics()
        for defn in METRICS_DEFINITIONS:
            assert hasattr(fake, defn.key), (
                f"FakePyS7Metrics missing attribute for metric key '{defn.key}'"
            )


# ---------------------------------------------------------------------------
# S7MetricsSensor
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_metrics():
    return FakePyS7Metrics()


@pytest.fixture
def coord_with_metrics(mock_coordinator, fake_metrics):
    mock_coordinator._pys7_metrics = fake_metrics
    return mock_coordinator


@pytest.fixture
def coord_without_metrics(mock_coordinator):
    mock_coordinator._pys7_metrics = None
    return mock_coordinator


@pytest.fixture
def device_info():
    return {
        "identifiers": {("s7plc", "test-device")},
        "name": "Test PLC",
        "manufacturer": "Siemens",
    }


def _make_sensor(coordinator, device_info, defn=None):
    """Create a S7MetricsSensor for testing."""
    defn = defn or METRICS_DEFINITIONS[0]
    return S7MetricsSensor(
        coordinator=coordinator,
        unique_id=f"test-device:metrics:{defn.key}",
        device_info=device_info,
        definition=defn,
    )


class TestS7MetricsSensor:
    """Tests for S7MetricsSensor entity."""

    def test_entity_category_is_diagnostic(self, coord_with_metrics, device_info):
        from homeassistant.helpers.entity import EntityCategory

        sensor = _make_sensor(coord_with_metrics, device_info)
        assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC

    def test_has_entity_name(self, coord_with_metrics, device_info):
        sensor = _make_sensor(coord_with_metrics, device_info)
        assert sensor._attr_has_entity_name is True

    def test_unique_id(self, coord_with_metrics, device_info):
        defn = METRICS_DEFINITIONS[0]
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor._attr_unique_id == f"test-device:metrics:{defn.key}"

    def test_translation_key_from_definition(self, coord_with_metrics, device_info):
        defn = METRICS_DEFINITIONS[0]
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor._attr_translation_key == f"metrics_{defn.key}"

    def test_icon_from_definition(self, coord_with_metrics, device_info):
        defn = METRICS_DEFINITIONS[0]
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor._attr_icon == defn.icon

    def test_available_with_metrics(self, coord_with_metrics, device_info):
        sensor = _make_sensor(coord_with_metrics, device_info)
        assert sensor.available is True

    def test_not_available_without_metrics(self, coord_without_metrics, device_info):
        sensor = _make_sensor(coord_without_metrics, device_info)
        assert sensor.available is False

    def test_native_value_connection_uptime(self, coord_with_metrics, device_info):
        defn = _find_defn("connection_uptime")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        # uptime=120.5, factor=1, precision=0 → int(round(120.5)) = 120
        assert sensor.native_value == 120

    def test_native_value_success_rate(self, coord_with_metrics, device_info):
        defn = _find_defn("success_rate")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 98.7  # precision=1

    def test_native_value_error_rate(self, coord_with_metrics, device_info):
        defn = _find_defn("error_rate")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 1.3

    def test_native_value_avg_read_duration_ms(self, coord_with_metrics, device_info):
        defn = _find_defn("avg_read_duration")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        # 0.015s * 1000 = 15.0ms
        assert sensor.native_value == 15.0

    def test_native_value_avg_write_duration_ms(self, coord_with_metrics, device_info):
        defn = _find_defn("avg_write_duration")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        # 0.010s * 1000 = 10.0ms
        assert sensor.native_value == 10.0

    def test_native_value_total_operations(self, coord_with_metrics, device_info):
        defn = _find_defn("total_operations")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 600

    def test_native_value_total_errors(self, coord_with_metrics, device_info):
        defn = _find_defn("total_errors")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 8

    def test_native_value_operations_per_minute(self, coord_with_metrics, device_info):
        defn = _find_defn("operations_per_minute")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 45.3

    def test_native_value_read_count(self, coord_with_metrics, device_info):
        defn = _find_defn("read_count")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 500

    def test_native_value_write_count(self, coord_with_metrics, device_info):
        defn = _find_defn("write_count")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 100

    def test_native_value_connection_count(self, coord_with_metrics, device_info):
        defn = _find_defn("connection_count")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 3

    def test_native_value_disconnection_count(self, coord_with_metrics, device_info):
        defn = _find_defn("disconnection_count")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 2

    def test_native_value_total_bytes_read(self, coord_with_metrics, device_info):
        defn = _find_defn("total_bytes_read")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 25600

    def test_native_value_total_bytes_written(self, coord_with_metrics, device_info):
        defn = _find_defn("total_bytes_written")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value == 4096

    def test_native_value_none_when_no_metrics(
        self, coord_without_metrics, device_info
    ):
        sensor = _make_sensor(coord_without_metrics, device_info)
        assert sensor.native_value is None

    def test_native_value_none_for_missing_attribute(
        self, coord_with_metrics, device_info
    ):
        """Metric key not on the metrics object → None."""
        defn = MetricDefinition(
            key="nonexistent_metric",
            name="Nonexistent",
            icon="mdi:help",
        )
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor.native_value is None

    def test_extra_state_attributes(self, coord_with_metrics, device_info):
        defn = _find_defn("success_rate")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        attrs = sensor.extra_state_attributes
        assert attrs == {"pys7_metric": "success_rate"}

    def test_unit_of_measurement(self, coord_with_metrics, device_info):
        defn = _find_defn("success_rate")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor._attr_native_unit_of_measurement == "%"

    def test_device_class_duration(self, coord_with_metrics, device_info):
        from homeassistant.components.sensor import SensorDeviceClass

        defn = _find_defn("connection_uptime")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor._attr_device_class == SensorDeviceClass.DURATION

    def test_state_class_measurement(self, coord_with_metrics, device_info):
        from homeassistant.components.sensor import SensorStateClass

        defn = _find_defn("success_rate")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor._attr_state_class == SensorStateClass.MEASUREMENT

    def test_state_class_total_increasing(self, coord_with_metrics, device_info):
        from homeassistant.components.sensor import SensorStateClass

        defn = _find_defn("total_operations")
        sensor = _make_sensor(coord_with_metrics, device_info, defn)
        assert sensor._attr_state_class == SensorStateClass.TOTAL_INCREASING


# ---------------------------------------------------------------------------
# All metrics produce valid values
# ---------------------------------------------------------------------------


class TestAllMetricsValues:
    """Ensure every defined metric produces a non-None native_value."""

    @pytest.mark.parametrize(
        "key", [d.key for d in METRICS_DEFINITIONS], ids=[d.key for d in METRICS_DEFINITIONS]
    )
    def test_metric_value_not_none(self, mock_coordinator, device_info, key):
        fake = FakePyS7Metrics()
        mock_coordinator._pys7_metrics = fake
        defn = _find_defn(key)
        sensor = _make_sensor(mock_coordinator, device_info, defn)
        value = sensor.native_value
        assert value is not None, f"Metric '{key}' returned None"
        assert isinstance(value, (int, float)), f"Metric '{key}' returned {type(value)}"


# ---------------------------------------------------------------------------
# Coordinator properties
# ---------------------------------------------------------------------------


class TestCoordinatorMetricsProperties:
    """Tests for pys7_metrics / pys7_metrics_dict on the real coordinator."""

    def test_pys7_metrics_returns_client_metrics(self, monkeypatch):
        from custom_components.s7plc.coordinator import S7Coordinator

        hass = MagicMock()
        hass.data = {}
        coord = S7Coordinator.__new__(S7Coordinator)
        # Minimal init for the properties
        coord._client = MagicMock()
        fake = FakePyS7Metrics()
        coord._client.metrics = fake

        assert coord.pys7_metrics is fake

    def test_pys7_metrics_none_when_no_client(self, monkeypatch):
        from custom_components.s7plc.coordinator import S7Coordinator

        coord = S7Coordinator.__new__(S7Coordinator)
        coord._client = None

        assert coord.pys7_metrics is None

    def test_pys7_metrics_none_when_client_has_no_metrics(self, monkeypatch):
        from custom_components.s7plc.coordinator import S7Coordinator

        coord = S7Coordinator.__new__(S7Coordinator)
        coord._client = MagicMock(spec=[])  # no 'metrics' attribute

        assert coord.pys7_metrics is None

    def test_pys7_metrics_dict_returns_dict(self, monkeypatch):
        from custom_components.s7plc.coordinator import S7Coordinator

        coord = S7Coordinator.__new__(S7Coordinator)
        coord._client = MagicMock()
        fake = FakePyS7Metrics()
        coord._client.metrics = fake

        result = coord.pys7_metrics_dict
        assert isinstance(result, dict)
        assert "total_operations" in result
        assert result["total_operations"] == 600

    def test_pys7_metrics_dict_empty_when_no_metrics(self, monkeypatch):
        from custom_components.s7plc.coordinator import S7Coordinator

        coord = S7Coordinator.__new__(S7Coordinator)
        coord._client = None

        assert coord.pys7_metrics_dict == {}


# ---------------------------------------------------------------------------
# Diagnostics integration
# ---------------------------------------------------------------------------


class TestDiagnosticsMetrics:
    """Tests for metrics in diagnostics output."""

    @pytest.mark.asyncio
    async def test_diagnostics_includes_pys7_metrics(self):
        from custom_components.s7plc.diagnostics import (
            async_get_config_entry_diagnostics,
        )

        hass = MagicMock()
        fake = FakePyS7Metrics()

        mock_coordinator = MagicMock()
        mock_coordinator.is_connected.return_value = True
        mock_coordinator.last_update_success = True
        mock_coordinator.update_interval = None
        mock_coordinator._plans_batch = []
        mock_coordinator._plans_str = []
        mock_coordinator._items = {}
        mock_coordinator.data = {}
        mock_coordinator.pys7_metrics_dict = fake.as_dict()

        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.title = "Test PLC"
        entry.data = {}
        entry.options = {}

        @dataclass
        class _RT:
            coordinator: object
            name: str
            host: str
            device_id: str

        entry.runtime_data = _RT(
            coordinator=mock_coordinator,
            name="Test PLC",
            host="192.168.1.1",
            device_id="test-device",
        )

        result = await async_get_config_entry_diagnostics(hass, entry)
        coord_info = result["runtime"]["coordinator"]

        assert "pys7_metrics" in coord_info
        assert coord_info["pys7_metrics"]["total_operations"] == 600
        assert coord_info["pys7_metrics"]["success_rate"] == 98.67

    @pytest.mark.asyncio
    async def test_diagnostics_no_metrics_when_empty(self):
        from custom_components.s7plc.diagnostics import (
            async_get_config_entry_diagnostics,
        )

        hass = MagicMock()

        mock_coordinator = MagicMock()
        mock_coordinator.is_connected.return_value = True
        mock_coordinator.last_update_success = True
        mock_coordinator.update_interval = None
        mock_coordinator._plans_batch = []
        mock_coordinator._plans_str = []
        mock_coordinator._items = {}
        mock_coordinator.data = {}
        mock_coordinator.pys7_metrics_dict = {}

        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.title = "Test PLC"
        entry.data = {}
        entry.options = {}

        @dataclass
        class _RT:
            coordinator: object
            name: str
            host: str
            device_id: str

        entry.runtime_data = _RT(
            coordinator=mock_coordinator,
            name="Test PLC",
            host="192.168.1.1",
            device_id="test-device",
        )

        result = await async_get_config_entry_diagnostics(hass, entry)
        coord_info = result["runtime"]["coordinator"]

        # Metrics section not present when dict is empty
        assert "pys7_metrics" not in coord_info


# ---------------------------------------------------------------------------
# helpers – build_expected_unique_ids includes metrics IDs
# ---------------------------------------------------------------------------


class TestHelpersMetricsUniqueIds:
    """Tests for metrics unique IDs in helpers."""

    def test_build_expected_unique_ids_includes_metrics(self):
        from custom_components.s7plc.helpers import build_expected_unique_ids

        ids = build_expected_unique_ids("dev1", {}, data={"enable_metrics": True})
        for defn in METRICS_DEFINITIONS:
            assert f"dev1:metrics:{defn.key}" in ids

    def test_build_expected_unique_ids_includes_connection(self):
        from custom_components.s7plc.helpers import build_expected_unique_ids

        ids = build_expected_unique_ids("dev1", {})
        assert "dev1:connection" in ids

    def test_build_expected_unique_ids_excludes_metrics_when_disabled(self):
        from custom_components.s7plc.helpers import build_expected_unique_ids

        ids = build_expected_unique_ids("dev1", {}, data={"enable_metrics": False})
        for defn in METRICS_DEFINITIONS:
            assert f"dev1:metrics:{defn.key}" not in ids

    def test_build_expected_unique_ids_excludes_metrics_no_data(self):
        from custom_components.s7plc.helpers import build_expected_unique_ids

        ids = build_expected_unique_ids("dev1", {})
        for defn in METRICS_DEFINITIONS:
            assert f"dev1:metrics:{defn.key}" not in ids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_defn(key: str) -> MetricDefinition:
    """Find a MetricDefinition by key."""
    for defn in METRICS_DEFINITIONS:
        if defn.key == key:
            return defn
    raise KeyError(f"No MetricDefinition with key '{key}'")

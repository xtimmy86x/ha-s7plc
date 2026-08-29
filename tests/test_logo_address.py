"""Independent boundary tests for official Siemens LOGO! profiles."""

import pytest

from custom_components.s7plc.logo_address import (
    get_logo_profile,
    is_logo_address_candidate,
    logo_profile_payload,
    logo_to_s7_address,
    parse_logo_address,
    s7_to_logo_address,
)

PROFILES = {
    "logo_0ba7": {
        "I": (24, "DB1,X923.0", "DB1,X925.7"),
        "AI": (8, "DB1,INT926", "DB1,INT940"),
        "Q": (16, "DB1,X942.0", "DB1,X943.7"),
        "AQ": (2, "DB1,INT944", "DB1,INT946"),
        "M": (27, "DB1,X948.0", "DB1,X951.2"),
        "AM": (16, "DB1,INT952", "DB1,INT982"),
    },
    "logo_0ba8": {
        "I": (24, "DB1,X1024.0", "DB1,X1026.7"),
        "AI": (8, "DB1,INT1032", "DB1,INT1046"),
        "Q": (20, "DB1,X1064.0", "DB1,X1066.3"),
        "AQ": (8, "DB1,INT1072", "DB1,INT1086"),
        "M": (64, "DB1,X1104.0", "DB1,X1111.7"),
        "AM": (64, "DB1,INT1118", "DB1,INT1244"),
        "NI": (64, "DB1,X1246.0", "DB1,X1253.7"),
        "NAI": (32, "DB1,INT1262", "DB1,INT1324"),
        "NQ": (64, "DB1,X1390.0", "DB1,X1397.7"),
        "NAQ": (32, "DB1,INT1406", "DB1,INT1468"),
    },
    "logo_9": {
        "I": (64, "DB1,X6024.0", "DB1,X6031.7"),
        "AI": (16, "DB1,INT6040", "DB1,INT6070"),
        "Q": (60, "DB1,X6104.0", "DB1,X6111.3"),
        "AQ": (16, "DB1,INT6120", "DB1,INT6150"),
        "M": (128, "DB1,X6184.0", "DB1,X6199.7"),
        "AM": (128, "DB1,INT6216", "DB1,INT6470"),
        "FAM": (32, "DB1,REAL6728", "DB1,REAL6852"),
        "NI": (512, "DB1,X6984.0", "DB1,X7047.7"),
        "NAI": (128, "DB1,INT7112", "DB1,INT7366"),
        "NQ": (480, "DB1,X7624.0", "DB1,X7683.7"),
        "NAQ": (128, "DB1,INT7752", "DB1,INT8006"),
        "NFAI": (32, "DB1,INT8264", "DB1,INT8326"),
        "NFAQ": (32, "DB1,INT8392", "DB1,INT8454"),
    },
}


@pytest.mark.parametrize(
    ("family", "area", "last", "first_address", "last_address"),
    [
        (family, area, *values)
        for family, areas in PROFILES.items()
        for area, values in areas.items()
    ],
)
def test_every_area_first_last_rejected_successor_and_reverse(
    family, area, last, first_address, last_address
):
    assert logo_to_s7_address(f"{area}1", family) == first_address
    assert logo_to_s7_address(f"{area}{last}", family) == last_address
    assert s7_to_logo_address(first_address, family) == f"{area}1"
    assert s7_to_logo_address(last_address, family) == f"{area}{last}"
    with pytest.raises(ValueError, match="address_out_of_range"):
        logo_to_s7_address(f"{area}{last + 1}", family)


@pytest.mark.parametrize("family", PROFILES)
def test_undocumented_area_is_rejected(family):
    unavailable = (
        "NI" if family == "logo_0ba7" else "FAM" if family == "logo_0ba8" else "XYZ"
    )
    with pytest.raises(
        ValueError, match="address_not_convertible|invalid_logo_address"
    ):
        parse_logo_address(f"{unavailable}1", family)


def test_logo_9_is_not_concatenated_with_0ba8():
    assert get_logo_profile("logo_9").documented
    assert logo_to_s7_address("I1", "logo_9") == "DB1,X6024.0"
    assert s7_to_logo_address("DB1,X1024.0", "logo_9") is None


@pytest.mark.parametrize("value", ["AI9", "I25", "Q61", "M0", "NAI129"])
def test_logo_candidate_recognizes_invalid_or_out_of_range_symbols(value):
    assert is_logo_address_candidate(value, "logo_0ba8")


@pytest.mark.parametrize("value", ["DB1,INT200", "DB1,X100.0", "I0.0", "Q1.3", "M10.2"])
def test_explicit_s7_is_not_a_logo_candidate(value):
    assert not is_logo_address_candidate(value, "logo_0ba8")


@pytest.mark.parametrize("value", ["IB10", "QW8", "MD72", "XYZ1"])
def test_logo_candidate_requires_a_prefix_from_the_selected_profile(value):
    assert not is_logo_address_candidate(value, "logo_0ba8")


def test_manual_vm_bounds_and_reserved_reverse_mapping():
    assert logo_to_s7_address("VB850", "logo_9") == "DB1,BYTE850"
    with pytest.raises(ValueError, match="address_out_of_range"):
        logo_to_s7_address("VW850", "logo_9")
    assert s7_to_logo_address("DB1,X1027.0", "logo_0ba8") is None


@pytest.mark.parametrize(
    ("symbol", "canonical"),
    [
        ("V0.0", "DB1,X0.0"),
        ("V850.7", "DB1,X850.7"),
        ("VB0", "DB1,BYTE0"),
        ("VB850", "DB1,BYTE850"),
        ("VW0", "DB1,WORD0"),
        ("VW849", "DB1,WORD849"),
        ("VD0", "DB1,DWORD0"),
        ("VD847", "DB1,DWORD847"),
    ],
)
def test_original_vm_boundaries_convert_in_both_directions(symbol, canonical):
    assert logo_to_s7_address(symbol, "logo_0ba8") == canonical
    assert s7_to_logo_address(canonical, "logo_0ba8") == symbol


@pytest.mark.parametrize("symbol", ["V0", "V0.8", "VB0.0", "VW850", "VD848", "VB-1"])
def test_original_vm_invalid_values_are_rejected(symbol):
    with pytest.raises(ValueError, match="invalid_logo_address|address_out_of_range"):
        logo_to_s7_address(symbol, "logo_0ba8")


@pytest.mark.parametrize("value", ["V0.0", "VB0", "VW10", "VD20", "V0.8", "VW850"])
def test_original_vm_syntax_is_a_logo_candidate_even_when_out_of_range(value):
    assert is_logo_address_candidate(value, "logo_0ba8")


def test_vm_payload_is_separate_and_uses_zero_based_width_aware_limits():
    payload = logo_profile_payload("logo_0ba8")

    assert [
        (area["name"], area["first"], area["last"], area["data_type"], area["width"])
        for area in payload["vm_areas"]
    ] == [
        ("V", 0, 850, "X", 1),
        ("VB", 0, 850, "BYTE", 1),
        ("VW", 0, 849, "WORD", 2),
        ("VD", 0, 847, "DWORD", 4),
    ]
    assert payload["vm_areas"][0]["bit_min"] == 0
    assert payload["vm_areas"][0]["bit_max"] == 7

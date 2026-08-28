"""Explicit checks for the Siemens LOGO! Parameter VM Mapping tables."""

import pytest

from custom_components.s7plc.logo_address import (
    get_logo_profile,
    logo_to_s7_address,
    parse_logo_address,
    s7_to_logo_address,
)


@pytest.mark.parametrize(
    ("family", "logo", "canonical"),
    [
        ("logo_0ba7", "I1", "DB1,X923.0"),
        ("logo_0ba7", "I12", "DB1,X924.3"),
        ("logo_0ba7", "I24", "DB1,X925.7"),
        ("logo_0ba7", "Q1", "DB1,X942.0"),
        ("logo_0ba7", "Q16", "DB1,X943.7"),
        ("logo_0ba7", "M27", "DB1,X951.2"),
        ("logo_0ba7", "AI1", "DB1,INT926"),
        ("logo_0ba7", "AI8", "DB1,INT940"),
        ("logo_0ba7", "AQ2", "DB1,INT946"),
        ("logo_0ba7", "AM6", "DB1,INT962"),
        ("logo_0ba7", "AM16", "DB1,INT982"),
        ("logo_0ba8", "I1", "DB1,X1024.0"),
        ("logo_0ba8", "I64", "DB1,X1031.7"),
        ("logo_0ba8", "Q64", "DB1,X1071.7"),
        ("logo_0ba8", "M112", "DB1,X1117.7"),
        ("logo_0ba8", "AI16", "DB1,INT1062"),
        ("logo_0ba8", "AQ16", "DB1,INT1102"),
        ("logo_0ba8", "AM64", "DB1,INT1244"),
        ("logo_0ba8", "NI128", "DB1,X1261.7"),
        ("logo_0ba8", "NAI64", "DB1,INT1388"),
        ("logo_0ba8", "NQ128", "DB1,X1405.7"),
        ("logo_0ba8", "NAQ32", "DB1,INT1468"),
        ("logo_9", "I64", "DB1,X1031.7"),
        ("logo_9", "I65", "DB1,X6024.0"),
        ("logo_9", "I128", "DB1,X6031.7"),
        ("logo_9", "AI17", "DB1,INT6040"),
        ("logo_9", "AI32", "DB1,INT6070"),
        ("logo_9", "Q65", "DB1,X6104.0"),
        ("logo_9", "Q118", "DB1,X6110.5"),
        ("logo_9", "AQ32", "DB1,INT6150"),
        ("logo_9", "M113", "DB1,X6184.0"),
        ("logo_9", "M240", "DB1,X6199.7"),
        ("logo_9", "AM65", "DB1,INT6216"),
        ("logo_9", "AM192", "DB1,INT6470"),
        ("logo_9", "FAM1", "DB1,REAL6728"),
        ("logo_9", "FAM32", "DB1,REAL6852"),
        ("logo_9", "NI129", "DB1,X6984.0"),
        ("logo_9", "NI640", "DB1,X7047.7"),
        ("logo_9", "NAI65", "DB1,INT7112"),
        ("logo_9", "NAI192", "DB1,INT7366"),
        ("logo_9", "NQ129", "DB1,X7624.0"),
        ("logo_9", "NQ608", "DB1,X7683.7"),
        ("logo_9", "NAQ33", "DB1,INT7752"),
        ("logo_9", "NAQ160", "DB1,INT8006"),
        ("logo_9", "NFAI32", "DB1,INT8326"),
        ("logo_9", "NFAQ32", "DB1,INT8454"),
    ],
)
def test_explicit_fixed_mappings(family, logo, canonical):
    assert logo_to_s7_address(logo, family) == canonical
    assert s7_to_logo_address(canonical, family) == logo


def test_case_insensitive_and_vm_manual():
    assert logo_to_s7_address("ai1", "logo_0ba7") == "DB1,INT926"
    assert logo_to_s7_address("v10.7", "logo_0ba7") == "DB1,X10.7"
    assert logo_to_s7_address("VB10", "logo_0ba7") == "DB1,BYTE10"
    assert logo_to_s7_address("vw10", "logo_0ba7") == "DB1,WORD10"
    assert logo_to_s7_address("VD10", "logo_0ba7") == "DB1,DWORD10"


@pytest.mark.parametrize(
    "address", ["I0", "I-1", "I25", "AI9", "NI1", "", "I", "AI1.0", "wat"]
)
def test_invalid_or_out_of_range(address):
    with pytest.raises(ValueError):
        logo_to_s7_address(address, "logo_0ba7")


def test_reserved_and_incompatible_addresses_do_not_reverse():
    assert s7_to_logo_address("DB1,X927.0", "logo_0ba7") is None
    assert s7_to_logo_address("DB1,WORD926", "logo_0ba7") is None
    assert s7_to_logo_address("DB1,INT928", "logo_0ba7") == "AI2"


def test_logo_9_has_its_own_discontinuous_profile():
    assert get_logo_profile("logo_9").documented
    assert logo_to_s7_address("I64", "logo_9") == "DB1,X1031.7"
    assert logo_to_s7_address("I65", "logo_9") == "DB1,X6024.0"
    with pytest.raises(ValueError, match="out_of_range"):
        logo_to_s7_address("I65", "logo_0ba8")
    with pytest.raises(ValueError, match="out_of_range"):
        logo_to_s7_address("Q119", "logo_9")


def test_manual_vm_range_is_the_documented_parameter_range():
    assert logo_to_s7_address("VB850", "logo_9") == "DB1,BYTE850"
    with pytest.raises(ValueError, match="out_of_range"):
        logo_to_s7_address("VW850", "logo_9")

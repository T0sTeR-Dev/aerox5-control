"""Verify all TrueMove Air facts offline, plus preset validation and framing."""

import json
from pathlib import Path

import pytest

from aerox5_control.protocol import truemove_air
from aerox5_control.protocol.aerox5 import (
    DPI_COMMAND_WIRED,
    DPI_COMMAND_WIRELESS,
    WIRELESS_COMMAND_FLAG,
    encode_dpi_presets,
)
from aerox5_control.protocol.truemove_air import (
    TRUEMOVE_AIR_DPI_VALUES,
    encode_dpi_value,
)
from aerox5_control.transport.hidapi_backend import encode_output_report


def test_complete_mapping_matches_all_180_public_reference_values():
    fixture_path = Path(__file__).parent / "fixtures" / "truemove_air.json"
    fixture = json.loads(fixture_path.read_text())
    pairs = fixture["dpi_and_encoded_hex"]
    expected = {dpi: int(encoded, 16) for dpi, encoded in pairs}
    assert len(pairs) == len(expected) == 180
    assert set(expected) == set(range(100, 18001, 100))
    assert len(set(expected.values())) == 180
    assert all(type(code) is int and 0 <= code <= 255 for code in expected.values())
    assert dict(TRUEMOVE_AIR_DPI_VALUES) == expected
    for dpi, encoded in expected.items():
        assert encode_dpi_value(dpi) == encoded
        assert encode_dpi_presets([dpi]) == bytes((0x6D, 1, 0, encoded))


@pytest.mark.parametrize(
    ("dpi", "encoded"),
    [(100, 0x00), (200, 0x02), (800, 0x09), (1600, 0x12), (3200, 0x26), (18000, 0xD6)],
)
def test_known_encoding_anchors(dpi, encoded):
    assert encode_dpi_value(dpi) == encoded


def test_wireless_sensitivity_command():
    assert DPI_COMMAND_WIRED == 0x2D
    assert WIRELESS_COMMAND_FLAG == 0x40
    assert DPI_COMMAND_WIRED | WIRELESS_COMMAND_FLAG == 0x6D
    assert DPI_COMMAND_WIRELESS == 0x6D


@pytest.mark.parametrize(
    ("presets", "payload", "buffer"),
    [
        ([800], b"\x6d\x01\x00\x09", b"\x00\x6d\x01\x00\x09"),
        ([800, 1600], b"\x6d\x02\x00\x09\x12", b"\x00\x6d\x02\x00\x09\x12"),
        (
            [400, 800, 1200, 2400, 3200],
            b"\x6d\x05\x00\x04\x09\x0d\x1b\x26",
            b"\x00\x6d\x05\x00\x04\x09\x0d\x1b\x26",
        ),
    ],
)
def test_exact_protocol_and_hidapi_packets(presets, payload, buffer):
    original = presets.copy()
    assert encode_dpi_presets(presets) == payload
    assert encode_output_report(encode_dpi_presets(presets)) == buffer
    assert presets == original


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5])
def test_preset_count_and_fixed_selected_index_preserve_duplicates(count):
    assert (
        encode_dpi_presets([800] * count) == bytes((0x6D, count, 0)) + b"\x09" * count
    )


def test_presets_are_not_sorted():
    assert encode_dpi_presets((1600, 800)) == b"\x6d\x02\x00\x12\x09"


@pytest.mark.parametrize(
    "presets",
    [
        [],
        [800] * 6,
        [0],
        [50],
        [850],
        [18100],
        [-100],
        [100.0],
        [True],
        [None],
        ["800"],
        [800, 850],
        [[800]],
        None,
        800,
        "800",
        b"800",
        {800},
        {800: 1},
    ],
)
def test_invalid_counts_values_and_types_are_rejected(presets):
    with pytest.raises(ValueError):
        encode_dpi_presets(presets)


def test_unknown_mapping_value_has_no_arithmetic_fallback(monkeypatch):
    known = dict(TRUEMOVE_AIR_DPI_VALUES)
    del known[800]
    monkeypatch.setattr(truemove_air, "TRUEMOVE_AIR_DPI_VALUES", known)
    with pytest.raises(ValueError, match="verified"):
        encode_dpi_presets([800])


def test_mapping_cannot_be_mutated():
    with pytest.raises(TypeError):
        TRUEMOVE_AIR_DPI_VALUES[800] = 8

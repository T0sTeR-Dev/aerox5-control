"""Pure battery encoding/decoding; these tests perform no I/O."""

import pytest

from aerox5_control.protocol.aerox5 import (
    BATTERY_QUERY_WIRED,
    BATTERY_QUERY_WIRELESS,
    WIRELESS_COMMAND_FLAG,
    BatteryStatus,
    battery_query_payload,
    decode_battery_response,
)
from aerox5_control.transport.hidapi_backend import encode_output_report


def test_wireless_command_and_exact_hidapi_buffer():
    assert BATTERY_QUERY_WIRED == 0x92
    assert WIRELESS_COMMAND_FLAG == 0x40
    assert BATTERY_QUERY_WIRED | WIRELESS_COMMAND_FLAG == 0xD2
    assert BATTERY_QUERY_WIRELESS == 0xD2
    assert battery_query_payload() == b"\xd2"
    # Exactly two bytes, not a 64/65-byte padded buffer or a feature report.
    assert encode_output_report(battery_query_payload()) == b"\x00\xd2"


@pytest.mark.parametrize(
    ("raw", "level", "charging"),
    [
        (16, 75, False),
        (0x90, 75, True),
        (1, 0, False),
        (0x81, 0, True),
        (21, 100, False),
        (0x95, 100, True),
    ],
)
def test_valid_levels_charging_and_boundaries(raw, level, charging):
    status = decode_battery_response(bytes((0xD2, raw)))
    assert status == BatteryStatus(level=level, charging=charging)
    assert status.available


@pytest.mark.parametrize("raw", [0, 22, 127, 0x80, 0x96, 0xFF])
def test_impossible_values_are_unavailable_not_clamped(raw):
    status = decode_battery_response(bytes((0xD2, raw)))
    assert not status.available
    assert status.level is None
    assert status.charging is None
    assert "invalid percentage" in status.reason


@pytest.mark.parametrize(
    "response",
    [
        b"",
        b"\xd2",
        b"\xd2\x10\x00",
        b"\x00\xd2\x10",
        b"\x00\x10",
        b"\x92\x10",
        b"\x40\xff",
        b"\xd2\x10" + bytes(61),
        b"\xd2\x10" + bytes(63),
        b"\xd2\x10\x01" + bytes(61),
        None,
        [0xD2, 16],
    ],
)
def test_empty_malformed_unrelated_and_off_responses(response):
    status = decode_battery_response(response)
    assert status.level is None
    assert status.charging is None
    assert status.reason


def test_oversized_battery_response_is_rejected():
    status = decode_battery_response(b"\xd2\x90" + bytes(62))
    assert not status.available
    assert "unexpected length" in status.reason


def test_padded_battery_response_is_rejected():
    status = decode_battery_response(b"\x40\xff" + bytes(62))
    assert not status.available
    assert "unexpected length" in status.reason


def test_wired_command_and_exact_hidapi_buffer():
    assert battery_query_payload(wireless=False) == b"\x92"
    assert encode_output_report(battery_query_payload(wireless=False)) == b"\x00\x92"


@pytest.mark.parametrize(
    ("raw", "level", "charging"),
    [
        (16, 75, False),
        (0x90, 75, True),
        (1, 0, False),
        (0x81, 0, True),
        (21, 100, False),
        (0x95, 100, True),
    ],
)
def test_valid_wired_levels_charging_and_boundaries(raw, level, charging):
    status = decode_battery_response(
        bytes((0x92, raw)),
        wireless=False,
    )
    assert status == BatteryStatus(level=level, charging=charging)
    assert status.available


def test_battery_response_header_must_match_connection_mode():
    wired = decode_battery_response(
        b"\x92\x10",
        wireless=False,
    )
    assert wired == BatteryStatus(level=75, charging=False)

    wireless = decode_battery_response(
        b"\xd2\x10",
        wireless=True,
    )
    assert wireless == BatteryStatus(level=75, charging=False)

    wrong_for_wired = decode_battery_response(
        b"\xd2\x10",
        wireless=False,
    )
    assert not wrong_for_wired.available
    assert "header" in wrong_for_wired.reason

    wrong_for_wireless = decode_battery_response(
        b"\x92\x10",
        wireless=True,
    )
    assert not wrong_for_wireless.available
    assert "header" in wrong_for_wireless.reason

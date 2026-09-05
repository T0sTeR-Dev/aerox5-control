"""Polling encoding is pure; all buffers here remain in memory."""

import pytest

from aerox5_control.protocol.aerox5 import (
    POLLING_RATE_COMMAND_WIRED,
    POLLING_RATE_COMMAND_WIRELESS,
    WIRELESS_COMMAND_FLAG,
    encode_polling_rate,
)
from aerox5_control.transport.hidapi_backend import encode_output_report


def test_wireless_polling_command_transformation():
    assert POLLING_RATE_COMMAND_WIRED == 0x2B
    assert WIRELESS_COMMAND_FLAG == 0x40
    assert POLLING_RATE_COMMAND_WIRED | WIRELESS_COMMAND_FLAG == 0x6B
    assert POLLING_RATE_COMMAND_WIRELESS == 0x6B


@pytest.mark.parametrize(
    ("rate", "payload", "hidapi_buffer"),
    [
        (1000, b"\x6b\x00", b"\x00\x6b\x00"),
        (500, b"\x6b\x01", b"\x00\x6b\x01"),
        (250, b"\x6b\x02", b"\x00\x6b\x02"),
        (125, b"\x6b\x03", b"\x00\x6b\x03"),
    ],
)
def test_exact_payload_and_unnumbered_buffer_without_padding(
    rate, payload, hidapi_buffer
):
    assert encode_polling_rate(rate) == payload
    assert encode_output_report(encode_polling_rate(rate)) == hidapi_buffer


@pytest.mark.parametrize(
    "rate", [0, 100, 144, 2000, -125, True, False, None, "1000", 1000.0, [], {}]
)
def test_invalid_rates_and_types_are_rejected(rate):
    with pytest.raises(ValueError, match="125, 250, 500, or 1000 Hz"):
        encode_polling_rate(rate)

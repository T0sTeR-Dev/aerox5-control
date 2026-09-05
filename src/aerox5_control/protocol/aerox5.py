"""Documented Aerox 5 battery, active polling-rate, and DPI preset encoding."""

from collections.abc import Sequence
from dataclasses import dataclass

from aerox5_control.protocol.truemove_air import encode_dpi_value

BATTERY_QUERY_WIRED = 0x92
WIRELESS_COMMAND_FLAG = 0x40
BATTERY_QUERY_WIRELESS = BATTERY_QUERY_WIRED | WIRELESS_COMMAND_FLAG
BATTERY_RESPONSE_SIZE = 2
CONFIGURATION_INPUT_REPORT_SIZE = 64
POLLING_RATE_COMMAND_WIRED = 0x2B
POLLING_RATE_COMMAND_WIRELESS = POLLING_RATE_COMMAND_WIRED | WIRELESS_COMMAND_FLAG
_POLLING_RATE_VALUES = {1000: 0x00, 500: 0x01, 250: 0x02, 125: 0x03}
SUPPORTED_POLLING_RATES = tuple(sorted(_POLLING_RATE_VALUES))
DPI_COMMAND_WIRED = 0x2D
DPI_COMMAND_WIRELESS = DPI_COMMAND_WIRED | WIRELESS_COMMAND_FLAG
MAX_DPI_PRESETS = 5
DPI_SELECTED_PRESET = 0


def validate_dpi_presets(presets: Sequence[int]) -> tuple[int, ...]:
    """Validate and snapshot an ordered list before any hardware access."""
    if (
        not isinstance(presets, Sequence)
        or isinstance(presets, (str, bytes, bytearray))
        or not 1 <= len(presets) <= MAX_DPI_PRESETS
    ):
        raise ValueError("Provide between 1 and 5 integer DPI presets")
    values = tuple(presets)
    if not 1 <= len(values) <= MAX_DPI_PRESETS:
        raise ValueError("Provide between 1 and 5 integer DPI presets")
    for value in values:
        encode_dpi_value(value)
    return values


def encode_dpi_presets(presets: Sequence[int]) -> bytes:
    """Encode command/count/index/values; select index 0 with no ID prefix."""
    values = validate_dpi_presets(presets)
    return bytes((DPI_COMMAND_WIRELESS, len(values), DPI_SELECTED_PRESET)) + bytes(
        encode_dpi_value(value) for value in values
    )


def encode_polling_rate(rate_hz: int) -> bytes:
    """Encode only the wireless command/value; no HIDAPI prefix or padding."""
    if type(rate_hz) is not int or rate_hz not in _POLLING_RATE_VALUES:
        raise ValueError("Polling rate must be one of 125, 250, 500, or 1000 Hz")
    return bytes((POLLING_RATE_COMMAND_WIRELESS, _POLLING_RATE_VALUES[rate_hz]))


@dataclass(frozen=True, slots=True)
class BatteryStatus:
    """Unavailable data has neither a level nor a charging value."""

    level: int | None = None
    charging: bool | None = None
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.level is not None

    @classmethod
    def unavailable(cls, reason: str) -> "BatteryStatus":
        return cls(reason=reason)


def battery_query_payload(*, wireless: bool = True) -> bytes:
    """Encode the battery command without the synthetic HIDAPI report-ID prefix."""
    command = BATTERY_QUERY_WIRELESS if wireless else BATTERY_QUERY_WIRED
    return bytes((command,))


def decode_battery_response(
    response: bytes, *, wireless: bool = True
) -> BatteryStatus:
    """Decode a two-byte wired or wireless battery response; never clamp."""
    if not isinstance(response, bytes):
        return BatteryStatus.unavailable("Malformed battery response type")
    if not response:
        return BatteryStatus.unavailable("No battery response; mouse may be asleep/off")
    if len(response) != BATTERY_RESPONSE_SIZE:
        return BatteryStatus.unavailable("Battery response has an unexpected length")
    if response[:2] == b"\x40\xff":
        return BatteryStatus.unavailable("Mouse is unavailable/asleep/off")
    expected_command = (
    BATTERY_QUERY_WIRELESS if wireless else BATTERY_QUERY_WIRED
)
    if response[0] != expected_command:
        return BatteryStatus.unavailable("Unexpected battery response header")
    value = response[1]
    level = ((value & 0x7F) - 1) * 5
    if not 0 <= level <= 100:
        return BatteryStatus.unavailable(
            "Battery response encodes an invalid percentage"
        )
    return BatteryStatus(level=level, charging=bool(value & 0x80))

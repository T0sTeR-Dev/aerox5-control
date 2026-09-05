"""The documented Aerox 5 battery query only; no setting commands."""

from dataclasses import dataclass

BATTERY_QUERY_WIRED = 0x92
WIRELESS_COMMAND_FLAG = 0x40
BATTERY_QUERY_WIRELESS = BATTERY_QUERY_WIRED | WIRELESS_COMMAND_FLAG
BATTERY_RESPONSE_SIZE = 2
CONFIGURATION_INPUT_REPORT_SIZE = 64


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


def battery_query_payload() -> bytes:
    """One command byte; the generic HID adapter adds the synthetic ID byte."""
    return bytes((BATTERY_QUERY_WIRELESS,))


def decode_battery_response(response: bytes) -> BatteryStatus:
    """Decode the second byte of a D2 reply; reject invalid levels, never clamp.

    Accept the meaningful two bytes, or a full 64-byte input report only when
    every trailing byte is zero. No synthetic HIDAPI prefix is removed on input.
    """
    if not isinstance(response, bytes):
        return BatteryStatus.unavailable("Malformed battery response type")
    if not response:
        return BatteryStatus.unavailable("No battery response; mouse may be asleep/off")
    if len(response) not in (BATTERY_RESPONSE_SIZE, CONFIGURATION_INPUT_REPORT_SIZE):
        return BatteryStatus.unavailable("Battery response has an unexpected length")
    if any(response[BATTERY_RESPONSE_SIZE:]):
        return BatteryStatus.unavailable(
            "Battery response has unexpected trailing data"
        )
    if response[:2] == b"\x40\xff":
        return BatteryStatus.unavailable("Mouse is unavailable/asleep/off")
    if response[0] != BATTERY_QUERY_WIRELESS:
        return BatteryStatus.unavailable("Unexpected battery response header")
    value = response[1]
    level = ((value & 0x7F) - 1) * 5
    if not 0 <= level <= 100:
        return BatteryStatus.unavailable(
            "Battery response encodes an invalid percentage"
        )
    return BatteryStatus(level=level, charging=bool(value & 0x80))

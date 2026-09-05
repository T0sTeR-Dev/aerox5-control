"""Discovery, receiver status, and explicit active polling/DPI requests."""

from collections.abc import Sequence

from aerox5_control.devices.aerox5 import (
    Aerox5Interface,
    Aerox5Receiver,
    Aerox5Status,
    DpiPresetsResult,
    PollingRateResult,
    discover_aerox5,
)
from aerox5_control.protocol.aerox5 import BatteryStatus
from aerox5_control.transport.hidapi_backend import HidApiTransport
from aerox5_control.transport.interfaces import HidDiscovery, HidTransport


def inspect_interfaces(
    transport: HidDiscovery | None = None,
) -> tuple[Aerox5Interface, ...]:
    """Discover interfaces without opening them or querying device state."""
    if transport is None:
        transport = HidApiTransport()
    return discover_aerox5(transport)


def get_battery(transport: HidTransport | None = None) -> BatteryStatus:
    if transport is None:
        transport = HidApiTransport()
    return Aerox5Receiver(transport).get_battery()


def get_status(transport: HidTransport | None = None) -> Aerox5Status:
    """Combine cached identity and one documented battery/charging query."""
    if transport is None:
        transport = HidApiTransport()
    return Aerox5Receiver(transport).get_status()


def set_polling_rate(
    rate_hz: int, transport: HidTransport | None = None
) -> PollingRateResult:
    """Send one validated polling request, without querying or saving settings."""
    if transport is None:
        transport = HidApiTransport()
    return Aerox5Receiver(transport).set_polling_rate(rate_hz)


def set_dpi_presets(
    presets: Sequence[int], transport: HidTransport | None = None
) -> DpiPresetsResult:
    """Validate and set DPI presets once, without saving or changing polling."""
    if transport is None:
        transport = HidApiTransport()
    return Aerox5Receiver(transport).set_dpi_presets(presets)

"""Discovery and explicitly requested battery queries."""

from aerox5_control.devices.aerox5 import (
    Aerox5Interface,
    Aerox5Receiver,
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

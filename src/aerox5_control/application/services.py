"""Read-only application services."""

from aerox5_control.devices.aerox5 import Aerox5Interface, discover_aerox5
from aerox5_control.transport.hidapi_backend import HidApiTransport
from aerox5_control.transport.interfaces import HidDiscovery


def inspect_interfaces(
    transport: HidDiscovery | None = None,
) -> tuple[Aerox5Interface, ...]:
    """Discover interfaces without opening them or querying device state."""
    if transport is None:
        transport = HidApiTransport()
    return discover_aerox5(transport)

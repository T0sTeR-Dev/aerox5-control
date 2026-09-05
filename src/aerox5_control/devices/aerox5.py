"""Identify Aerox 5 Wireless interfaces using known standard USB IDs."""

from dataclasses import dataclass

from aerox5_control.transport.interfaces import HidDiscovery, HidInterface

STEELSERIES_VENDOR_ID = 0x1038
AEROX5_RECEIVER_PRODUCT_ID = 0x1852
AEROX5_WIRED_PRODUCT_ID = 0x1854

_CONNECTIONS = {
    AEROX5_RECEIVER_PRODUCT_ID: "2.4 GHz",
    AEROX5_WIRED_PRODUCT_ID: "wired",
}


@dataclass(frozen=True, slots=True)
class Aerox5Interface:
    """A matching interface, without assuming a configuration capability."""

    hid: HidInterface
    connection: str


def discover_aerox5(transport: HidDiscovery) -> tuple[Aerox5Interface, ...]:
    """Retain all matching entries, including interfaces sharing HID paths."""
    return tuple(
        Aerox5Interface(hid=interface, connection=_CONNECTIONS[interface.product_id])
        for interface in transport.enumerate(STEELSERIES_VENDOR_ID, 0)
        if interface.vendor_id == STEELSERIES_VENDOR_ID
        and interface.product_id in _CONNECTIONS
    )

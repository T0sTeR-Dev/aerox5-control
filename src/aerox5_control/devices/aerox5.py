"""Identify Aerox 5 Wireless interfaces using known standard USB IDs."""

from dataclasses import dataclass

from aerox5_control.protocol.aerox5 import (
    CONFIGURATION_INPUT_REPORT_SIZE,
    BatteryStatus,
    battery_query_payload,
    decode_battery_response,
)
from aerox5_control.transport.hidapi_backend import HidError
from aerox5_control.transport.interfaces import HidDiscovery, HidInterface, HidTransport

STEELSERIES_VENDOR_ID = 0x1038
AEROX5_RECEIVER_PRODUCT_ID = 0x1852
AEROX5_WIRED_PRODUCT_ID = 0x1854

_CONNECTIONS = {
    AEROX5_RECEIVER_PRODUCT_ID: "2.4 GHz",
    AEROX5_WIRED_PRODUCT_ID: "wired",
}

AEROX5_USB_IDS = frozenset((STEELSERIES_VENDOR_ID, pid) for pid in _CONNECTIONS)

RECEIVER_CONFIGURATION_INTERFACE = 3
RECEIVER_CONFIGURATION_USAGE_PAGE = 0xFFC0
RECEIVER_CONFIGURATION_USAGE = 0x0001
BATTERY_READ_TIMEOUT_MS = 1000


@dataclass(frozen=True, slots=True)
class Aerox5Interface:
    """A matching interface, without assuming a configuration capability."""

    hid: HidInterface
    connection: str


def discover_aerox5(transport: HidDiscovery) -> tuple[Aerox5Interface, ...]:
    """Retain all matching entries, including interfaces sharing HID paths."""
    return tuple(
        Aerox5Interface(hid=interface, connection=connection)
        for product_id, connection in _CONNECTIONS.items()
        for interface in transport.enumerate(STEELSERIES_VENDOR_ID, product_id)
        if interface.vendor_id == STEELSERIES_VENDOR_ID
        and interface.product_id == product_id
    )


def _is_receiver_configuration(interface: HidInterface) -> bool:
    return (
        interface.vendor_id == STEELSERIES_VENDOR_ID
        and interface.product_id == AEROX5_RECEIVER_PRODUCT_ID
        and interface.interface_number == RECEIVER_CONFIGURATION_INTERFACE
        and interface.usage_page == RECEIVER_CONFIGURATION_USAGE_PAGE
        and interface.usage == RECEIVER_CONFIGURATION_USAGE
    )


class Aerox5Receiver:
    """Query only the confirmed standard receiver configuration interface."""

    def __init__(self, transport: HidTransport) -> None:
        self._transport = transport

    def get_battery(self) -> BatteryStatus:
        """One query and one bounded read on the same handle; never retry."""
        try:
            entries = self._transport.enumerate(
                STEELSERIES_VENDOR_ID, AEROX5_RECEIVER_PRODUCT_ID
            )
            candidates = {
                entry.path: entry
                for entry in entries
                if _is_receiver_configuration(entry)
            }
            if not candidates:
                return BatteryStatus.unavailable(
                    "Receiver configuration interface not found"
                )
            if len(candidates) != 1:
                return BatteryStatus.unavailable(
                    "Multiple receiver configuration interfaces found"
                )
            path = next(iter(candidates))
            if any(
                entry.path == path and not _is_receiver_configuration(entry)
                for entry in entries
            ):
                return BatteryStatus.unavailable(
                    "Conflicting metadata for the selected HID path"
                )
            with self._transport.open_path(path) as connection:
                connection.write_output(battery_query_payload(), report_id=0)
                response = connection.read_input(
                    CONFIGURATION_INPUT_REPORT_SIZE, timeout_ms=BATTERY_READ_TIMEOUT_MS
                )
            return decode_battery_response(response)
        except (HidError, OSError) as error:
            return BatteryStatus.unavailable(str(error))

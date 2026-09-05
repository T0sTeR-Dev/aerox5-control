"""Identify Aerox 5 Wireless interfaces using known standard USB IDs."""

from dataclasses import dataclass

from aerox5_control.protocol.aerox5 import (
    CONFIGURATION_INPUT_REPORT_SIZE,
    BatteryStatus,
    battery_query_payload,
    decode_battery_response,
    encode_polling_rate,
)
from aerox5_control.transport.hidapi_backend import (
    HidError,
    HidOperationError,
    HidReadTimeout,
)
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
POLLING_READBACK_TIMEOUT_MS = 1000


@dataclass(frozen=True, slots=True)
class Aerox5Interface:
    """A matching interface, without assuming a configuration capability."""

    hid: HidInterface
    connection: str


@dataclass(frozen=True, slots=True)
class Aerox5Status:
    """Enumeration metadata survives a failed battery query.

    Connection describes the receiver's USB identity, not a live radio link.
    Firmware and hardware revision are not yet supported by this implementation.
    """

    interface: Aerox5Interface | None
    battery: BatteryStatus


@dataclass(frozen=True, slots=True)
class PollingRateResult:
    """Outcome of one request, not a measurement of the active polling rate.

    Readback bytes have no assigned semantics. Even a failed write may have
    reached the receiver, so write_attempted means the active rate is uncertain.
    """

    requested_rate_hz: int
    interface: Aerox5Interface | None
    write_attempted: bool
    readback: bytes | None
    error: str | None = None

    @property
    def completed(self) -> bool:
        """The write, readback, and close completed without a transport error."""
        return self.error is None and self.readback is not None


class ReceiverSelectionError(HidError):
    """No single, unambiguous receiver configuration interface was found."""


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
    """Use only the confirmed standard receiver configuration interface."""

    def __init__(self, transport: HidTransport) -> None:
        self._transport = transport

    def _configuration_interface(self) -> Aerox5Interface:
        """Share strict selection across queries and settings, without opening."""
        entries = self._transport.enumerate(
            STEELSERIES_VENDOR_ID, AEROX5_RECEIVER_PRODUCT_ID
        )
        candidates = {
            entry.path: entry for entry in entries if _is_receiver_configuration(entry)
        }
        if not candidates:
            raise ReceiverSelectionError("Receiver configuration interface not found")
        if len(candidates) != 1:
            raise ReceiverSelectionError(
                "Multiple receiver configuration interfaces found"
            )
        path = next(iter(candidates))
        if any(entry.path == path and entry != candidates[path] for entry in entries):
            raise ReceiverSelectionError(
                "Conflicting metadata for the selected HID path"
            )
        return Aerox5Interface(
            hid=candidates[path], connection=_CONNECTIONS[AEROX5_RECEIVER_PRODUCT_ID]
        )

    def get_battery(self) -> BatteryStatus:
        return self.get_status().battery

    def get_status(self) -> Aerox5Status:
        """One query and one bounded read on the same handle; never retry."""
        selected = None
        try:
            selected = self._configuration_interface()
            with self._transport.open_path(selected.hid.path) as connection:
                connection.write_output(battery_query_payload(), report_id=0)
                response = connection.read_input(
                    CONFIGURATION_INPUT_REPORT_SIZE, timeout_ms=BATTERY_READ_TIMEOUT_MS
                )
            battery = decode_battery_response(response)
        except (HidError, OSError) as error:
            battery = BatteryStatus.unavailable(str(error))
        return Aerox5Status(interface=selected, battery=battery)

    def set_polling_rate(self, rate_hz: int) -> PollingRateResult:
        """Validate before discovery, write once, read once, and never save/retry."""
        payload = encode_polling_rate(rate_hz)
        selected = None
        write_attempted = False
        readback = None
        error_message = None
        try:
            selected = self._configuration_interface()
            with self._transport.open_path(selected.hid.path) as connection:
                write_attempted = True
                connection.write_output(payload, report_id=0)
                response = connection.read_input(
                    CONFIGURATION_INPUT_REPORT_SIZE,
                    timeout_ms=POLLING_READBACK_TIMEOUT_MS,
                )
                # Enforce the same structural contract for injected transports.
                # No header, acknowledgment, or rate semantics are assigned.
                if (
                    not isinstance(response, bytes)
                    or len(response) > CONFIGURATION_INPUT_REPORT_SIZE
                ):
                    raise HidOperationError("Malformed polling readback")
                if not response:
                    raise HidReadTimeout("Polling readback timed out")
                readback = response
        except (HidError, OSError) as error:
            error_message = str(error)
        return PollingRateResult(
            requested_rate_hz=rate_hz,
            interface=selected,
            write_attempted=write_attempted,
            readback=readback,
            error=error_message,
        )

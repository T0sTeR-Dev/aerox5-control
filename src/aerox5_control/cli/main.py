"""The aerox5-control-cli command."""

import argparse
import sys
from collections.abc import Sequence

from aerox5_control.application.services import inspect_interfaces
from aerox5_control.devices.aerox5 import Aerox5Interface
from aerox5_control.transport.hidapi_backend import HidError


def _hex(value: int | None) -> str:
    return "(unavailable)" if value is None else f"0x{value:04x}"


def _text(value: str | int | None) -> str:
    return "(unavailable)" if value is None else str(value)


def format_interface(index: int, interface: Aerox5Interface) -> str:
    """Render cached enumeration metadata without any hardware access."""
    hid = interface.hid
    path = (
        hid.path.decode("utf-8", errors="backslashreplace")
        if isinstance(hid.path, bytes)
        else hid.path
    )
    return "\n".join(
        (
            f"Interface {index}: Aerox 5 Wireless ({interface.connection})",
            f"  Vendor ID: {_hex(hid.vendor_id)}",
            f"  Product ID: {_hex(hid.product_id)}",
            f"  Interface number: {_text(hid.interface_number)}",
            f"  Usage page: {_hex(hid.usage_page)}",
            f"  Usage: {_hex(hid.usage)}",
            f"  Manufacturer string: {_text(hid.manufacturer_string)}",
            f"  Product string: {_text(hid.product_string)}",
            f"  Serial number: {_text(hid.serial_number)}",
            f"  HID path: {path}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run discovery or report an error without requesting elevated access."""
    parser = argparse.ArgumentParser(
        prog="aerox5-control-cli",
        description="Read-only discovery for the SteelSeries Aerox 5 Wireless.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect", help="enumerate all matching HID interfaces")
    parser.parse_args(argv)

    try:
        interfaces = inspect_interfaces()
    except HidError as error:
        print(f"aerox5-control-cli: {error}", file=sys.stderr)
        return 1

    if not interfaces:
        print("No matching Aerox 5 Wireless HID interfaces reported by HIDAPI.")
        return 0

    print(f"Discovered {len(interfaces)} matching HID interface entries.\n")
    print(
        "\n\n".join(format_interface(i, item) for i, item in enumerate(interfaces, 1))
    )
    return 0

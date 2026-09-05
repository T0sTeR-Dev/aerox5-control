"""The aerox5-control-cli command."""

import argparse
import sys
from collections.abc import Sequence

from aerox5_control.application.hid_info import inspect_hid_descriptors
from aerox5_control.application.services import inspect_interfaces
from aerox5_control.cli.hid_info import format_candidates, format_descriptor
from aerox5_control.devices.aerox5 import Aerox5Interface
from aerox5_control.transport.hidapi_backend import HidError


def _hex(value: int | None) -> str:
    return "(unavailable)" if value is None else f"0x{value:04x}"


def _text(value: str | int | None) -> str:
    return "(unavailable)" if value is None else str(value)


def format_interface(
    index: int, interface: Aerox5Interface, *, heading: str = "Interface"
) -> str:
    """Render cached enumeration metadata without any hardware access."""
    hid = interface.hid
    path = (
        hid.path.decode("utf-8", errors="backslashreplace")
        if isinstance(hid.path, bytes)
        else hid.path
    )
    return "\n".join(
        (
            f"{heading} {index}: Aerox 5 Wireless ({interface.connection})",
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
    commands.add_parser("hid-info", help="inspect cached HID report descriptors")
    args = parser.parse_args(argv)

    try:
        if args.command == "hid-info":
            return _hid_info()
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


def _hid_info() -> int:
    inspections = inspect_hid_descriptors()
    if not inspections:
        print("No matching Aerox 5 Wireless HID interfaces reported by HIDAPI.")
        return 0
    print(
        f"Discovered {len(inspections)} distinct HID paths "
        f"({sum(len(item.entries) for item in inspections)} enumeration entries)."
    )
    print("Wire bytes include an explicit report ID byte only for numbered reports.")
    print("HIDAPI's synthetic zero-ID buffer prefix is not included.\n")
    for index, item in enumerate(inspections, 1):
        print(format_interface(index, item.entries[0], heading="HID entry"))
        print(format_descriptor(item))
        print()
    print(format_candidates(inspections))
    return 1 if any(item.error for item in inspections) else 0

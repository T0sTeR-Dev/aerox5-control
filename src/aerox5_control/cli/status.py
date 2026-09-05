"""Format supported device information without performing I/O."""

from aerox5_control.devices.aerox5 import Aerox5Status


def format_status(status: Aerox5Status) -> str:
    lines = []
    if status.interface is None:
        lines.append("Device: unavailable")
    else:
        interface = status.interface
        hid = interface.hid
        path = (
            hid.path.decode("utf-8", errors="backslashreplace")
            if isinstance(hid.path, bytes)
            else hid.path
        )
        lines.extend(
            (
                "Device: SteelSeries Aerox 5 Wireless",
                f"Connection: {interface.connection}",
                f"Vendor ID: 0x{hid.vendor_id:04x}",
                f"Product ID: 0x{hid.product_id:04x}",
                f"Interface: {hid.interface_number}",
                f"HID path: {path}",
            )
        )
        if hid.manufacturer_string:
            lines.append(f"Manufacturer: {hid.manufacturer_string}")
        if hid.serial_number:
            lines.append(f"Serial number: {hid.serial_number}")
        if hid.release_number is not None:
            lines.append(f"USB device release (bcdDevice): 0x{hid.release_number:04x}")
    if status.battery.available:
        lines.append(f"Battery: {status.battery.level}%")
        lines.append(f"Charging: {'yes' if status.battery.charging else 'no'}")
    else:
        lines.append("Battery: unavailable")
    return "\n".join(lines)

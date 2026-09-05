"""Coordinate allowlisted descriptor reads and generic offline parsing."""

from dataclasses import dataclass

from aerox5_control.application.services import inspect_interfaces
from aerox5_control.devices.aerox5 import AEROX5_USB_IDS, Aerox5Interface
from aerox5_control.hid_descriptor.models import DescriptorInfo
from aerox5_control.hid_descriptor.parser import DescriptorParseError, parse_descriptor
from aerox5_control.transport.interfaces import HidDiscovery
from aerox5_control.transport.linux_sysfs import (
    DescriptorReadError,
    DescriptorSnapshot,
    DescriptorSource,
    SysfsDescriptorReader,
)


@dataclass(frozen=True, slots=True)
class InterfaceInspection:
    entries: tuple[Aerox5Interface, ...]
    snapshot: DescriptorSnapshot | None
    descriptor: DescriptorInfo | None
    error: str | None


def inspect_hid_descriptors(
    transport: HidDiscovery | None = None,
    source: DescriptorSource | None = None,
) -> tuple[InterfaceInspection, ...]:
    """Read once per HID path, preserving all enumerated usage collections."""
    if source is None:
        source = SysfsDescriptorReader(AEROX5_USB_IDS)
    groups: dict[bytes | str, list[Aerox5Interface]] = {}
    for entry in inspect_interfaces(transport):
        groups.setdefault(entry.hid.path, []).append(entry)
    results = []
    for entries in groups.values():
        snapshot = None
        descriptor = None
        error = None
        first = entries[0].hid
        identities = {
            (entry.hid.vendor_id, entry.hid.product_id, entry.hid.interface_number)
            for entry in entries
        }
        try:
            if len(identities) != 1:
                raise DescriptorReadError(
                    "Conflicting identities share the same HID path"
                )
            snapshot = source.read(first)
            descriptor = parse_descriptor(snapshot.data)
        except (DescriptorReadError, DescriptorParseError) as failure:
            error = str(failure)
        results.append(InterfaceInspection(tuple(entries), snapshot, descriptor, error))
    return tuple(results)

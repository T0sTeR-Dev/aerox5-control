"""Read cached report descriptors without opening /dev/hidraw or issuing ioctls."""

import os
import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from aerox5_control.hid_descriptor.parser import MAX_DESCRIPTOR_SIZE
from aerox5_control.transport.interfaces import HidInterface

SYSFS_HIDRAW_ROOT = Path("/sys/class/hidraw")


class DescriptorReadError(Exception):
    """A cached descriptor is unavailable or its identity cannot be verified."""


@dataclass(frozen=True, slots=True)
class DescriptorSnapshot:
    data: bytes
    source: Path
    usb_parent: Path | None


class DescriptorSource(Protocol):
    def read(self, interface: HidInterface) -> DescriptorSnapshot: ...


class SysfsDescriptorReader:
    """Inspect only explicitly allowed USB identities, rechecked in sysfs."""

    def __init__(
        self,
        allowed_ids: Collection[tuple[int, int]],
        root: Path | None = None,
    ) -> None:
        self.allowed_ids = frozenset(allowed_ids)
        self.root = root if root is not None else SYSFS_HIDRAW_ROOT

    def read(self, interface: HidInterface) -> DescriptorSnapshot:
        expected = (interface.vendor_id, interface.product_id)
        if expected not in self.allowed_ids:
            raise DescriptorReadError(
                "Device identity is outside the inspection allowlist"
            )
        path = os.fsdecode(interface.path)
        if not re.fullmatch(r"/dev/hidraw[0-9]+", path):
            raise DescriptorReadError("HID path is not a Linux /dev/hidrawN path")

        try:
            # Resolve once so a reused hidraw number cannot redirect later reads.
            device = (self.root / Path(path).name / "device").resolve(strict=True)
            self._verify_identity(device, expected)
            usb_interface = next(
                (
                    parent
                    for parent in device.parents
                    if (parent / "bInterfaceNumber").is_file()
                ),
                None,
            )
            if usb_interface is not None and interface.interface_number is not None:
                number = int(
                    (usb_interface / "bInterfaceNumber").read_text().strip(), 16
                )
                if number != interface.interface_number:
                    raise DescriptorReadError(
                        "USB interface number changed since enumeration"
                    )
            source = device / "report_descriptor"
            with source.open("rb") as stream:
                data = stream.read(MAX_DESCRIPTOR_SIZE + 1)
            self._verify_identity(device, expected)
            if not data or len(data) > MAX_DESCRIPTOR_SIZE:
                raise DescriptorReadError(
                    "Cached descriptor is empty or exceeds 4096 bytes"
                )
            return DescriptorSnapshot(
                data, source, usb_interface.parent if usb_interface else None
            )
        except (OSError, ValueError) as error:
            raise DescriptorReadError(
                f"Cannot read cached descriptor: {error}"
            ) from error

    @staticmethod
    def _verify_identity(device: Path, expected: tuple[int, int]) -> None:
        properties = dict(
            line.split("=", 1)
            for line in (device / "uevent").read_text().splitlines()
            if "=" in line
        )
        try:
            bus, vendor, product = (
                int(part, 16) for part in properties["HID_ID"].split(":")
            )
        except (KeyError, ValueError) as error:
            raise DescriptorReadError("Cannot verify sysfs HID_ID") from error
        if bus != 3 or (vendor, product) != expected:
            raise DescriptorReadError("Sysfs USB identity does not match enumeration")

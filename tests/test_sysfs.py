"""Descriptor reads use temporary sysfs trees and never physical devices."""

from dataclasses import replace
from pathlib import Path

import pytest

from aerox5_control.devices.aerox5 import AEROX5_USB_IDS
from aerox5_control.transport.interfaces import HidInterface
from aerox5_control.transport.linux_sysfs import (
    DescriptorReadError,
    SysfsDescriptorReader,
)


@pytest.fixture
def interface(record):
    return HidInterface.from_enumeration({**record, "path": b"/dev/hidraw13"})


def test_reads_cached_descriptor_without_requiring_device_node(interface, make_sysfs):
    device = make_sysfs(interface, b"captured-bytes")
    snapshot = SysfsDescriptorReader(AEROX5_USB_IDS).read(interface)
    assert snapshot.data == b"captured-bytes"
    assert snapshot.source == device / "report_descriptor"
    assert snapshot.usb_parent == device.parent.parent


@pytest.mark.parametrize(
    "path",
    [b"/dev/hidraw13/../hidraw14", b"/dev/input/event0", b"opaque", b"/tmp/hidraw13"],
)
def test_rejects_non_hidraw_paths_before_reading(interface, path):
    with pytest.raises(DescriptorReadError, match="not a Linux"):
        SysfsDescriptorReader(AEROX5_USB_IDS).read(replace(interface, path=path))


def test_unrelated_device_is_rejected_before_any_file_access(interface, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Attempted filesystem access for an unrelated device")

    monkeypatch.setattr(Path, "resolve", forbidden)
    with pytest.raises(DescriptorReadError, match="allowlist"):
        SysfsDescriptorReader(AEROX5_USB_IDS).read(
            replace(interface, product_id=0x9999)
        )


@pytest.mark.parametrize(
    "identity", ["0003:00001038:00009999", "0005:00001038:00001852", "malformed"]
)
def test_identity_mismatch_prevents_descriptor_access(
    interface, make_sysfs, monkeypatch, identity
):
    device = make_sysfs(interface, b"must-not-read")
    (device / "uevent").write_text(f"HID_ID={identity}\n")
    original = Path.open

    def guarded(path, *args, **kwargs):
        if path.name == "report_descriptor":
            pytest.fail("Read descriptor before verifying identity")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(DescriptorReadError):
        SysfsDescriptorReader(AEROX5_USB_IDS).read(interface)


def test_interface_number_mismatch_is_rejected(interface, make_sysfs):
    make_sysfs(interface, b"cached")
    with pytest.raises(DescriptorReadError, match="interface number changed"):
        SysfsDescriptorReader(AEROX5_USB_IDS).read(
            replace(interface, interface_number=1)
        )


def test_missing_sysfs_is_a_read_error(interface):
    with pytest.raises(DescriptorReadError, match="Cannot read cached"):
        SysfsDescriptorReader(AEROX5_USB_IDS).read(interface)


def test_descriptor_permission_error_is_reported(interface, make_sysfs, monkeypatch):
    make_sysfs(interface, b"cached")
    original = Path.open

    def denied(path, *args, **kwargs):
        if path.name == "report_descriptor":
            raise PermissionError("synthetic permission failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(DescriptorReadError, match="synthetic permission failure"):
        SysfsDescriptorReader(AEROX5_USB_IDS).read(interface)


@pytest.mark.parametrize("data", [b"", b"x" * 4097])
def test_empty_or_oversized_cached_descriptor_is_reported(interface, make_sysfs, data):
    make_sysfs(interface, data)
    with pytest.raises(DescriptorReadError, match="empty or exceeds"):
        SysfsDescriptorReader(AEROX5_USB_IDS).read(interface)


def test_rechecks_identity_after_descriptor_read(interface, make_sysfs, monkeypatch):
    make_sysfs(interface, b"cached")
    original = Path.read_text
    reads = 0

    def swapped(path, *args, **kwargs):
        nonlocal reads
        if path.name == "uevent":
            reads += 1
            if reads == 2:
                return "HID_ID=0003:00001038:00009999\n"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", swapped)
    with pytest.raises(DescriptorReadError, match="does not match"):
        SysfsDescriptorReader(AEROX5_USB_IDS).read(interface)
    assert reads == 2

"""All tests replace both native HID modules before discovery can run."""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from aerox5_control.transport import linux_sysfs


@pytest.fixture(autouse=True)
def hid_backend(monkeypatch):
    # Any device/open/report operation is absent and raises AttributeError.
    backend = Mock(spec_set=["enumerate"])
    backend.enumerate.return_value = []
    monkeypatch.setitem(sys.modules, "hid", backend)
    monkeypatch.setitem(sys.modules, "hidraw", backend)
    return backend


@pytest.fixture
def io_backend(hid_backend, monkeypatch):
    """Opt-in mocked handle; feature reports and VID/PID opens remain absent."""
    backend = Mock(spec_set=["enumerate", "device"])
    device = Mock(spec_set=["open_path", "write", "read", "close"])
    backend.enumerate.return_value = []
    backend.device.return_value = device

    def write(data):
        assert data == b"\x00\xd2", "Only the battery query is allowed in I/O tests"
        return len(data)

    device.write.side_effect = write
    device.read.return_value = [0xD2, 16]
    monkeypatch.setitem(sys.modules, "hid", backend)
    monkeypatch.setitem(sys.modules, "hidraw", backend)
    return backend, device


@pytest.fixture
def receiver_configuration(record):
    return {
        **record,
        "interface_number": 3,
        "usage_page": 0xFFC0,
        "usage": 1,
        "path": b"/dev/hidraw42",
    }


@pytest.fixture
def record():
    return {
        "vendor_id": 0x1038,
        "product_id": 0x1852,
        "interface_number": 4,
        "usage_page": 0xFF00,
        "usage": 1,
        "manufacturer_string": "SteelSeries",
        "product_string": "SteelSeries Aerox 5 Wireless",
        "serial_number": "synthetic-serial",
        "path": b"/dev/hidraw-test0",
    }


@pytest.fixture(autouse=True)
def sysfs_root(tmp_path, monkeypatch):
    """Default descriptor inspection in tests can never reach real sysfs."""
    root = tmp_path / "sys" / "class" / "hidraw"
    root.mkdir(parents=True)
    monkeypatch.setattr(linux_sysfs, "SYSFS_HIDRAW_ROOT", root)
    return root


@pytest.fixture
def captured_interfaces():
    path = Path(__file__).parent / "fixtures" / "aerox5_receiver.json"
    return json.loads(path.read_text())["interfaces"]


@pytest.fixture
def make_sysfs(sysfs_root, tmp_path):
    def create(interface, data):
        name = Path(
            interface.path.decode()
            if isinstance(interface.path, bytes)
            else interface.path
        ).name
        number = (
            interface.interface_number if interface.interface_number is not None else 0
        )
        usb_interface = tmp_path / "devices" / "usb-test" / f"1-1:1.{number}"
        device = usb_interface / name
        device.mkdir(parents=True)
        (usb_interface / "bInterfaceNumber").write_text(f"{number:02x}\n")
        (device / "uevent").write_text(
            f"HID_ID=0003:{interface.vendor_id:08X}:{interface.product_id:08X}\n"
        )
        (device / "report_descriptor").write_bytes(data)
        entry = sysfs_root / name
        entry.mkdir()
        (entry / "device").symlink_to(device, target_is_directory=True)
        return device

    return create

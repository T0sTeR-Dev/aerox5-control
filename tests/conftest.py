"""All tests replace both native HID modules before discovery can run."""

import sys
from unittest.mock import Mock

import pytest


@pytest.fixture(autouse=True)
def hid_backend(monkeypatch):
    # Any device/open/report operation is absent and raises AttributeError.
    backend = Mock(spec_set=["enumerate"])
    backend.enumerate.return_value = []
    monkeypatch.setitem(sys.modules, "hid", backend)
    monkeypatch.setitem(sys.modules, "hidraw", backend)
    return backend


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

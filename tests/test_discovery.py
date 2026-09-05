"""Aerox identification without deduplication or interface assumptions."""

from unittest.mock import call

from aerox5_control.application.services import inspect_interfaces
from aerox5_control.devices.aerox5 import discover_aerox5
from aerox5_control.transport.hidapi_backend import HidApiTransport


def test_discovery_keeps_all_interfaces_and_connections(hid_backend, record):
    records = [
        {**record, "interface_number": number, "path": f"/dev/mock{number}".encode()}
        for number in range(5)
    ]
    # Same path with a different collection must also remain visible.
    records.append({**records[-1], "usage": 2})
    # A second receiver must not be merged by product ID or serial number.
    records.append({**record, "path": b"/dev/second-receiver"})
    records.append({**record, "product_id": 0x1854, "path": b"/dev/wired"})
    hid_backend.enumerate.return_value = records

    interfaces = inspect_interfaces()

    assert len(interfaces) == 8
    assert [item.hid.path for item in interfaces] == [item["path"] for item in records]
    assert [item.hid.interface_number for item in interfaces[:5]] == list(range(5))
    assert [item.hid.usage for item in interfaces[4:6]] == [1, 2]
    assert [item.connection for item in interfaces] == ["2.4 GHz"] * 7 + ["wired"]
    assert hid_backend.mock_calls == [call.enumerate(0x1038, 0)]


def test_discovery_requires_vendor_and_product_match(hid_backend, record):
    hid_backend.enumerate.return_value = [
        {**record, "vendor_id": 0x1234},
        {**record, "product_id": 0x9999},
        {**record, "product_id": 0x1854},
    ]

    (interface,) = discover_aerox5(HidApiTransport(hid_backend))

    assert interface.hid.vendor_id == 0x1038
    assert interface.hid.product_id == 0x1854
    assert interface.connection == "wired"


def test_no_devices_is_successful(hid_backend):
    assert inspect_interfaces(HidApiTransport(hid_backend)) == ()
    assert hid_backend.mock_calls == [call.enumerate(0x1038, 0)]

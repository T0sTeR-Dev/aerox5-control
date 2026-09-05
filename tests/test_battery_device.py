"""Fake transport transactions prove routing, one-command policy, and cleanup."""

from contextlib import contextmanager

import pytest

from aerox5_control.application.services import get_battery
from aerox5_control.devices.aerox5 import Aerox5Receiver
from aerox5_control.transport.hidapi_backend import HidReadTimeout
from aerox5_control.transport.interfaces import HidInterface


class FakeTransport:
    def __init__(
        self,
        entries,
        response=b"\xd2\x10",
        *,
        failure=None,
        expected_payload=b"\xd2",
    ):
        self.entries = tuple(HidInterface.from_enumeration(entry) for entry in entries)
        self.response = response
        self.failure = failure
        self.expected_payload = expected_payload
        self.calls = []

    def _fail(self, stage):
        if self.failure and self.failure[0] == stage:
            raise self.failure[1]

    def enumerate(self, vendor_id=0, product_id=0):
        self.calls.append(("enumerate", vendor_id, product_id))
        self._fail("enumerate")
        return self.entries

    @contextmanager
    def open_path(self, path):
        self.calls.append(("open", path))
        self._fail("open")
        try:
            yield self
        finally:
            self.close()

    def write_output(self, payload, *, report_id=0):
        assert payload == self.expected_payload and report_id == 0
        self.calls.append(("write", payload, report_id))
        self._fail("write")

    def read_input(self, max_length, *, timeout_ms):
        assert timeout_ms > 0
        self.calls.append(("read", max_length, timeout_ms))
        self._fail("read")
        return self.response

    def close(self):
        self.calls.append(("close",))


def test_routes_only_to_configuration_interface_with_dynamic_path(
    receiver_configuration,
):
    entries = [
        {
            **receiver_configuration,
            "interface_number": number,
            "path": f"/dev/hidraw{number}".encode(),
        }
        for number in (0, 1, 2, 4)
    ] + [
        {**receiver_configuration, "product_id": 0x1854},
        {**receiver_configuration, "vendor_id": 1},
        receiver_configuration,
        receiver_configuration.copy(),  # Duplicate collection entry, one query.
    ]
    # Unrelated records use different paths, even though the fake ignores filters.
    entries[4]["path"] = b"/dev/wired"
    entries[5]["path"] = b"/dev/unrelated"
    transport = FakeTransport(entries)
    status = get_battery(transport)
    assert status.level == 75
    assert transport.calls == [
        ("enumerate", 0x1038, 0x1852),
        ("open", b"/dev/hidraw42"),
        ("write", b"\xd2", 0),
        ("read", 2, 1000),
        ("close",),
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vendor_id", 0),
        ("product_id", 0x185C),
        ("interface_number", 0),
        ("interface_number", 1),
        ("interface_number", 2),
        ("interface_number", 4),
        ("interface_number", None),
        ("usage_page", 0xFFC1),
        ("usage_page", None),
        ("usage", 2),
        ("usage", None),
    ],
)
def test_unsupported_metadata_never_opens_or_writes(
    receiver_configuration, field, value
):
    transport = FakeTransport([{**receiver_configuration, field: value}])
    assert not Aerox5Receiver(transport).get_battery().available
    assert transport.calls == [
        ("enumerate", 0x1038, 0x1852),
        ("enumerate", 0x1038, 0x1854),
    ]


def test_multiple_receivers_do_not_trigger_queries(receiver_configuration):
    transport = FakeTransport(
        [receiver_configuration, {**receiver_configuration, "path": b"/dev/hidraw43"}]
    )
    status = get_battery(transport)
    assert "Multiple" in status.reason
    assert transport.calls == [("enumerate", 0x1038, 0x1852)]


def test_conflicting_metadata_for_same_path_is_rejected(receiver_configuration):
    transport = FakeTransport(
        [receiver_configuration, {**receiver_configuration, "interface_number": 4}]
    )
    status = get_battery(transport)
    assert "Conflicting" in status.reason
    assert transport.calls == [("enumerate", 0x1038, 0x1852)]


@pytest.mark.parametrize(
    ("stage", "error"),
    [
        ("enumerate", OSError("disconnected")),
        ("open", PermissionError("permission denied")),
        ("open", FileNotFoundError("device disconnected")),
        ("write", OSError("device disconnected")),
        ("read", OSError("device disconnected")),
        ("read", HidReadTimeout("read timeout")),
    ],
)
def test_failures_are_unavailable_without_retries(receiver_configuration, stage, error):
    transport = FakeTransport([receiver_configuration], failure=(stage, error))
    status = get_battery(transport)
    assert not status.available and status.charging is None
    assert str(error) in status.reason
    writes = [call for call in transport.calls if call[0] == "write"]
    assert writes == ([] if stage in ("enumerate", "open") else [("write", b"\xd2", 0)])
    if stage in ("read", "write"):
        assert transport.calls[-1] == ("close",)
    if stage == "write":
        assert not any(call[0] == "read" for call in transport.calls)


def test_empty_reply_is_unavailable_and_handle_closes(receiver_configuration):
    transport = FakeTransport([receiver_configuration], response=b"")
    assert not get_battery(transport).available
    assert transport.calls[-1] == ("close",)


def test_device_construction_does_not_touch_transport(receiver_configuration):
    transport = FakeTransport([receiver_configuration])
    Aerox5Receiver(transport)
    assert transport.calls == []


def test_wired_fallback_uses_wired_battery_command(receiver_configuration):
    wired_configuration = {
        **receiver_configuration,
        "product_id": 0x1854,
        "path": b"/dev/hidraw77",
    }

    transport = FakeTransport(
        [wired_configuration],
        response=b"\x92\x90",
        expected_payload=b"\x92",
    )

    status = Aerox5Receiver(transport).get_status()

    assert status.battery.level == 75
    assert status.battery.charging is True

    assert status.interface is not None
    assert status.interface.hid.product_id == 0x1854
    assert status.interface.hid.interface_number == 3
    assert status.interface.connection == "wired"

    assert transport.calls == [
        ("enumerate", 0x1038, 0x1852),
        ("enumerate", 0x1038, 0x1854),
        ("open", b"/dev/hidraw77"),
        ("write", b"\x92", 0),
        ("read", 2, 1000),
        ("close",),
    ]


def test_wireless_receiver_is_preferred_when_both_are_available(
    receiver_configuration,
):
    wired_configuration = {
        **receiver_configuration,
        "product_id": 0x1854,
        "path": b"/dev/wired",
    }

    transport = FakeTransport(
        [wired_configuration, receiver_configuration],
    )

    status = Aerox5Receiver(transport).get_status()

    assert status.battery.available
    assert status.interface is not None
    assert status.interface.hid.product_id == 0x1852
    assert status.interface.connection == "2.4 GHz"

    assert transport.calls == [
        ("enumerate", 0x1038, 0x1852),
        ("open", b"/dev/hidraw42"),
        ("write", b"\xd2", 0),
        ("read", 2, 1000),
        ("close",),
    ]

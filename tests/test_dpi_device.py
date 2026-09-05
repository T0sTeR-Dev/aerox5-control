"""DPI transactions use a FakeTransport with an exact sensitivity allowlist."""

from contextlib import contextmanager

import pytest

from aerox5_control.application.services import set_dpi_presets
from aerox5_control.devices.aerox5 import Aerox5Receiver
from aerox5_control.transport.hidapi_backend import HidReadTimeout
from aerox5_control.transport.interfaces import HidInterface


class FakeTransport:
    def __init__(self, entries, readback=bytes(64), *, failure=None):
        self.entries = tuple(HidInterface.from_enumeration(entry) for entry in entries)
        self.readback = readback
        self.failure = failure
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
        assert payload == b"\x6d\x01\x00\x09" and report_id == 0
        self.calls.append(("write", payload, report_id))
        self._fail("write")

    def read_input(self, max_length, *, timeout_ms):
        self.calls.append(("read", max_length, timeout_ms))
        self._fail("read")
        return self.readback

    def close(self):
        self.calls.append(("close",))
        self._fail("close")


@pytest.mark.parametrize("readback", [b"\x00", b"\x40\xff", b"\x6d\x09", bytes(64)])
def test_interface_three_and_single_transaction_with_opaque_readback(
    receiver_configuration, readback
):
    selected = {**receiver_configuration, "path": b"/dev/hidraw88"}
    entries = [
        {**selected, "interface_number": n, "path": f"/dev/hidraw{n}".encode()}
        for n in (0, 1, 2, 4)
    ] + [
        {**selected, "product_id": 0x1854, "path": b"/dev/wired"},
        {**selected, "vendor_id": 1, "path": b"/dev/unrelated"},
        selected,
        selected.copy(),
    ]
    transport = FakeTransport(entries, readback)
    presets = [800]
    result = set_dpi_presets(presets, transport)
    presets[0] = 1600
    assert result.completed
    assert result.requested_presets == (800,)
    assert result.write_attempted
    assert result.error is None
    assert result.readback == readback
    assert result.interface.hid.interface_number == 3
    assert transport.calls == [
        ("enumerate", 0x1038, 0x1852),
        ("open", b"/dev/hidraw88"),
        ("write", b"\x6d\x01\x00\x09", 0),
        ("read", 64, 1000),
        ("close",),
    ]


@pytest.mark.parametrize(
    "presets",
    [[], [800] * 6, [0], [50], [850], [18100], ["800"], [800.0], [True], None],
)
def test_invalid_input_never_touches_transport(receiver_configuration, presets):
    transport = FakeTransport([receiver_configuration])
    with pytest.raises(ValueError):
        Aerox5Receiver(transport).set_dpi_presets(presets)
    with pytest.raises(ValueError):
        set_dpi_presets(presets, transport)
    assert transport.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vendor_id", 0),
        ("product_id", 0x1854),
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
def test_wrong_or_missing_interface_metadata_prevents_open(
    receiver_configuration, field, value
):
    transport = FakeTransport([{**receiver_configuration, field: value}])
    result = set_dpi_presets([800], transport)
    assert not result.completed and not result.write_attempted
    assert result.interface is None
    assert result.readback is None
    assert "not found" in result.error
    assert transport.calls == [("enumerate", 0x1038, 0x1852)]


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"path": b"/dev/hidraw43"}, "Multiple"),
        ({"interface_number": 4}, "Conflicting"),
        ({"serial_number": "another-device"}, "Conflicting"),
    ],
)
def test_ambiguous_receiver_prevents_open(receiver_configuration, patch, reason):
    transport = FakeTransport(
        [receiver_configuration, {**receiver_configuration, **patch}]
    )
    result = set_dpi_presets([800], transport)
    assert not result.completed and not result.write_attempted
    assert reason in result.error
    assert transport.calls == [("enumerate", 0x1038, 0x1852)]


@pytest.mark.parametrize(
    ("stage", "error"),
    [
        ("enumerate", OSError("device disconnected")),
        ("open", PermissionError("permission denied")),
        ("open", FileNotFoundError("device disconnected")),
        ("write", OSError("device disconnected")),
        ("read", HidReadTimeout("read timed out")),
        ("read", OSError("device disconnected")),
        ("close", OSError("close failed")),
    ],
)
def test_failures_close_without_retry(receiver_configuration, stage, error):
    transport = FakeTransport([receiver_configuration], failure=(stage, error))
    result = set_dpi_presets([800], transport)
    attempted = stage not in ("enumerate", "open")
    assert not result.completed
    assert str(error) in result.error
    assert result.write_attempted is attempted
    assert result.readback == (bytes(64) if stage == "close" else None)
    assert [item for item in transport.calls if item[0] == "write"] == (
        [("write", b"\x6d\x01\x00\x09", 0)] if attempted else []
    )
    assert [item for item in transport.calls if item[0] == "read"] == (
        [("read", 64, 1000)] if stage in ("read", "close") else []
    )
    if attempted:
        assert transport.calls[-1] == ("close",)


@pytest.mark.parametrize("readback", [b"", None, [0], bytes(65)])
def test_invalid_injected_readback_is_failure(receiver_configuration, readback):
    transport = FakeTransport([receiver_configuration], readback)
    result = set_dpi_presets([800], transport)
    assert not result.completed
    assert result.write_attempted
    assert result.error
    assert result.readback is None
    if readback == b"":
        assert "timed out" in result.error
    assert transport.calls == [
        ("enumerate", 0x1038, 0x1852),
        ("open", b"/dev/hidraw42"),
        ("write", b"\x6d\x01\x00\x09", 0),
        ("read", 64, 1000),
        ("close",),
    ]

"""Status uses strict mocked HID handles; only the known battery query is allowed."""

from unittest.mock import call

import pytest

from aerox5_control.application.services import get_status
from aerox5_control.cli.main import main
from aerox5_control.devices.aerox5 import Aerox5Receiver
from aerox5_control.transport.hidapi_backend import HidApiTransport


@pytest.mark.parametrize(
    ("response", "level", "charging"),
    [
        ([0xD2, 9], 40, False),
        ([0xD2, 0x89], 40, True),
        ([0xD2, 1], 0, False),
        ([0xD2, 0x95], 100, True),
    ],
)
def test_status_queries_only_selected_interface_once(
    io_backend, receiver_configuration, capsys, response, level, charging
):
    backend, device = io_backend
    selected = {**receiver_configuration, "release_number": 0x0102}
    backend.enumerate.return_value = [
        {
            **receiver_configuration,
            "interface_number": number,
            "path": f"/dev/hidraw{number}".encode(),
        }
        for number in (0, 1, 2, 4)
    ] + [selected, selected.copy()]
    device.read.return_value = response

    assert main(["status"]) == 0

    output = capsys.readouterr()
    assert output.out == (
        "Device: SteelSeries Aerox 5 Wireless\n"
        "Connection: 2.4 GHz\n"
        "Vendor ID: 0x1038\n"
        "Product ID: 0x1852\n"
        "Interface: 3\n"
        "HID path: /dev/hidraw42\n"
        "Manufacturer: SteelSeries\n"
        "Serial number: synthetic-serial\n"
        "USB device release (bcdDevice): 0x0102\n"
        f"Battery: {level}%\n"
        f"Charging: {'yes' if charging else 'no'}\n"
    )
    assert output.err == ""
    assert backend.mock_calls == [
        call.enumerate(0x1038, 0x1852),
        call.device(),
        call.device().open_path(b"/dev/hidraw42"),
        call.device().write(b"\x00\xd2"),
        call.device().read(2, 1000),
        call.device().close(),
    ]


@pytest.mark.parametrize(
    "response",
    [
        [],  # Native HIDAPI read timeout.
        [0xD2],
        [0xD2, 0],
        [0xD2, 22],
        [0xD2, 0xFF],
        [0x40, 0xFF],
        [0x00, 9],
        [0x92, 9],
        [0xD2, 9, 0],
        [0xD2, 9, 1] + [0] * 61,
        [0xD2, 256],
    ],
)
def test_invalid_response_keeps_identity_but_not_battery_or_charging(
    io_backend, receiver_configuration, capsys, response
):
    backend, device = io_backend
    backend.enumerate.return_value = [receiver_configuration]
    device.read.return_value = response

    assert main(["status"]) == 1

    output = capsys.readouterr()
    assert "Device: SteelSeries Aerox 5 Wireless\n" in output.out
    assert "Connection: 2.4 GHz\n" in output.out
    assert output.out.endswith("Battery: unavailable\n")
    assert "Charging:" not in output.out
    assert "Firmware:" not in output.out
    assert "%" not in output.out
    assert output.err
    if response == []:
        assert "timed out" in output.err
    device.write.assert_called_once_with(b"\x00\xd2")
    device.read.assert_called_once_with(2, 1000)
    device.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("stage", "error"),
    [
        ("open_path", PermissionError("permission denied")),
        ("open_path", FileNotFoundError("device disconnected")),
        ("write", OSError("device disconnected")),
        ("read", OSError("device disconnected")),
        ("close", OSError("device disconnected")),
    ],
)
def test_io_failures_preserve_metadata_and_close_without_retry(
    io_backend, receiver_configuration, capsys, stage, error
):
    backend, device = io_backend
    backend.enumerate.return_value = [receiver_configuration]
    getattr(device, stage).side_effect = error

    assert main(["status"]) == 1

    output = capsys.readouterr()
    assert "Interface: 3\n" in output.out
    assert "Battery: unavailable\n" in output.out
    assert "Charging:" not in output.out
    assert str(error) in output.err
    if stage == "open_path":
        device.write.assert_not_called()
    else:
        device.write.assert_called_once_with(b"\x00\xd2")
    if stage in ("open_path", "write"):
        device.read.assert_not_called()
    else:
        device.read.assert_called_once_with(2, 1000)
    device.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vendor_id", 0x1234),
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
def test_status_never_opens_unsupported_interfaces(
    hid_backend, receiver_configuration, capsys, field, value
):
    hid_backend.enumerate.return_value = [{**receiver_configuration, field: value}]
    assert main(["status"]) == 1
    assert capsys.readouterr().out == "Device: unavailable\nBattery: unavailable\n"
    assert hid_backend.mock_calls == [
        call.enumerate(0x1038, 0x1852),
        call.enumerate(0x1038, 0x1854),
    ]


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"path": b"/dev/hidraw43"}, "Multiple"),
        ({"interface_number": 4}, "Conflicting"),
        ({"serial_number": "another-receiver"}, "Conflicting"),
        ({"release_number": 0x0102}, "Conflicting"),
    ],
)
def test_ambiguous_metadata_never_opens_device(
    hid_backend, receiver_configuration, capsys, patch, reason
):
    hid_backend.enumerate.return_value = [
        receiver_configuration,
        {**receiver_configuration, **patch},
    ]
    assert main(["status"]) == 1
    output = capsys.readouterr()
    assert output.out == "Device: unavailable\nBattery: unavailable\n"
    assert reason in output.err
    assert hid_backend.mock_calls == [call.enumerate(0x1038, 0x1852)]


@pytest.mark.parametrize("error", [None, OSError("device disconnected")])
def test_no_receiver_or_enumeration_error_is_unavailable(hid_backend, capsys, error):
    hid_backend.enumerate.side_effect = error
    assert main(["status"]) == 1
    output = capsys.readouterr()
    assert output.out == "Device: unavailable\nBattery: unavailable\n"
    assert output.err
    expected_calls = [call.enumerate(0x1038, 0x1852)]
    if error is None:
        expected_calls.append(call.enumerate(0x1038, 0x1854))
    assert hid_backend.mock_calls == expected_calls


def test_missing_metadata_and_unsupported_versions_are_omitted(
    io_backend, receiver_configuration, capsys
):
    backend, device = io_backend
    backend.enumerate.return_value = [
        {
            **receiver_configuration,
            "manufacturer_string": "",
            "serial_number": None,
            "release_number": "invalid",
            "path": b"/dev/hidraw-\xff",
        }
    ]
    assert main(["status"]) == 0
    output = capsys.readouterr()
    for label in (
        "Manufacturer:",
        "Serial number:",
        "bcdDevice",
        "Firmware:",
        "Revision:",
    ):
        assert label not in output.out
    assert r"HID path: /dev/hidraw-\xff" in output.out
    device.open_path.assert_called_once_with(b"/dev/hidraw-\xff")
    device.write.assert_called_once_with(b"\x00\xd2")
    assert output.err == ""


def test_application_returns_structured_metadata_without_firmware_inference(
    io_backend, receiver_configuration
):
    backend, device = io_backend
    backend.enumerate.return_value = [
        {**receiver_configuration, "release_number": 0x0102}
    ]
    status = get_status(HidApiTransport(backend))
    assert status.interface.connection == "2.4 GHz"
    assert status.interface.hid.release_number == 0x0102
    assert status.battery.level == 75
    assert status.battery.charging is False
    device.write.assert_called_once_with(b"\x00\xd2")


def test_later_disconnect_does_not_reuse_previous_battery(
    io_backend, receiver_configuration
):
    backend, device = io_backend
    backend.enumerate.return_value = [receiver_configuration]
    receiver = Aerox5Receiver(HidApiTransport(backend))
    assert receiver.get_status().battery.level == 75
    backend.enumerate.return_value = []
    status = receiver.get_status()
    assert status.interface is None
    assert status.battery.level is None
    assert status.battery.charging is None
    # The second call discovers afresh and never creates another handle.
    backend.device.assert_called_once_with()
    device.write.assert_called_once_with(b"\x00\xd2")
    device.close.assert_called_once_with()

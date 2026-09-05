"""Desktop state exercises existing services exclusively through strict HID mocks."""

from unittest.mock import call

import pytest

from aerox5_control.application.desktop import (
    POLLING_RATES,
    PRESET_COUNTS,
    DesktopService,
    hardware_problem,
    parse_dpi_inputs,
    validate_polling_input,
)


def test_disconnected_refresh_uses_only_restricted_discovery(hid_backend):
    overview = DesktopService().refresh()
    assert overview.state == "Disconnected"
    assert overview.battery == overview.charging == "Unavailable"
    assert overview.vendor_id == overview.product_id == "Unavailable"
    assert "Refresh" in overview.message
    assert hid_backend.mock_calls == [call.enumerate(0x1038, 0x1852)]


@pytest.mark.parametrize(
    ("value", "battery", "charging"),
    [
        (1, "0%", "No"),
        (9, "40%", "No"),
        (0x95, "100%", "Yes"),
    ],
)
def test_connected_overview(
    io_backend, receiver_configuration, value, battery, charging
):
    backend, device = io_backend
    backend.enumerate.return_value = [receiver_configuration]
    device.read.return_value = [0xD2, value]
    overview = DesktopService().refresh()
    assert overview.name == "SteelSeries Aerox 5 Wireless"
    assert overview.state == "Connected"
    assert overview.connection == "2.4 GHz"
    assert overview.vendor_id == "0x1038"
    assert overview.product_id == "0x1852"
    assert overview.battery == battery
    assert overview.charging == charging
    assert backend.mock_calls == [
        call.enumerate(0x1038, 0x1852),
        call.device(),
        call.device().open_path(receiver_configuration["path"]),
        call.device().write(b"\x00\xd2"),
        call.device().read(64, 1000),
        call.device().close(),
    ]


@pytest.mark.parametrize(
    ("reply", "state", "message"),
    [
        ([], "Connection unavailable", "did not respond in time"),
        ([0xD2], "Connection unavailable", "Battery and charging"),
        ([0xD2, 22], "Connection unavailable", "Battery and charging"),
        ([0x40, 0xFF], "Disconnected", "wake the mouse"),
    ],
)
def test_battery_unavailable_does_not_claim_receiver_proves_mouse_link(
    io_backend, receiver_configuration, reply, state, message
):
    backend, device = io_backend
    backend.enumerate.return_value = [receiver_configuration]
    device.read.return_value = reply
    overview = DesktopService().refresh()
    assert overview.state == state
    assert overview.connection == "2.4 GHz"
    assert overview.battery == overview.charging == "Unavailable"
    assert message in overview.message


@pytest.mark.parametrize(
    ("stage", "error", "state", "message"),
    [
        (
            "open_path",
            PermissionError("permission denied"),
            "Connection unavailable",
            "Permission denied",
        ),
        ("read", OSError("device disconnected"), "Disconnected", "Reconnect"),
        (
            "write",
            OSError("write failed"),
            "Connection unavailable",
            "could not be completed",
        ),
    ],
)
def test_refresh_errors(
    io_backend, receiver_configuration, stage, error, state, message
):
    backend, device = io_backend
    backend.enumerate.return_value = [receiver_configuration]
    getattr(device, stage).side_effect = error
    overview = DesktopService().refresh()
    assert overview.state == state
    assert overview.battery == overview.charging == "Unavailable"
    assert message in overview.message
    assert device.write.call_count <= 1


@pytest.mark.parametrize(
    "presets",
    [
        ["100"],
        ["18000"],
        ["800", "1600"],
        ["400", "800", "1200", "2400", "3200"],
    ],
)
def test_valid_dpi_inputs(presets, hid_backend):
    assert parse_dpi_inputs(presets) == tuple(map(int, presets))
    assert not hid_backend.mock_calls


@pytest.mark.parametrize(
    "presets",
    [
        [],
        ["800"] * 6,
        ["0"],
        ["50"],
        ["850"],
        ["18100"],
        ["18001"],
        [""],
        [" "],
        ["800.0"],
        ["8e2"],
        ["one"],
        ["800_0"],
        ["-100"],
        ["８００"],
        [800],
        "800",
    ],
)
def test_invalid_dpi_is_never_rounded_or_sent(presets, hid_backend):
    with pytest.raises(ValueError):
        parse_dpi_inputs(presets)
    assert not hid_backend.mock_calls


def test_options():
    assert POLLING_RATES == (125, 250, 500, 1000)
    assert PRESET_COUNTS == (1, 2, 3, 4, 5)
    for value in POLLING_RATES:
        assert validate_polling_input(value) == value


@pytest.mark.parametrize("rate", [None, True, 100, 1000.0, "1000"])
def test_invalid_polling(rate, hid_backend):
    with pytest.raises(ValueError):
        validate_polling_input(rate)
    assert not hid_backend.mock_calls


@pytest.mark.parametrize("operation", ["dpi", "polling"])
def test_adapter_sends_one_existing_request_on_interface_three_only(
    operation, request, receiver_configuration
):
    backend, device = request.getfixturevalue(f"{operation}_backend")
    backend.enumerate.return_value = [
        {**receiver_configuration, "interface_number": number, "path": f"fake-{number}"}
        for number in (0, 1, 2, 4)
    ] + [receiver_configuration]
    service = DesktopService()
    feedback = (
        service.apply_dpi((800,)) if operation == "dpi" else service.apply_polling(1000)
    )
    payload = b"\x00\x6d\x01\x00\x09" if operation == "dpi" else b"\x00\x6b\x00"
    assert not feedback.error
    assert "request sent" in feedback.message
    assert "not been read back" in feedback.message
    assert backend.mock_calls == [
        call.enumerate(0x1038, 0x1852),
        call.device(),
        call.device().open_path(receiver_configuration["path"]),
        call.device().write(payload),
        call.device().read(64, 1000),
        call.device().close(),
    ]


@pytest.mark.parametrize("operation", ["dpi", "polling"])
@pytest.mark.parametrize(
    ("stage", "error", "message", "attempted"),
    [
        ("open_path", PermissionError("permission denied"), "Permission denied", False),
        ("write", OSError("device disconnected"), "Reconnect", True),
        ("read", OSError("device disconnected"), "Reconnect", True),
        ("read", None, "did not respond in time", True),
        ("write", OSError("write failed"), "could not be completed", True),
    ],
)
def test_setting_errors_and_uncertain_writes(
    operation, request, receiver_configuration, stage, error, message, attempted
):
    backend, device = request.getfixturevalue(f"{operation}_backend")
    backend.enumerate.return_value = [receiver_configuration]
    if error is None:
        device.read.return_value = []
    else:
        getattr(device, stage).side_effect = error
    service = DesktopService()
    feedback = (
        service.apply_dpi((800,)) if operation == "dpi" else service.apply_polling(1000)
    )
    assert feedback.error
    assert message in feedback.message
    assert ("may already have changed" in feedback.message) == attempted
    assert device.write.call_count == int(attempted)


def test_unknown_errors_are_useful_without_raw_paths():
    problem = hardware_problem(OSError("/dev/hidraw-secret: unknown failure"))
    assert problem.error
    assert "device access" in problem.message
    assert "CLI status" in problem.message
    assert "/dev/" not in problem.message

"""CLI battery tests patch both native modules before the command is invoked."""

from unittest.mock import call

import pytest

from aerox5_control.cli.main import main


@pytest.mark.parametrize(
    ("value", "charging"), [(16, "no"), (0x90, "yes"), (1, "no"), (21, "no")]
)
def test_battery_command(io_backend, receiver_configuration, capsys, value, charging):
    backend, device = io_backend
    backend.enumerate.return_value = [receiver_configuration]
    device.read.return_value = [0xD2, value]
    assert main(["battery"]) == 0
    output = capsys.readouterr()
    level = ((value & 0x7F) - 1) * 5
    assert output.out == f"Battery: {level}%\nCharging: {charging}\n"
    assert output.err == ""
    assert backend.mock_calls == [
        call.enumerate(0x1038, 0x1852),
        call.device(),
        call.device().open_path(b"/dev/hidraw42"),
        call.device().write(b"\x00\xd2"),
        call.device().read(2, 1000),
        call.device().close(),
    ]


@pytest.mark.parametrize("response", [[], [0xD2], [0xD2, 0], [0x40, 0xFF], [0, 16]])
def test_unavailable_output_omits_charging(
    io_backend, receiver_configuration, capsys, response
):
    backend, device = io_backend
    backend.enumerate.return_value = [receiver_configuration]
    device.read.return_value = response
    assert main(["battery"]) == 1
    output = capsys.readouterr()
    assert output.out == "Battery: unavailable\n"
    assert output.err
    device.write.assert_called_once_with(b"\x00\xd2")
    device.close.assert_called_once_with()


def test_permission_failure_is_actionable_without_root(
    io_backend, receiver_configuration, capsys
):
    backend, device = io_backend
    backend.enumerate.return_value = [receiver_configuration]
    device.open_path.side_effect = PermissionError("permission denied")
    assert main(["battery"]) == 1
    output = capsys.readouterr()
    assert output.out == "Battery: unavailable\n"
    assert "permission denied" in output.err
    device.write.assert_not_called()
    device.read.assert_not_called()


def test_no_receiver_never_opens_device(hid_backend, capsys):
    assert main(["battery"]) == 1
    assert capsys.readouterr().out == "Battery: unavailable\n"
    assert hid_backend.mock_calls == [call.enumerate(0x1038, 0x1852), call.enumerate(0x1038, 0x1854)]


def test_discovery_does_not_query_battery(io_backend, receiver_configuration, capsys):
    backend, device = io_backend
    backend.enumerate.return_value = [receiver_configuration]
    assert main(["inspect"]) == 0
    assert "Battery:" not in capsys.readouterr().out
    backend.device.assert_not_called()
    assert device.mock_calls == []

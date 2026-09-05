"""Polling CLI calls native HIDAPI mocks with an exact command allowlist."""

from unittest.mock import call

import pytest

from aerox5_control.application.services import set_polling_rate
from aerox5_control.cli.main import main
from aerox5_control.transport import hidapi_backend


@pytest.mark.parametrize(
    ("rate", "buffer"),
    [
        (1000, b"\x00\x6b\x00"),
        (500, b"\x00\x6b\x01"),
        (250, b"\x00\x6b\x02"),
        (125, b"\x00\x6b\x03"),
    ],
)
def test_each_cli_rate_sends_only_one_exact_polling_command(
    polling_backend, receiver_configuration, capsys, rate, buffer
):
    backend, device = polling_backend
    backend.enumerate.return_value = [receiver_configuration]

    assert main(["polling", "set", str(rate)]) == 0

    output = capsys.readouterr()
    assert output.out == (
        f"Polling-rate request sent: {rate} Hz\n"
        "Readback received; active rate unverified.\n"
    )
    assert output.err == ""
    # This complete call sequence also rules out saves, battery queries,
    # feature reports, and all other commands before or after the polling write.
    assert backend.mock_calls == [
        call.enumerate(0x1038, 0x1852),
        call.device(),
        call.device().open_path(b"/dev/hidraw42"),
        call.device().write(buffer),
        call.device().read(64, 1000),
        call.device().close(),
    ]


@pytest.mark.parametrize("value", ["0", "100", "144", "2000", "1000.0", "invalid"])
def test_invalid_cli_rate_never_loads_hid(monkeypatch, hid_backend, value):
    def forbid_import(name):
        pytest.fail(f"Validation loaded HID module {name}")

    monkeypatch.setattr(hidapi_backend, "import_module", forbid_import)
    with pytest.raises(SystemExit) as caught:
        main(["polling", "set", value])
    assert caught.value.code == 2
    assert hid_backend.mock_calls == []


def test_invalid_service_rate_never_loads_hid(monkeypatch, hid_backend):
    def forbid_import(name):
        pytest.fail(f"Validation loaded HID module {name}")

    monkeypatch.setattr(hidapi_backend, "import_module", forbid_import)
    with pytest.raises(ValueError):
        set_polling_rate(144)
    assert hid_backend.mock_calls == []


@pytest.mark.parametrize(
    ("method", "error"),
    [
        ("open_path", PermissionError("permission denied")),
        ("open_path", FileNotFoundError("device disconnected")),
        ("write", OSError("device disconnected")),
        ("read", OSError("device disconnected")),
        ("close", OSError("close failed")),
    ],
)
def test_cli_io_errors_are_clear_and_never_retried(
    polling_backend, receiver_configuration, capsys, method, error
):
    backend, device = polling_backend
    backend.enumerate.return_value = [receiver_configuration]
    getattr(device, method).side_effect = error

    assert main(["polling", "set", "1000"]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert "polling-rate request failed" in output.err
    assert str(error) in output.err
    if method == "open_path":
        device.write.assert_not_called()
        assert "may have changed" not in output.err
    else:
        device.write.assert_called_once_with(b"\x00\x6b\x00")
        assert "may have changed; no retry was sent" in output.err
    if method in ("open_path", "write"):
        device.read.assert_not_called()
    else:
        device.read.assert_called_once_with(64, 1000)
    device.close.assert_called_once_with()


@pytest.mark.parametrize("count", [0, 1, 2, -1])
def test_short_write_fails_without_readback_or_retry(
    polling_backend, receiver_configuration, capsys, count
):
    backend, device = polling_backend
    backend.enumerate.return_value = [receiver_configuration]
    device.write.side_effect = None
    device.write.return_value = count
    assert main(["polling", "set", "500"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Incomplete HID output write" in output.err
    assert "may have changed" in output.err
    device.write.assert_called_once_with(b"\x00\x6b\x01")
    device.read.assert_not_called()
    device.close.assert_called_once_with()


@pytest.mark.parametrize("response", [[], None, [256], [True], "data", [0] * 65])
def test_timeout_or_invalid_native_readback_is_failure(
    polling_backend, receiver_configuration, capsys, response
):
    backend, device = polling_backend
    backend.enumerate.return_value = [receiver_configuration]
    device.read.return_value = response
    assert main(["polling", "set", "125"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "polling-rate request failed" in output.err
    assert "may have changed; no retry was sent" in output.err
    if response == []:
        assert "timed out" in output.err
    device.write.assert_called_once_with(b"\x00\x6b\x03")
    device.read.assert_called_once_with(64, 1000)
    device.close.assert_called_once_with()


@pytest.mark.parametrize("error", [None, OSError("receiver disconnected")])
def test_missing_receiver_or_enumeration_failure_never_opens(
    hid_backend, capsys, error
):
    hid_backend.enumerate.side_effect = error
    assert main(["polling", "set", "1000"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "polling-rate request failed" in output.err
    assert "may have changed" not in output.err
    assert hid_backend.mock_calls == [call.enumerate(0x1038, 0x1852)]

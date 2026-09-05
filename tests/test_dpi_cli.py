"""Full CLI transactions use strict mocked native handles, never hardware."""

from unittest.mock import call

import pytest

from aerox5_control.application.services import set_dpi_presets
from aerox5_control.cli.main import main
from aerox5_control.transport import hidapi_backend


@pytest.mark.parametrize(
    ("presets", "buffer"),
    [
        ([800], b"\x00\x6d\x01\x00\x09"),
        ([800, 1600], b"\x00\x6d\x02\x00\x09\x12"),
        ([400, 800, 1200, 2400, 3200], b"\x00\x6d\x05\x00\x04\x09\x0d\x1b\x26"),
        ([100], b"\x00\x6d\x01\x00\x00"),
        ([18000], b"\x00\x6d\x01\x00\xd6"),
        ([1600, 800], b"\x00\x6d\x02\x00\x12\x09"),
        # These are valid sensor data bytes, not save/polling command opcodes.
        ([6800, 9000], b"\x00\x6d\x02\x00\x51\x6b"),
    ],
)
def test_one_exact_dpi_write_and_no_other_command(
    dpi_backend, receiver_configuration, capsys, presets, buffer
):
    backend, device = dpi_backend
    backend.enumerate.return_value = [receiver_configuration]
    assert main(["dpi", "set", *map(str, presets)]) == 0
    output = capsys.readouterr()
    assert output.out == (
        f"DPI preset request sent: {' / '.join(map(str, presets))}\n"
        "Requested selected preset: 0 (first)\n"
        "Readback received; active DPI presets unverified.\n"
    )
    assert output.err == ""
    # Full sequence excludes saves, polling writes, battery queries, retries,
    # and feature-report calls as well as checking the synthetic zero prefix.
    assert backend.mock_calls == [
        call.enumerate(0x1038, 0x1852),
        call.device(),
        call.device().open_path(b"/dev/hidraw42"),
        call.device().write(buffer),
        call.device().read(64, 1000),
        call.device().close(),
    ]


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["800"] * 6,
        ["0"],
        ["50"],
        ["850"],
        ["18100"],
        ["800.0"],
        ["bad"],
        ["800", "850"],
    ],
)
def test_invalid_cli_arguments_never_load_hid(monkeypatch, hid_backend, args):
    def forbid_import(name):
        pytest.fail(f"DPI validation loaded HID module {name}")

    monkeypatch.setattr(hidapi_backend, "import_module", forbid_import)
    with pytest.raises(SystemExit) as caught:
        main(["dpi", "set", *args])
    assert caught.value.code == 2
    assert hid_backend.mock_calls == []


def test_invalid_service_input_never_loads_hid(monkeypatch, hid_backend):
    def forbid_import(name):
        pytest.fail(f"DPI validation loaded HID module {name}")

    monkeypatch.setattr(hidapi_backend, "import_module", forbid_import)
    with pytest.raises(ValueError):
        set_dpi_presets([850])
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
def test_cli_failure_is_explicit_and_never_retried(
    dpi_backend, receiver_configuration, capsys, method, error
):
    backend, device = dpi_backend
    backend.enumerate.return_value = [receiver_configuration]
    getattr(device, method).side_effect = error
    assert main(["dpi", "set", "800"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "DPI preset request failed" in output.err
    assert str(error) in output.err
    if method == "open_path":
        device.write.assert_not_called()
        assert "may have changed" not in output.err
    else:
        device.write.assert_called_once_with(b"\x00\x6d\x01\x00\x09")
        assert "may have changed; no retry was sent" in output.err
    if method in ("open_path", "write"):
        device.read.assert_not_called()
    else:
        device.read.assert_called_once_with(64, 1000)
    device.close.assert_called_once_with()


@pytest.mark.parametrize("count", [0, 1, 4, -1])
def test_incomplete_write_is_not_retried(
    dpi_backend, receiver_configuration, capsys, count
):
    backend, device = dpi_backend
    backend.enumerate.return_value = [receiver_configuration]
    device.write.side_effect = None
    device.write.return_value = count
    assert main(["dpi", "set", "800"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Incomplete HID output write" in output.err
    assert "may have changed" in output.err
    device.write.assert_called_once_with(b"\x00\x6d\x01\x00\x09")
    device.read.assert_not_called()
    device.close.assert_called_once_with()


@pytest.mark.parametrize("response", [[], None, [256], [True], "data", [0] * 65])
def test_timeout_and_malformed_native_readback_are_failures(
    dpi_backend, receiver_configuration, capsys, response
):
    backend, device = dpi_backend
    backend.enumerate.return_value = [receiver_configuration]
    device.read.return_value = response
    assert main(["dpi", "set", "800"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "DPI preset request failed" in output.err
    assert "may have changed; no retry was sent" in output.err
    if response == []:
        assert "timed out" in output.err
    device.write.assert_called_once_with(b"\x00\x6d\x01\x00\x09")
    device.read.assert_called_once_with(64, 1000)
    device.close.assert_called_once_with()


@pytest.mark.parametrize("error", [None, OSError("device disconnected")])
def test_no_receiver_or_enumeration_failure_never_opens(hid_backend, capsys, error):
    hid_backend.enumerate.side_effect = error
    assert main(["dpi", "set", "800"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "DPI preset request failed" in output.err
    assert "may have changed" not in output.err
    assert hid_backend.mock_calls == [call.enumerate(0x1038, 0x1852)]

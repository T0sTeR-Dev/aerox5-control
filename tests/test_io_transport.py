"""Native API adapter tests use strict mocks, never actual HID handles."""

from unittest.mock import call

import pytest

from aerox5_control.transport.hidapi_backend import (
    HidApiTransport,
    HidOperationError,
    HidReadTimeout,
    encode_output_report,
)


def test_exact_output_and_same_handle_read_close(io_backend):
    backend, device = io_backend
    with HidApiTransport(backend).open_path("/dev/hidraw42") as connection:
        connection.write_output(b"\xd2")
        assert connection.read_input(64, timeout_ms=1000) == b"\xd2\x10"
    backend.device.assert_called_once_with()
    assert device.mock_calls == [
        call.open_path(b"/dev/hidraw42"),
        call.write(b"\x00\xd2"),
        call.read(64, 1000),
        call.close(),
    ]


@pytest.mark.parametrize("count", [0, 1, -1, 3, None, True])
def test_short_or_invalid_write_result_fails_without_retry(io_backend, count):
    backend, device = io_backend
    device.write.side_effect = None
    device.write.return_value = count
    with pytest.raises(HidOperationError, match="Incomplete"):
        with HidApiTransport(backend).open_path(b"/dev/hidraw42") as connection:
            connection.write_output(b"\xd2")
    device.write.assert_called_once_with(b"\x00\xd2")
    device.read.assert_not_called()
    device.close.assert_called_once_with()


def test_timeout_is_bounded_and_closes(io_backend):
    backend, device = io_backend
    device.read.return_value = []
    with pytest.raises(HidReadTimeout):
        with HidApiTransport(backend).open_path(b"/dev/hidraw42") as connection:
            connection.read_input(64, timeout_ms=1000)
    device.read.assert_called_once_with(64, 1000)
    device.close.assert_called_once_with()
    device.write.assert_not_called()


@pytest.mark.parametrize(
    "values", [None, [256], [-1], [True], "data", [1.0], list(bytes(65))]
)
def test_malformed_native_read_is_rejected(io_backend, values):
    backend, device = io_backend
    device.read.return_value = values
    with pytest.raises(HidOperationError):
        with HidApiTransport(backend).open_path(b"/dev/hidraw42") as connection:
            connection.read_input(64, timeout_ms=1000)
    device.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("method", "error"),
    [
        ("open_path", PermissionError("permission denied")),
        ("open_path", OSError("open failed")),
        ("write", OSError("device disconnected")),
        ("read", OSError("device disconnected")),
        ("close", OSError("close failed")),
    ],
)
def test_native_failures_close_handle(io_backend, method, error):
    backend, device = io_backend
    getattr(device, method).side_effect = error
    with pytest.raises(HidOperationError, match=str(error)):
        with HidApiTransport(backend).open_path(b"/dev/hidraw42") as connection:
            connection.write_output(b"\xd2")
            connection.read_input(64, timeout_ms=1000)
    device.close.assert_called_once_with()
    if method == "open_path":
        device.write.assert_not_called()
    if method in ("open_path", "write"):
        device.read.assert_not_called()


def test_read_failure_is_not_hidden_by_close_failure(io_backend):
    backend, device = io_backend
    device.read.side_effect = OSError("read disconnected")
    device.close.side_effect = OSError("close disconnected")
    with pytest.raises(HidOperationError, match="read disconnected"):
        with HidApiTransport(backend).open_path(b"/dev/hidraw42") as connection:
            connection.read_input(64, timeout_ms=1000)


@pytest.mark.parametrize("timeout", [0, -1, None, True])
def test_infinite_or_invalid_timeout_is_rejected_before_read(io_backend, timeout):
    backend, device = io_backend
    with HidApiTransport(backend).open_path(b"/dev/hidraw42") as connection:
        with pytest.raises(ValueError, match="timeout"):
            connection.read_input(64, timeout_ms=timeout)
    device.read.assert_not_called()


def test_connection_close_is_idempotent_and_rejects_further_io(io_backend):
    backend, device = io_backend
    connection = HidApiTransport(backend).open_path(b"/dev/hidraw42")
    connection.close()
    connection.close()
    with pytest.raises(HidOperationError, match="closed"):
        connection.write_output(b"\xd2")
    with pytest.raises(HidOperationError, match="closed"):
        connection.read_input(64, timeout_ms=1000)
    device.close.assert_called_once_with()
    device.write.assert_not_called()
    device.read.assert_not_called()


def test_generic_numbered_report_framing_is_pure():
    assert encode_output_report(b"\xd2", report_id=3) == b"\x03\xd2"


@pytest.mark.parametrize("report_id", [-1, 256, None, True])
def test_invalid_report_id_is_rejected(report_id):
    with pytest.raises(ValueError):
        encode_output_report(b"\xd2", report_id=report_id)

"""Generic HIDAPI enumeration and explicitly requested output/input report I/O."""

import os
from contextlib import AbstractContextManager
from importlib import import_module
from typing import Protocol, cast

from aerox5_control.transport.interfaces import EnumerationBackend, HidInterface


class HidError(Exception):
    """HID discovery or I/O could not be completed."""


class HidBackendUnavailable(HidError):
    """The required Python binding or native library is unavailable."""


class HidEnumerationError(HidError):
    """The backend failed to enumerate devices."""


class HidOperationError(HidError):
    """An interface could not be opened, read, written, or closed."""


class HidReadTimeout(HidOperationError):
    """No input report arrived before the read timeout."""


class _NativeDevice(Protocol):
    def open_path(self, path: bytes) -> None: ...
    def write(self, data: bytes) -> int: ...
    def read(self, max_length: int, timeout_ms: int) -> list[int]: ...
    def close(self) -> None: ...


class _DeviceBackend(EnumerationBackend, Protocol):
    def device(self) -> _NativeDevice: ...


def encode_output_report(payload: bytes, *, report_id: int = 0) -> bytes:
    """Add HIDAPI's ID prefix; an unnumbered report uses a synthetic zero.

    Payload lengths and any protocol padding belong to the caller. Never pad,
    truncate, or reinterpret the payload here.
    """
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("Output payload must be nonempty bytes")
    if type(report_id) is not int or not 0 <= report_id <= 255:
        raise ValueError("Report ID must be a byte")
    return bytes((report_id,)) + payload


class HidApiConnection(AbstractContextManager):
    """Own one handle, checking writes and bounding each input read."""

    def __init__(self, device: _NativeDevice) -> None:
        self._device: _NativeDevice | None = device

    def _handle(self) -> _NativeDevice:
        if self._device is None:
            raise HidOperationError("HID interface is closed")
        return self._device

    def write_output(self, payload: bytes, *, report_id: int = 0) -> None:
        data = encode_output_report(payload, report_id=report_id)
        try:
            written = self._handle().write(data)
        except (OSError, RuntimeError) as error:
            raise HidOperationError(f"HID output write failed: {error}") from error
        if type(written) is not int or written != len(data):
            raise HidOperationError(
                f"Incomplete HID output write: {written!r} of {len(data)} bytes"
            )

    def read_input(self, max_length: int, *, timeout_ms: int) -> bytes:
        if type(max_length) is not int or max_length <= 0:
            raise ValueError("Read length must be positive")
        if type(timeout_ms) is not int or timeout_ms <= 0:
            raise ValueError(
                "Read timeout must be positive; infinite reads are forbidden"
            )
        try:
            values = self._handle().read(max_length, timeout_ms)
        except (OSError, RuntimeError) as error:
            raise HidOperationError(f"HID input read failed: {error}") from error
        # HIDAPI returns a list of byte values; reject malformed adapter results.
        if not isinstance(values, (list, bytes)) or any(
            type(value) is not int or not 0 <= value <= 255 for value in values
        ):
            raise HidOperationError("Malformed HID input data")
        if not values:
            raise HidReadTimeout("HID input read timed out")
        if len(values) > max_length:
            raise HidOperationError("HID input exceeded the requested read length")
        return bytes(values)

    def close(self) -> None:
        device, self._device = self._device, None
        if device is not None:
            try:
                device.close()
            except (OSError, RuntimeError) as error:
                raise HidOperationError(f"HID close failed: {error}") from error

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            self.close()
        except HidError:
            if exc_type is None:
                raise


class HidApiTransport:
    """Enumeration does not open devices; open_path must be explicitly called."""

    def __init__(self, backend: EnumerationBackend | None = None) -> None:
        self._backend = backend

    def _load_backend(self) -> EnumerationBackend:
        backend = self._backend
        if backend is None:
            try:
                try:
                    # Upstream Linux wheels ship hidraw alongside a libusb hid.
                    module = import_module("hidraw")
                except ModuleNotFoundError as error:
                    if error.name != "hidraw":
                        raise
                    # Arch's hidraw-only python-hidapi build names its module hid.
                    module = import_module("hid")
                backend = cast(EnumerationBackend, module)
            except (ImportError, OSError) as error:
                raise HidBackendUnavailable(
                    "Cannot load python-hidapi. Install python-hidapi on Arch Linux "
                    "or hidapi in your Python environment, and ensure native "
                    f"HIDAPI is available. Details: {error}"
                ) from error
            self._backend = backend
        return backend

    def enumerate(
        self, vendor_id: int = 0, product_id: int = 0
    ) -> tuple[HidInterface, ...]:
        """Return every backend entry; zero IDs mean no filter for that ID."""
        try:
            records = self._load_backend().enumerate(vendor_id, product_id)
        except (OSError, RuntimeError) as error:
            raise HidEnumerationError(f"HID enumeration failed: {error}") from error

        return tuple(HidInterface.from_enumeration(record) for record in records)

    def open_path(self, path: bytes | str) -> HidApiConnection:
        """Open the exact enumerated path; no VID/PID-based handle selection."""
        raw_path = os.fsencode(path)
        if not raw_path or b"\x00" in raw_path:
            raise HidOperationError("Invalid HID path")
        backend = cast(_DeviceBackend, self._load_backend())
        try:
            device = backend.device()
        except (OSError, RuntimeError) as error:
            raise HidOperationError(f"HID handle creation failed: {error}") from error
        connection = HidApiConnection(device)
        try:
            device.open_path(raw_path)
        except (OSError, RuntimeError, ValueError) as error:
            try:
                connection.close()
            except HidError:
                pass  # Preserve the opening failure as the actionable error.
            raise HidOperationError(f"HID open failed: {error}") from error
        return connection

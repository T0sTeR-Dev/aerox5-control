"""Discovery through python-hidapi, with no device-handle operations."""

from importlib import import_module
from typing import cast

from aerox5_control.transport.interfaces import EnumerationBackend, HidInterface


class HidError(Exception):
    """An HID backend could not be loaded or enumerated."""


class HidBackendUnavailable(HidError):
    """The required Python binding or native library is unavailable."""


class HidEnumerationError(HidError):
    """The backend failed to enumerate devices."""


class HidApiTransport:
    """Enumerate generic HID metadata; never instantiate or open a device."""

    def __init__(self, backend: EnumerationBackend | None = None) -> None:
        self._backend = backend

    def enumerate(
        self, vendor_id: int = 0, product_id: int = 0
    ) -> tuple[HidInterface, ...]:
        """Return every backend entry; zero IDs mean no filter for that ID."""
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

        try:
            records = backend.enumerate(vendor_id, product_id)
        except (OSError, RuntimeError) as error:
            raise HidEnumerationError(f"HID enumeration failed: {error}") from error

        return tuple(HidInterface.from_enumeration(record) for record in records)

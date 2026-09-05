"""HID metadata and discovery contracts, independent of vendor protocols."""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import NotRequired, Protocol, TypedDict


class HidEnumerationRecord(TypedDict):
    """The HIDAPI enumeration fields consumed by this application."""

    vendor_id: int
    product_id: int
    path: bytes | str
    interface_number: NotRequired[int | None]
    usage_page: NotRequired[int | None]
    usage: NotRequired[int | None]
    manufacturer_string: NotRequired[str | None]
    product_string: NotRequired[str | None]
    serial_number: NotRequired[str | None]


@dataclass(frozen=True, slots=True)
class HidInterface:
    """One enumeration entry; a HID path is opaque and need not be unique."""

    vendor_id: int
    product_id: int
    interface_number: int | None
    usage_page: int | None
    usage: int | None
    manufacturer_string: str | None
    product_string: str | None
    serial_number: str | None
    path: bytes | str

    @classmethod
    def from_enumeration(cls, record: HidEnumerationRecord) -> "HidInterface":
        """Copy metadata without querying an interface for missing fields."""
        interface_number = record.get("interface_number")
        return cls(
            vendor_id=record["vendor_id"],
            product_id=record["product_id"],
            interface_number=None if interface_number == -1 else interface_number,
            usage_page=record.get("usage_page"),
            usage=record.get("usage"),
            manufacturer_string=record.get("manufacturer_string") or None,
            product_string=record.get("product_string") or None,
            serial_number=record.get("serial_number") or None,
            path=record["path"],
        )


class EnumerationBackend(Protocol):
    """The only operation needed from python-hidapi."""

    def enumerate(
        self, vendor_id: int = 0, product_id: int = 0
    ) -> list[HidEnumerationRecord]: ...


class HidDiscovery(Protocol):
    """Transport interface consumed by device discovery."""

    def enumerate(
        self, vendor_id: int = 0, product_id: int = 0
    ) -> tuple[HidInterface, ...]: ...


class HidConnection(Protocol):
    """Report I/O on a single already-selected interface."""

    def write_output(self, payload: bytes, *, report_id: int = 0) -> None: ...

    def read_input(self, max_length: int, *, timeout_ms: int) -> bytes: ...

    def close(self) -> None: ...


class HidTransport(HidDiscovery, Protocol):
    def open_path(self, path: bytes | str) -> AbstractContextManager[HidConnection]: ...

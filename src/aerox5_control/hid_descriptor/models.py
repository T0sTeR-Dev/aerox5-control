"""Report layout summaries; sizes include constant fields and padding."""

from dataclasses import dataclass
from typing import Literal

ReportKind = Literal["input", "output", "feature"]


def is_vendor_page(page: int | None) -> bool:
    return page is not None and 0xFF00 <= page <= 0xFFFF


def usage_page_label(page: int | None) -> str:
    if page is None:
        return "unavailable"
    if is_vendor_page(page):
        return "vendor-specific"
    names = {
        0x01: "Generic Desktop",
        0x07: "Keyboard/Keypad",
        0x08: "LEDs",
        0x09: "Button",
        0x0C: "Consumer",
    }
    if page in names:
        return f"standard ({names[page]})"
    return "non-vendor (standard/reserved range)"


@dataclass(frozen=True, slots=True)
class Collection:
    kind: int
    usage_page: int | None
    usage: int | None
    depth: int

    @property
    def label(self) -> str:
        names = {(1, 2): "Mouse", (1, 6): "Keyboard", (0x0C, 1): "Consumer Control"}
        if is_vendor_page(self.usage_page):
            return "Vendor-specific"
        return names.get((self.usage_page, self.usage), "Other/unknown")


@dataclass(frozen=True, slots=True)
class ReportLayout:
    kind: ReportKind
    report_id: int | None
    payload_bits: int

    @property
    def payload_bytes(self) -> int:
        return (self.payload_bits + 7) // 8

    @property
    def wire_bytes(self) -> int:
        """Include a report ID byte only for explicitly numbered reports."""
        return self.payload_bytes + (self.report_id is not None)


@dataclass(frozen=True, slots=True)
class DescriptorInfo:
    size: int
    sha256: str
    collections: tuple[Collection, ...]
    usage_pages: tuple[int, ...]
    reports: tuple[ReportLayout, ...]

    @property
    def vendor_application(self) -> bool:
        return any(
            item.kind == 1 and is_vendor_page(item.usage_page)
            for item in self.collections
        )

    @property
    def configuration_candidate(self) -> bool:
        """A structural hint only; this establishes no protocol semantics."""
        return self.vendor_application and any(
            item.kind in ("output", "feature") for item in self.reports
        )

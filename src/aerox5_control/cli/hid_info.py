"""Human-readable descriptor summaries and explicitly tentative role assessment."""

from aerox5_control.application.hid_info import InterfaceInspection
from aerox5_control.hid_descriptor.models import usage_page_label


def _hex(value: int | None) -> str:
    return "unavailable" if value is None else f"0x{value:04x}"


def format_descriptor(inspection: InterfaceInspection) -> str:
    lines = []
    for entry in inspection.entries:
        lines.append(
            f"  Enumerated usage: {_hex(entry.hid.usage_page)} / "
            f"{_hex(entry.hid.usage)}"
            f" - {usage_page_label(entry.hid.usage_page)}"
        )
    if inspection.snapshot:
        lines.append(f"  Descriptor source: {inspection.snapshot.source}")
        if inspection.snapshot.usb_parent:
            lines.append(f"  USB device: {inspection.snapshot.usb_parent}")
    if inspection.error:
        lines.append(f"  Descriptor unavailable/unsupported: {inspection.error}")
        lines.append("  Report sizes and configuration role: unknown")
        return "\n".join(lines)

    descriptor = inspection.descriptor
    assert descriptor is not None
    lines.extend(
        [
            f"  Report descriptor: {descriptor.size} bytes",
            f"  Descriptor SHA-256: {descriptor.sha256}",
            "  Descriptor usage pages:",
        ]
    )
    for page in descriptor.usage_pages:
        lines.append(f"    {_hex(page)}: {usage_page_label(page)}")
    lines.append("  Application collections:")
    applications = [item for item in descriptor.collections if item.kind == 1]
    for item in applications:
        lines.append(
            f"    {item.label}: page {_hex(item.usage_page)}, usage {_hex(item.usage)}"
        )
    if not applications:
        lines.append("    none declared")
    ids = sorted(
        {item.report_id for item in descriptor.reports if item.report_id is not None}
    )
    lines.append(
        "  Report IDs: "
        + (", ".join(f"0x{value:02x}" for value in ids) if ids else "none (unnumbered)")
    )
    for kind in ("input", "output", "feature"):
        reports = [item for item in descriptor.reports if item.kind == kind]
        lines.append(f"  {kind.capitalize()} reports:")
        if not reports:
            lines.append("    none declared")
        for report in reports:
            label = (
                "unnumbered"
                if report.report_id is None
                else f"ID 0x{report.report_id:02x}"
            )
            lines.append(
                f"    {label}: {report.payload_bits} payload bits, "
                f"{report.payload_bytes} payload bytes, {report.wire_bytes} wire bytes"
            )
    if descriptor.configuration_candidate:
        lines.append(
            "  Role: strong configuration candidate (uncertain): vendor-specific "
            "application with output/feature reports; protocol not verified."
        )
    elif descriptor.vendor_application:
        lines.append("  Role: vendor-specific input; purpose unverified.")
    else:
        lines.append(
            "  Role: standard/other application; no configuration role established."
        )
    return "\n".join(lines)


def format_candidates(inspections: tuple[InterfaceInspection, ...]) -> str:
    candidates = [
        item
        for item in inspections
        if item.descriptor is not None and item.descriptor.configuration_candidate
    ]
    lines = ["Configuration candidates (descriptor evidence only; uncertain):"]
    if not candidates:
        lines.append("  None established from the available descriptors.")
    for item in candidates:
        hid = item.entries[0].hid
        path = (
            hid.path.decode(errors="backslashreplace")
            if isinstance(hid.path, bytes)
            else hid.path
        )
        lines.append(
            f"  {path}, USB interface {hid.interface_number}: "
            "vendor application + output/feature"
        )
    if any(item.error for item in inspections):
        lines.append(
            "  Inspection incomplete: unavailable descriptors "
            "may hide other candidates."
        )
    if len(candidates) > 1:
        lines.append("  Multiple candidates; no unique interface selected.")
    return "\n".join(lines)

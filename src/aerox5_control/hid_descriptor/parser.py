"""Parse HID 1.11 short items to summarize collections and report lengths.

No field values or vendor command semantics are inferred. Unsupported items are
rejected instead of returning potentially misleading partial report sizes.
"""

from dataclasses import dataclass, replace
from hashlib import sha256

from aerox5_control.hid_descriptor.models import (
    Collection,
    DescriptorInfo,
    ReportKind,
    ReportLayout,
)

MAX_DESCRIPTOR_SIZE = 4096


class DescriptorParseError(ValueError):
    """A descriptor is malformed or outside the supported summary grammar."""


@dataclass
class _Globals:
    usage_page: int | None = None
    report_size: int = 0
    report_count: int = 0
    report_id: int | None = None


def parse_descriptor(data: bytes) -> DescriptorInfo:
    """Sum Report Size * Report Count per type/ID, including constant padding."""
    if not data or len(data) > MAX_DESCRIPTOR_SIZE:
        raise DescriptorParseError("Descriptor must contain 1 to 4096 bytes")

    state = _Globals()
    stack: list[_Globals] = []
    collections = []
    pages: set[int] = set()
    totals: dict[tuple[ReportKind, int | None], int] = {}
    local_usage: tuple[int | None, int] | None = None
    depth = 0
    offset = 0
    kinds: dict[int, ReportKind] = {8: "input", 9: "output", 11: "feature"}

    while offset < len(data):
        start = offset
        prefix = data[offset]
        offset += 1
        if prefix == 0xFE:
            raise DescriptorParseError(f"Unsupported long item at byte {start}")
        size = (0, 1, 2, 4)[prefix & 3]
        if offset + size > len(data):
            raise DescriptorParseError(f"Truncated item at byte {start}")
        value = int.from_bytes(data[offset : offset + size], "little")
        offset += size
        item_type = (prefix >> 2) & 3
        tag = prefix >> 4

        if item_type == 1:  # Global state persists until changed or popped.
            if tag in (10, 11):
                if size:
                    raise DescriptorParseError(f"Invalid Push/Pop at byte {start}")
                if tag == 10:
                    stack.append(replace(state))
                elif stack:
                    state = stack.pop()
                else:
                    raise DescriptorParseError(f"Pop without Push at byte {start}")
            elif tag <= 9:
                if not size:
                    raise DescriptorParseError(f"Empty global item at byte {start}")
                if tag == 0:
                    if value > 0xFFFF:
                        raise DescriptorParseError("Usage page exceeds 16 bits")
                    state.usage_page = value
                    pages.add(value)
                elif tag == 7:
                    state.report_size = value
                elif tag == 8:
                    if size != 1 or not 1 <= value <= 255:
                        raise DescriptorParseError("Report ID must be 1 to 255")
                    state.report_id = value
                elif tag == 9:
                    state.report_count = value
                # Logical/physical limits and units do not affect bit totals.
            else:
                raise DescriptorParseError(f"Unknown global item at byte {start}")
        elif item_type == 2:
            if tag not in (0, 1, 2, 3, 4, 5, 7, 8, 9) or not size:
                raise DescriptorParseError(f"Unsupported local item at byte {start}")
            if tag in (0, 1):  # Usage or the first usage of a range.
                page, usage = (
                    (value >> 16, value & 0xFFFF)
                    if size == 4
                    else (state.usage_page, value)
                )
                if page is not None:
                    pages.add(page)
                if local_usage is None:
                    local_usage = (page, usage)
        elif item_type == 0:
            if tag in kinds:
                if not size or not state.report_size or not state.report_count:
                    raise DescriptorParseError(f"Incomplete report at byte {start}")
                key = (kinds[tag], state.report_id)
                totals[key] = (
                    totals.get(key, 0) + state.report_size * state.report_count
                )
            elif tag == 10:
                if size != 1:
                    raise DescriptorParseError(f"Invalid collection at byte {start}")
                page, usage = local_usage if local_usage else (None, None)
                collections.append(Collection(value, page, usage, depth))
                depth += 1
            elif tag == 12:
                if size or not depth:
                    raise DescriptorParseError(f"Unmatched End Collection at {start}")
                depth -= 1
            else:
                raise DescriptorParseError(f"Unknown main item at byte {start}")
            local_usage = None  # All Main items consume local state.
        else:
            raise DescriptorParseError(f"Reserved item type at byte {start}")

    if depth or stack:
        raise DescriptorParseError("Unclosed Collection or Push")
    ids = {report_id for _, report_id in totals}
    if None in ids and len(ids) > 1:
        raise DescriptorParseError("Mixed numbered and unnumbered reports")
    reports = tuple(
        ReportLayout(kind, report_id, bits)
        for (kind, report_id), bits in sorted(
            totals.items(), key=lambda item: (item[0][0], item[0][1] or 0)
        )
    )
    return DescriptorInfo(
        len(data),
        sha256(data).hexdigest(),
        tuple(collections),
        tuple(sorted(pages)),
        reports,
    )

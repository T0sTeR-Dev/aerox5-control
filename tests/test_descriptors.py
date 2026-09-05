"""Captured descriptor regression tests and synthetic HID item edge cases."""

import pytest

from aerox5_control.hid_descriptor.models import usage_page_label
from aerox5_control.hid_descriptor.parser import DescriptorParseError, parse_descriptor


@pytest.mark.parametrize(
    ("number", "size", "expected"),
    [
        (0, 98, {"input": 12}),
        (1, 59, {"input": 33, "output": 1}),
        (2, 25, {"input": 4}),
        (3, 37, {"input": 64, "output": 64, "feature": 512}),
        (4, 21, {"input": 64}),
    ],
)
def test_captured_receiver_layouts(captured_interfaces, number, size, expected):
    descriptor = parse_descriptor(
        bytes.fromhex(captured_interfaces[number]["descriptor_hex"])
    )
    assert descriptor.size == size
    assert {
        report.kind: report.payload_bytes for report in descriptor.reports
    } == expected
    assert all(report.report_id is None for report in descriptor.reports)
    assert all(
        report.wire_bytes == report.payload_bytes for report in descriptor.reports
    )


def test_roles_are_inferred_from_collections_not_interface_numbers(captured_interfaces):
    descriptors = [
        parse_descriptor(bytes.fromhex(item["descriptor_hex"]))
        for item in captured_interfaces
    ]
    assert [info.collections[0].label for info in descriptors] == [
        "Mouse",
        "Keyboard",
        "Consumer Control",
        "Vendor-specific",
        "Vendor-specific",
    ]
    assert [info.configuration_candidate for info in descriptors] == [
        False,
        False,
        False,
        True,
        False,
    ]
    # The normal mouse report also contains vendor fields; this does not make
    # the mouse application a configuration interface.
    assert 0xFFC1 in descriptors[0].usage_pages
    assert not descriptors[0].vendor_application


def test_numbered_reports_sum_fields_and_count_padding_before_rounding():
    # ID 7: three data bits plus five constant bits; output and feature use
    # the same ID but have independent sizes. ID 8 is a second input report.
    info = parse_descriptor(
        bytes.fromhex(
            "85 07 75 01 95 03 81 02 95 05 81 01 "
            "75 08 95 02 91 02 75 01 95 03 b1 02 "
            "85 08 75 08 95 04 81 02"
        )
    )
    assert {
        (r.kind, r.report_id): (r.payload_bits, r.payload_bytes, r.wire_bytes)
        for r in info.reports
    } == {
        ("input", 7): (8, 1, 2),
        ("input", 8): (32, 4, 5),
        ("output", 7): (16, 2, 3),
        ("feature", 7): (3, 1, 2),
    }


def test_push_pop_restores_report_size_count_id_and_usage_page():
    info = parse_descriptor(
        bytes.fromhex(
            "05 01 85 01 75 08 95 02 a4 "
            "06 00 ff 85 02 75 10 95 01 09 01 a1 01 81 02 c0 "
            "b4 09 02 a1 01 81 02 81 01 c0"
        )
    )
    assert [(r.report_id, r.payload_bits) for r in info.reports] == [(1, 32), (2, 16)]
    assert [(c.usage_page, c.usage) for c in info.collections] == [(0xFF00, 1), (1, 2)]


def test_four_byte_usage_overrides_page_and_locals_reset_after_main_items():
    info = parse_descriptor(
        bytes.fromhex(
            "05 01 0b 01 00 c0 ff a1 01 c0 a1 01 c0 75 08 97 00 02 00 00 b1 02"
        )
    )
    assert (info.collections[0].usage_page, info.collections[0].usage) == (0xFFC0, 1)
    assert info.collections[1].usage_page is None
    assert info.reports[0].payload_bytes == 512


def test_usage_page_is_bound_when_local_usage_is_declared():
    info = parse_descriptor(bytes.fromhex("05 01 09 02 06 c0 ff a1 01 c0"))
    assert info.collections[0].label == "Mouse"
    assert not info.vendor_application


@pytest.mark.parametrize(
    "data",
    [
        "",
        "75",
        "97 01 00",
        "fe 00 00",
        "85 00",
        "86 01 00",
        "b4",
        "a4",
        "a1 01",
        "c0",
        "81 02",
        "fc",
        "05 01 a9 01",
        "75 08 95 01 81 02 85 01 81 02",
    ],
)
def test_malformed_or_unsupported_descriptors_do_not_return_partial_sizes(data):
    with pytest.raises(DescriptorParseError):
        parse_descriptor(bytes.fromhex(data))


def test_oversized_descriptor_is_rejected():
    with pytest.raises(DescriptorParseError):
        parse_descriptor(b"\x00" * 4097)


@pytest.mark.parametrize(
    ("page", "label"),
    [
        (None, "unavailable"),
        (1, "standard (Generic Desktop)"),
        (0xFF00, "vendor-specific"),
        (0xFFFF, "vendor-specific"),
        (0xFEFF, "non-vendor (standard/reserved range)"),
    ],
)
def test_usage_page_classification(page, label):
    assert usage_page_label(page) == label

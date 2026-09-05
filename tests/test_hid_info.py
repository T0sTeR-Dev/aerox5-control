"""End-to-end descriptor inspection with captured bytes and mock enumeration."""

from unittest.mock import Mock, call

import pytest

from aerox5_control.application.hid_info import inspect_hid_descriptors
from aerox5_control.cli.main import main
from aerox5_control.transport.interfaces import HidInterface
from aerox5_control.transport.linux_sysfs import DescriptorReadError


@pytest.fixture
def receiver(hid_backend, captured_interfaces, record, make_sysfs):
    records = []
    for item in captured_interfaces:
        entry = {
            **record,
            **{key: value for key, value in item.items() if key != "descriptor_hex"},
            "path": f"/dev/hidraw{item['interface_number'] + 20}".encode(),
        }
        make_sysfs(
            HidInterface.from_enumeration(entry), bytes.fromhex(item["descriptor_hex"])
        )
        records.append(entry)
    hid_backend.enumerate.return_value = records
    return records


def test_hid_info_prints_captured_receiver_layout_and_candidate(
    receiver, hid_backend, capsys
):
    assert main(["hid-info"]) == 0
    output = capsys.readouterr()
    for expected in [
        "5 distinct HID paths (5 enumeration entries)",
        "Mouse:",
        "Keyboard:",
        "Consumer Control:",
        "0xffc0: vendor-specific",
        "0xffc1: vendor-specific",
        "Report IDs: none (unnumbered)",
        "512 payload bytes, 512 wire bytes",
        "64 payload bytes, 64 wire bytes",
        "Report descriptor: 98 bytes",
        "Descriptor source:",
        "Descriptor SHA-256:",
        "USB interface 3",
        "strong configuration candidate (uncertain)",
        "protocol not verified",
        "HID path: /dev/hidraw23",
        "Manufacturer string: SteelSeries",
        "Serial number: synthetic-serial",
    ]:
        assert expected in output.out
    assert output.err == ""
    assert hid_backend.mock_calls == [
        call.enumerate(0x1038, 0x1852),
        call.enumerate(0x1038, 0x1854),
    ]


def test_duplicate_collection_entries_are_not_counted_as_interfaces(
    receiver, hid_backend
):
    hid_backend.enumerate.return_value = receiver + [{**receiver[3], "usage": 2}]
    inspections = inspect_hid_descriptors()
    assert len(inspections) == 5
    assert len(inspections[3].entries) == 2


def test_candidate_does_not_depend_on_interface_number(
    record, make_sysfs, captured_interfaces, hid_backend
):
    entry = {
        **record,
        "interface_number": 9,
        "path": b"/dev/hidraw40",
        "product_id": 0x1854,
    }
    make_sysfs(
        HidInterface.from_enumeration(entry),
        bytes.fromhex(captured_interfaces[3]["descriptor_hex"]),
    )
    hid_backend.enumerate.return_value = [entry]
    (inspection,) = inspect_hid_descriptors()
    assert inspection.entries[0].connection == "wired"
    assert inspection.entries[0].hid.interface_number == 9
    assert inspection.descriptor.configuration_candidate


def test_missing_descriptor_does_not_hide_other_interfaces(
    receiver, hid_backend, capsys
):
    hid_backend.enumerate.return_value = receiver + [
        {**receiver[0], "path": b"/dev/hidraw999"}
    ]
    assert main(["hid-info"]) == 1
    output = capsys.readouterr().out
    assert "6 distinct HID paths" in output
    assert "Descriptor unavailable/unsupported" in output
    assert "USB interface 3" in output
    assert "Inspection incomplete" in output


def test_malformed_descriptor_produces_unknown_sizes(
    record, hid_backend, make_sysfs, capsys
):
    entry = {**record, "path": b"/dev/hidraw41"}
    make_sysfs(HidInterface.from_enumeration(entry), b"\x75")
    hid_backend.enumerate.return_value = [entry]
    assert main(["hid-info"]) == 1
    output = capsys.readouterr().out
    assert "Truncated item" in output
    assert "Report sizes and configuration role: unknown" in output


def test_unrelated_devices_never_reach_descriptor_reader(record, hid_backend):
    hid_backend.enumerate.return_value = [
        {**record, "vendor_id": 1},
        {**record, "product_id": 0x9999},
    ]
    source = Mock(spec_set=["read"])
    assert inspect_hid_descriptors(source=source) == ()
    assert source.mock_calls == []


def test_descriptor_read_occurs_once_for_shared_path(receiver, hid_backend):
    hid_backend.enumerate.return_value = [receiver[3], {**receiver[3], "usage": 2}]
    source = Mock(spec_set=["read"])
    source.read.side_effect = DescriptorReadError("synthetic unavailable descriptor")
    (inspection,) = inspect_hid_descriptors(source=source)
    assert len(inspection.entries) == 2
    source.read.assert_called_once()


def test_conflicting_same_path_identity_is_not_inspected(receiver, hid_backend):
    hid_backend.enumerate.return_value = [
        receiver[3],
        {**receiver[3], "interface_number": 99},
    ]
    source = Mock(spec_set=["read"])
    (inspection,) = inspect_hid_descriptors(source=source)
    assert "Conflicting identities" in inspection.error
    assert source.mock_calls == []


def test_no_matches_hid_info(hid_backend, capsys):
    assert main(["hid-info"]) == 0
    assert "No matching" in capsys.readouterr().out

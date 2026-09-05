"""CLI integration uses the strict mock backend supplied to every test."""

from unittest.mock import call

import pytest

from aerox5_control.cli.main import main
from aerox5_control.transport import hidapi_backend


def test_inspect_prints_every_field_and_interface(hid_backend, record, capsys):
    hid_backend.enumerate.return_value = [
        record,
        {**record, "product_id": 0x1854, "interface_number": 0, "path": b"/dev/wired"},
    ]

    assert main(["inspect"]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    for expected in (
        "Discovered 2 matching HID interface entries.",
        "Interface 1: Aerox 5 Wireless (2.4 GHz)",
        "Vendor ID: 0x1038",
        "Product ID: 0x1852",
        "Interface number: 4",
        "Usage page: 0xff00",
        "Usage: 0x0001",
        "Manufacturer string: SteelSeries",
        "Product string: SteelSeries Aerox 5 Wireless",
        "Serial number: synthetic-serial",
        "HID path: /dev/hidraw-test0",
        "Interface 2: Aerox 5 Wireless (wired)",
        "Product ID: 0x1854",
        "Interface number: 0",
        "HID path: /dev/wired",
    ):
        assert expected in output.out
    assert hid_backend.mock_calls == [call.enumerate(0x1038, 0)]


def test_inspect_handles_missing_metadata_and_non_utf8_path(hid_backend, capsys):
    hid_backend.enumerate.return_value = [
        {"vendor_id": 0x1038, "product_id": 0x1852, "path": b"/dev/mock-\xff"}
    ]

    assert main(["inspect"]) == 0

    output = capsys.readouterr().out
    assert output.count("(unavailable)") == 6
    assert r"HID path: /dev/mock-\xff" in output


def test_inspect_handles_no_matches(hid_backend, capsys):
    assert main(["inspect"]) == 0
    output = capsys.readouterr()
    assert "No matching Aerox 5 Wireless HID interfaces reported" in output.out
    assert output.err == ""


def test_inspect_reports_backend_failure(hid_backend, capsys):
    hid_backend.enumerate.side_effect = OSError("enumeration unavailable")
    assert main(["inspect"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "HID enumeration failed: enumeration unavailable" in output.err


def test_inspect_reports_missing_dependency(monkeypatch, capsys):
    def missing_module(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(hidapi_backend, "import_module", missing_module)
    assert main(["inspect"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Install python-hidapi" in output.err


@pytest.mark.parametrize(
    ("args", "status"),
    [(["--help"], 0), (["inspect", "--help"], 0), ([], 2), (["write"], 2)],
)
def test_argument_handling_never_loads_hid(monkeypatch, hid_backend, args, status):
    def forbid_import(name):
        pytest.fail(f"Argument handling imported {name}")

    monkeypatch.setattr(hidapi_backend, "import_module", forbid_import)
    with pytest.raises(SystemExit) as caught:
        main(args)
    assert caught.value.code == status
    assert hid_backend.mock_calls == []

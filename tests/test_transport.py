"""Generic enumeration and backend failure behavior."""

from unittest.mock import call

import pytest

from aerox5_control.transport import hidapi_backend
from aerox5_control.transport.hidapi_backend import (
    HidApiTransport,
    HidBackendUnavailable,
    HidEnumerationError,
)
from aerox5_control.transport.interfaces import HidInterface


def test_generic_transport_preserves_all_metadata_and_other_vendors(
    hid_backend, record
):
    record["vendor_id"] = 0x1234
    original = record.copy()
    hid_backend.enumerate.return_value = [record]

    interfaces = HidApiTransport().enumerate()

    assert interfaces == (HidInterface(**record),)
    assert record == original
    assert hid_backend.mock_calls == [call.enumerate(0, 0)]


def test_transport_forwards_filters_to_injected_backend(hid_backend):
    assert HidApiTransport(hid_backend).enumerate(0x1234, 0x5678) == ()
    assert hid_backend.mock_calls == [call.enumerate(0x1234, 0x5678)]


def test_missing_optional_metadata_does_not_trigger_queries(hid_backend):
    hid_backend.enumerate.return_value = [
        {"vendor_id": 0x1038, "product_id": 0x1854, "path": b"opaque-path"}
    ]

    (interface,) = HidApiTransport().enumerate()

    assert interface == HidInterface(
        vendor_id=0x1038,
        product_id=0x1854,
        interface_number=None,
        usage_page=None,
        usage=None,
        manufacturer_string=None,
        product_string=None,
        serial_number=None,
        path=b"opaque-path",
    )
    assert hid_backend.mock_calls == [call.enumerate(0, 0)]


@pytest.mark.parametrize("missing", [None, ""])
def test_empty_strings_and_unknown_interface_are_unavailable(
    hid_backend, record, missing
):
    record.update(
        interface_number=-1,
        manufacturer_string=missing,
        product_string=missing,
        serial_number=missing,
    )
    hid_backend.enumerate.return_value = [record]

    (interface,) = HidApiTransport().enumerate()

    assert interface.interface_number is None
    assert interface.manufacturer_string is None
    assert interface.product_string is None
    assert interface.serial_number is None


def test_zero_metadata_is_preserved(hid_backend, record):
    record.update(interface_number=0, usage_page=0, usage=0)
    hid_backend.enumerate.return_value = [record]
    (interface,) = HidApiTransport().enumerate()
    assert (interface.interface_number, interface.usage_page, interface.usage) == (
        0,
        0,
        0,
    )


@pytest.mark.parametrize("path", [b"/dev/hidraw-\xff", "/dev/hidraw-unicode-ä"])
def test_paths_are_preserved_without_decoding(hid_backend, record, path):
    record["path"] = path
    hid_backend.enumerate.return_value = [record]
    assert HidApiTransport().enumerate()[0].path == path


@pytest.mark.parametrize(
    "error", [OSError("permission denied"), RuntimeError("failed")]
)
def test_enumeration_error_retains_cause(hid_backend, error):
    hid_backend.enumerate.side_effect = error
    with pytest.raises(HidEnumerationError, match=str(error)) as caught:
        HidApiTransport().enumerate()
    assert caught.value.__cause__ is error


@pytest.mark.parametrize(
    "error", [ImportError("missing hid"), OSError("missing library")]
)
def test_backend_load_failure_is_actionable(monkeypatch, error):
    def fail_import(name):
        assert name == "hidraw"
        raise error

    monkeypatch.setattr(hidapi_backend, "import_module", fail_import)
    with pytest.raises(HidBackendUnavailable, match="Install python-hidapi") as caught:
        HidApiTransport().enumerate()
    assert caught.value.__cause__ is error


def test_prefers_explicit_hidraw_backend(monkeypatch, hid_backend):
    imports = []

    def import_hidraw(name):
        imports.append(name)
        assert name == "hidraw"
        return hid_backend

    monkeypatch.setattr(hidapi_backend, "import_module", import_hidraw)
    transport = HidApiTransport()
    transport.enumerate()
    transport.enumerate()
    assert imports == ["hidraw"]
    assert hid_backend.mock_calls == [call.enumerate(0, 0), call.enumerate(0, 0)]


def test_supports_arch_hidraw_only_module_name(monkeypatch, hid_backend):
    imports = []

    def import_arch_backend(name):
        imports.append(name)
        if name == "hidraw":
            raise ModuleNotFoundError("No module named 'hidraw'", name="hidraw")
        assert name == "hid"
        return hid_backend

    monkeypatch.setattr(hidapi_backend, "import_module", import_arch_backend)
    assert HidApiTransport().enumerate() == ()
    assert imports == ["hidraw", "hid"]
    assert hid_backend.mock_calls == [call.enumerate(0, 0)]


def test_broken_hidraw_does_not_fall_back_to_libusb(monkeypatch):
    imports = []

    def broken_hidraw(name):
        imports.append(name)
        raise ModuleNotFoundError("missing dependency", name="internal_dependency")

    monkeypatch.setattr(hidapi_backend, "import_module", broken_hidraw)
    with pytest.raises(HidBackendUnavailable):
        HidApiTransport().enumerate()
    assert imports == ["hidraw"]


def test_construction_does_not_load_backend(monkeypatch):
    def forbid_import(name):
        pytest.fail(f"Backend imported before enumeration: {name}")

    monkeypatch.setattr(hidapi_backend, "import_module", forbid_import)
    HidApiTransport()

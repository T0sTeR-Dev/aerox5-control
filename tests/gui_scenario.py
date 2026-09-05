"""Native GTK scenarios run only by the private-display test harness."""

import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock, call


def main():
    assert os.environ["GDK_BACKEND"] == "broadway"
    assert not os.environ.get("DISPLAY")
    assert not os.environ.get("WAYLAND_DISPLAY")
    # Child processes do not inherit pytest monkeypatches. Install fail-closed
    # guards BEFORE importing any application module, in addition to fake services.
    sys.modules["hid"] = Mock(spec_set=[])
    sys.modules["hidraw"] = Mock(spec_set=[])

    from aerox5_control.application import services
    from aerox5_control.gui._gtk import Gio, GLib
    from aerox5_control.gui.application import AeroxApplication

    api = Mock(spec_set=["get_status", "set_dpi_presets", "set_polling_rate"])
    services.get_status = api.get_status
    services.set_dpi_presets = api.set_dpi_presets
    services.set_polling_rate = api.set_polling_rate

    def status(*, connected=False, level=40, charging=False, reason=None):
        return SimpleNamespace(
            interface=SimpleNamespace(
                connection="2.4 GHz",
                hid=SimpleNamespace(
                    product_string="SteelSeries Aerox 5 Wireless",
                    vendor_id=0x1038,
                    product_id=0x1852,
                ),
            )
            if connected
            else None,
            battery=SimpleNamespace(
                available=connected and reason is None,
                level=level,
                charging=charging,
                reason=reason or "Receiver configuration interface not found",
            ),
        )

    api.get_status.return_value = status()
    api.set_dpi_presets.return_value = SimpleNamespace(completed=True)
    api.set_polling_rate.return_value = SimpleNamespace(completed=True)
    app = AeroxApplication()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    assert app.register(None)
    app.activate()
    window = app.get_active_window()
    assert window is not None

    def drain():
        context = GLib.MainContext.default()
        deadline = time.monotonic() + 5
        while window.controller.state.busy or context.pending():
            assert time.monotonic() < deadline, "GUI operation did not complete"
            context.iteration(False)
            time.sleep(0.001)

    def displayed(field):
        return window.overview_rows[field].get_subtitle()

    try:
        drain()
        assert window.get_title() == "Aerox 5 Control"
        assert window.stack.get_pages().get_n_items() == 2
        assert displayed("state") == "Disconnected"
        assert displayed("battery") == displayed("charging") == "Unavailable"
        assert api.mock_calls == [call.get_status()]  # No startup setting writes.
        assert all(entry.get_text() == "" for entry in window.preset_entries)
        assert window.polling_choice.get_selected() == 0

        # Refresh rediscovers after reconnecting; second activation only presents.
        app.activate()
        assert api.mock_calls == [call.get_status()]
        api.get_status.return_value = status(connected=True, charging=True)
        window.refresh_button.emit("clicked")
        assert not window.refresh_button.get_sensitive()
        assert not window.dpi_group.get_sensitive()
        drain()
        assert displayed("state") == "Connected"
        assert displayed("connection") == "2.4 GHz"
        assert displayed("vendor_id") == "0x1038"
        assert displayed("product_id") == "0x1852"
        assert displayed("battery") == "40%"
        assert displayed("charging") == "Yes"

        api.reset_mock()
        window.stack.set_visible_child_name("sensitivity")
        window.preset_count.set_selected(4)
        assert all(entry.get_visible() for entry in window.preset_entries)
        window.preset_count.set_selected(1)
        assert [entry.get_visible() for entry in window.preset_entries] == [
            True,
            True,
            False,
            False,
            False,
        ]
        window.preset_entries[0].set_text("850")
        window.preset_entries[1].set_text("1600")
        assert not api.mock_calls  # Editing never writes.
        window.dpi_apply.emit("clicked")
        assert window.controller.state.error
        assert window.preset_entries[0].get_text() == "850"  # Never rounded.
        assert not api.mock_calls

        window.preset_entries[0].set_text("800")
        window.dpi_apply.emit("clicked")
        window.dpi_apply.emit("clicked")  # Busy guard rejects duplicate signals.
        drain()
        assert api.mock_calls == [call.set_dpi_presets((800, 1600))]
        assert "DPI preset request sent" in window.feedback.get_text()
        assert "not been read back" in window.feedback.get_text()

        api.reset_mock()
        model = window.polling_choice.get_model()
        assert [model.get_string(i) for i in range(model.get_n_items())] == [
            "Choose a rate…",
            "125 Hz",
            "250 Hz",
            "500 Hz",
            "1000 Hz",
        ]
        window.polling_apply.emit("clicked")  # No rate chosen.
        assert window.controller.state.error
        assert not api.mock_calls
        window.polling_choice.set_selected(4)
        assert not api.mock_calls
        window.polling_apply.emit("clicked")
        window.polling_apply.emit("clicked")
        drain()
        assert api.mock_calls == [call.set_polling_rate(1000)]
        assert "Polling-rate request sent" in window.feedback.get_text()

        api.set_polling_rate.return_value = SimpleNamespace(
            completed=False,
            write_attempted=True,
            error="device disconnected",
        )
        window.polling_apply.emit("clicked")
        drain()
        assert displayed("state") == "Disconnected"
        assert displayed("battery") == displayed("charging") == "Unavailable"
        assert "may already have changed" in window.feedback.get_text()
        assert window.refresh_button.get_sensitive()

        for reason, message in (
            ("permission denied", "Permission denied"),
            ("HID input read timed out", "did not respond in time"),
            ("Malformed battery response", "Battery and charging"),
        ):
            api.get_status.return_value = status(connected=True, reason=reason)
            window.refresh_button.emit("clicked")
            drain()
            assert displayed("battery") == displayed("charging") == "Unavailable"
            assert message in window.feedback.get_text()

        api.get_status.return_value = status(connected=True)
        window.refresh_button.emit("clicked")
        drain()
        assert displayed("state") == "Connected"
        assert displayed("charging") == "No"
        assert window.preset_entries[0].get_text() == "800"  # Session draft survives.
        assert not sys.modules["hid"].mock_calls
        assert not sys.modules["hidraw"].mock_calls
    finally:
        window.close()
        app.quit()
    print("native GUI scenarios passed")


if __name__ == "__main__":
    main()

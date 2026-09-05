"""Native single-window application, without background or startup services."""

from aerox5_control.gui._gtk import Adw, GLib
from aerox5_control.gui.window import ControlWindow


class AeroxApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.aerox5_control.Aerox5Control")
        GLib.set_application_name("Aerox 5 Control")

    def do_activate(self) -> None:
        window = self.get_active_window()
        if window is None:
            window = ControlWindow(self)
            window.controller.refresh()  # One status refresh; no setting writes.
        window.present()

    def do_shutdown(self) -> None:
        for window in self.get_windows():
            window.controller.close()
        Adw.Application.do_shutdown(self)

"""Select native library versions before importing their introspection bindings."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

__all__ = ["Adw", "GLib", "Gio", "Gtk"]

"""Optional graphical entry point; the CLI never imports GTK."""

import sys


def main(argv: list[str] | None = None) -> int:
    try:
        from aerox5_control.gui._gtk import Adw
    except (ImportError, ValueError) as error:
        print(
            "Aerox 5 Control requires GTK4, Libadwaita, and PyGObject. "
            "On Arch install gtk4, libadwaita, and python-gobject; "
            "use a virtual environment with --system-site-packages.\n"
            f"{error}",
            file=sys.stderr,
        )
        return 1
    if (Adw.get_major_version(), Adw.get_minor_version()) < (1, 4):
        print("Aerox 5 Control requires Libadwaita 1.4 or newer.", file=sys.stderr)
        return 1

    from aerox5_control.gui.application import AeroxApplication

    return AeroxApplication().run(sys.argv if argv is None else argv)

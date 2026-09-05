"""Widgets bind only to desktop application state and explicit user actions."""

from aerox5_control.application.desktop import POLLING_RATES, PRESET_COUNTS
from aerox5_control.application.desktop_controller import (
    DesktopController,
    DesktopState,
)
from aerox5_control.gui._gtk import Adw, GLib, Gtk


class ControlWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(
            application=application,
            title="Aerox 5 Control",
            default_width=540,
            default_height=680,
        )
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Aerox 5 Control"))
        self.refresh_button = Gtk.Button(
            label="Refresh", tooltip_text="Refresh device status"
        )
        header.pack_start(self.refresh_button)
        self.spinner = Gtk.Spinner()
        header.pack_end(self.spinner)
        toolbar.add_top_bar(header)

        self.stack = Adw.ViewStack(vexpand=True)
        self.stack.add_titled_with_icon(
            self._build_overview(), "overview", "Overview", "input-mouse-symbolic"
        )
        self.stack.add_titled_with_icon(
            self._build_sensitivity(),
            "sensitivity",
            "Sensitivity",
            "preferences-system-symbolic",
        )
        switcher = Adw.ViewSwitcher(stack=self.stack, halign=Gtk.Align.CENTER)
        toolbar.add_top_bar(switcher)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self.stack)
        self.feedback = Gtk.Label(
            wrap=True,
            xalign=0,
            margin_start=24,
            margin_end=24,
            margin_top=8,
            margin_bottom=16,
            visible=False,
        )
        content.append(self.feedback)
        toolbar.set_content(content)
        self.set_content(toolbar)

        self.controller = DesktopController(self._render, GLib.idle_add)
        self.refresh_button.connect(
            "clicked", lambda _button: self.controller.refresh()
        )
        self.dpi_apply.connect("clicked", self._apply_dpi)
        self.polling_apply.connect("clicked", self._apply_polling)
        self.connect("close-request", self._close)
        self._render(self.controller.state)

    def _build_overview(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Device")
        self.overview_rows = {}
        for key, title in (
            ("name", "Device name"),
            ("state", "Status"),
            ("connection", "Connection"),
            ("vendor_id", "Vendor ID"),
            ("product_id", "Product ID"),
            ("battery", "Battery"),
            ("charging", "Charging"),
        ):
            row = Adw.ActionRow(title=title, use_markup=False)
            self.overview_rows[key] = row
            group.add(row)
        page.add(group)
        self.connection_note = Adw.PreferencesGroup()
        page.add(self.connection_note)
        return page

    @staticmethod
    def _choice_row(
        title: str, choices: tuple[str, ...]
    ) -> tuple[Adw.ActionRow, Gtk.DropDown]:
        row = Adw.ActionRow(title=title)
        dropdown = Gtk.DropDown.new_from_strings(choices)
        dropdown.set_valign(Gtk.Align.CENTER)
        row.add_suffix(dropdown)
        row.set_activatable_widget(dropdown)
        dropdown.set_tooltip_text(title)
        return row, dropdown

    def _build_sensitivity(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        self.dpi_group = Adw.PreferencesGroup(
            title="DPI presets to send",
            description="Enter 1–5 presets, from 100 to 18000 DPI in steps of 100. "
            "Applying selects the first preset.",
        )
        row, self.preset_count = self._choice_row(
            "Number of presets", tuple(str(count) for count in PRESET_COUNTS)
        )
        self.dpi_group.add(row)
        self.preset_entries = []
        for number in PRESET_COUNTS:
            entry = Adw.EntryRow(title=f"Preset {number} · DPI", visible=number == 1)
            entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
            self.preset_entries.append(entry)
            self.dpi_group.add(entry)
        self.preset_count.connect("notify::selected", self._update_preset_count)
        self.dpi_apply = Gtk.Button(label="Apply DPI presets", margin_top=12)
        self.dpi_apply.add_css_class("suggested-action")
        self.dpi_group.add(self.dpi_apply)
        page.add(self.dpi_group)

        self.polling_group = Adw.PreferencesGroup(title="Polling rate to send")
        row, self.polling_choice = self._choice_row(
            "Polling rate",
            ("Choose a rate…",) + tuple(f"{rate} Hz" for rate in POLLING_RATES),
        )
        self.polling_group.add(row)
        self.polling_apply = Gtk.Button(label="Apply polling rate", margin_top=12)
        self.polling_apply.add_css_class("suggested-action")
        self.polling_group.add(self.polling_apply)
        page.add(self.polling_group)
        page.add(
            Adw.PreferencesGroup(
                description="These are values you enter for this session. Current DPI "
                "and polling settings cannot be read from the mouse. "
                "Apply sends only the chosen setting; "
                "settings are not saved to onboard memory."
            )
        )
        return page

    def _update_preset_count(self, _dropdown, _property) -> None:
        count = self.preset_count.get_selected() + 1
        for index, entry in enumerate(self.preset_entries):
            entry.set_visible(index < count)

    def _apply_dpi(self, _button) -> None:
        count = self.preset_count.get_selected() + 1
        self.controller.apply_dpi(
            tuple(entry.get_text() for entry in self.preset_entries[:count])
        )

    def _apply_polling(self, _button) -> None:
        index = self.polling_choice.get_selected()
        rate = POLLING_RATES[index - 1] if 1 <= index <= len(POLLING_RATES) else None
        self.controller.apply_polling(rate)

    def _render(self, state: DesktopState) -> None:
        for key, row in self.overview_rows.items():
            row.set_subtitle(getattr(state.overview, key))
        self.connection_note.set_description(state.overview.message)
        self.spinner.set_spinning(state.busy)
        self.refresh_button.set_sensitive(not state.busy)
        self.dpi_group.set_sensitive(not state.busy)
        self.polling_group.set_sensitive(not state.busy)
        self.feedback.set_text(state.message)
        self.feedback.set_visible(bool(state.message))
        if state.error:
            self.feedback.add_css_class("error")
        else:
            self.feedback.remove_css_class("error")

    def _close(self, _window) -> bool:
        self.controller.close()
        return False

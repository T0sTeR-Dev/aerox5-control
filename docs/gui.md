# Aerox 5 Control v0.1

Launch the installed entry point as a normal desktop user:

```sh
.venv/bin/aerox5-control
```

GTK4, Libadwaita >= 1.4, and PyGObject >= 3.46 are required. Arch's native packages
are `gtk4`, `libadwaita`, and `python-gobject`. The optional Python `gui` extra
declares PyGObject; native GTK/Libadwaita libraries still come from the OS.
The virtual environment must expose these system bindings; see the README setup.
Missing bindings produce a terminal diagnostic. The CLI remains usable without
any GUI dependency.

## Window and user actions

The compact native window has two pages:

| Page | Contents and actions |
| --- | --- |
| Overview | Device name, connection state/type, VID/PID, battery, charging; Refresh |
| Sensitivity | Preset count, 1–5 DPI entry rows, explicit Apply DPI; polling selector and explicit Apply polling |

The first activation performs one existing status query. Activating the same
running window again only presents it. Subsequent refreshes require the Refresh
button; no timer, watcher, daemon, or automatic setting action is installed.

DPI entries start empty. The rate selector starts with “Choose a rate…”. Both
groups are labeled as values to send, and the page explains that their contents
are session drafts, not confirmed hardware state. Drafts survive Refresh and
page switches but are neither written to disk nor restored after closing. The
first preset is selected when a DPI list is applied. Hidden entries are excluded
from the submitted list. Increasing the count reveals the session's draft entries.

DPI text uses entry rows rather than a numeric widget that could normalize input
on focus loss. A whole decimal number is required in every active entry, followed
by the existing protocol validator: 1–5 values, 100–18000, exact steps of 100, and
membership in the established TrueMove Air mapping. Invalid input remains visible
and is rejected before any worker/hardware operation is scheduled. There is no
rounding. Polling choices reuse the existing supported-rate list.

Each Apply button submits only its own setting. Busy controls and a controller
guard prevent duplicate signals from queueing a second operation. Success means
the existing transaction completed, not that the setting was independently read
back or verified. After a write attempt, failures explicitly state that the
setting may already have changed. No retry, rollback, save, or extra query follows.

## Separation and threading

```text
gui/window.py                   GTK widgets and signal handlers
application/desktop_controller  One-operation scheduling and immutable UI state
application/desktop             Input validation and presentation adapter
application/services            Existing service API
devices/aerox5                  Existing device selection and transactions
protocol                        Existing encoding/decoding
transport                       Existing generic HIDAPI I/O
```

The GUI imports no HID, device, or protocol module. It receives display strings
and invokes Refresh, Apply DPI, or Apply polling through the application API.
Raw paths and packets stay outside GUI code and the normal overview.

The controller owns a `ThreadPoolExecutor(max_workers=1)`. It snapshots validated
input on the main thread, marks the window busy, and submits one service call.
The worker returns state/feedback without touching widgets. Completion is queued
with `GLib.idle_add`; only that main-thread callback updates state and widgets.
This follows the [PyGObject threading guidance](https://pygobject.gnome.org/guide/threading.html).
The same interface-selection safeguards, managed handles, 64-byte input limit,
and 1000 ms read timeout are inherited from the existing device implementation.

Closing shuts down scheduling without blocking the GTK thread. An already running
operation is allowed to finish and close its handle; its late result is ignored.
The controller never queues follow-up writes, retries, or periodic tasks.

## Connection and failures

Only a valid battery response together with selected receiver metadata yields
“Connected”. This is the result of the last refresh, not continuous link monitoring.
The connection type describes the receiver mode (currently 2.4 GHz).

No selected receiver, a reported asleep/off mouse, or a reported disconnect yields
“Disconnected”. Permission errors, timeouts, invalid battery responses, and unknown
communication failures yield “Connection unavailable”, because receiver presence
alone cannot establish the mouse's state. Battery and charging become unavailable;
they never retain a stale percentage after an operation reports a hardware error.
When a fresh discovery finds no receiver, old identity fields are cleared too.

Device results currently expose diagnostic strings. The presentation adapter maps
known error hints to useful messages, without showing raw paths. If a native
backend only says “open failed”, the GUI conservatively recommends checking the
connection and device access rather than claiming a specific cause. Unexpected
service exceptions also become visible error state instead of escaping into GTK.
The CLI retains detailed diagnostics.

The application remains open. Reconnecting/waking the mouse and pressing Refresh
rediscovers the device; no restart or automatic write is needed. A failed setting
write is never automatically retried.

## Scope and validation

The protocol, device, transport, and existing service files are unchanged in this
phase. The GUI reuses only status/battery, DPI presets, and polling-rate operations.
No command was added. RGB, button mapping, timers, profiles, automatic application,
background/startup services, onboard persistence, save/reset, firmware, macros,
and Bluetooth configuration remain absent.

Tests cover state, strict validation, one-call behavior, worker/main-thread
dispatch, duplicate-action rejection, shutdown, permissions, timeout, disconnect,
and recovery. Strict mocked HID integration verifies interface 3 selection and
the existing exact output bytes, with no save or unrelated command. Import/call
boundary checks prevent direct HID use from UI modules.

The native widget test launches a private
[GTK Broadway display](https://docs.gtk.org/gtk4/broadway.html) using temporary Unix
sockets and no browser. Its child process blocks both native HID modules before
importing the application and replaces all three service functions with mocks.
It exercises startup, both pages, raw DPI validation, each Apply button, busy
state, unavailable information, disconnect/reconnect, and error feedback. It never
uses the desktop compositor, the user's session bus, or physical hardware.
This test needs GTK's `gtk4-broadwayd` and permission to create local Unix sockets;
missing optional GTK dependencies are reported as a skip. All other tests remain
independent of GTK. Run:

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

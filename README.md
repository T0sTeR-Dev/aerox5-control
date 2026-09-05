# aerox5-control

An independent Linux utility for the SteelSeries Aerox 5 Wireless. The current
implementation provides **HID discovery, cached descriptor inspection, device
status, a battery query, active polling-rate control, and DPI presets** using
python-hidapi. Polling and DPI are separate operations; neither sends a save command.
It has no dependency on rivalcfg and does not install, import, invoke, or bundle it.

## Development setup

Python 3.11 or newer is required. On Arch Linux the Python binding is packaged as
`python-hidapi`; the PyPI distribution is `hidapi`. The native `hidapi` library
alone does not provide the Python module.

Use the Linux hidraw backend. Upstream Linux wheels provide it as `hidraw`,
alongside a libusb-backed `hid` module. The transport prefers `hidraw`. When that
module is absent, it uses `hid`, the name used by Arch's hidraw-only package.
A broken `hidraw` import is reported as an error without falling back to libusb.
Custom builds providing only `hid` must also use the hidraw backend.
See the [Arch package linkage](https://archlinux.org/packages/extra/x86_64/python-hidapi/sonames/)
and [upstream backend selection](https://github.com/trezor/cython-hidapi/blob/master/setup.py).

For an isolated development environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/aerox5-control-cli inspect
```

After activating the environment, the command is `aerox5-control-cli inspect`.
`python -m aerox5_control inspect` is also supported. Run the application as your
normal user; it does not require root or install permission rules.

## Discovery

The command requests enumeration separately for each exact VID/PID below and
retains every matching entry:

| Vendor ID | Product ID | Connection |
| --- | --- | --- |
| `0x1038` | `0x1852` | 2.4 GHz receiver |
| `0x1038` | `0x1854` | Wired |

For each entry it prints the vendor ID, product ID, interface number, usage page,
usage, manufacturer string, product string, serial number, and HID path.
Missing optional metadata is shown as `(unavailable)`. HIDAPI's unknown interface
number `-1` is normalized to unavailable; zero-valued usage fields are preserved.
Paths remain opaque bytes or strings in the transport model. The CLI renders byte
paths as UTF-8 with backslash escapes for undecodable bytes.

Entries are not deduplicated by product ID, serial number, or path. A device can
have multiple HID interfaces, and an interface can have multiple collections.
Discovery preserves every interface. The separate battery command uses the
confirmed receiver configuration interface described below. Receiver discovery
does not prove that its paired mouse is connected or awake.

Exit status is 0 for successful enumeration, including an empty result; 1 for a
backend loading/enumeration error; and 2 for invalid command-line arguments.
An empty result means the backend reported no matching entries, not that hardware
absence or permissions have been independently established.

## HID descriptor inspection

```sh
.venv/bin/aerox5-control-cli hid-info
```

`hid-info` shows all discovery metadata, descriptor source/length/SHA-256,
application collections, standard/vendor-specific usage pages, report IDs, and
input/output/feature report sizes. It reads each distinct HID path's descriptor
once, retaining all enumerated usage collections for that path. HID entry numbers
are display ordinals; the separate `Interface number` field is the USB interface
number. The USB parent path identifies which device owns an interface.

Sizes include constant fields and padding. Payload bytes are rounded up after
summing all fields belonging to a report type and ID. Wire bytes include an ID
byte only for explicitly numbered reports; HIDAPI's synthetic zero prefix for
unnumbered report buffers is not included. These are descriptor-declared lengths,
not observations of live report traffic or USB endpoint packet sizes.

Descriptors come exclusively from `/sys/class/hidraw/hidrawN/device/report_descriptor`.
The reader verifies the allowlisted USB identity against cached `HID_ID` before
and after reading, and checks the interface number when available. It does not
open `/dev/hidrawN`, even if those device nodes are missing from the environment.
Unavailable, malformed, or unsupported descriptors produce per-interface errors;
other interfaces are still displayed and the command exits with status 1.
An empty discovery result exits with status 0. No fallback opens a device or
requests a report when cached descriptor inspection fails.

The reusable parser handles HID short items, global Push/Pop, local usage scope,
extended usages, collections, and separate bit totals for each type/report ID.
It is a layout summarizer, not a complete HID validator or field-value decoder.
Long items, delimiters, reserved items, malformed state, and descriptors larger
than 4096 bytes are rejected without returning partial sizes.

Configuration candidates are inferred from vendor-specific application
collections with output or feature reports. This is explicitly uncertain and
does not select an interface for communication. The battery command separately
uses the confirmed standard receiver interface. See
[the observed receiver interfaces](docs/hid-interfaces.md) and
[captured descriptor fixtures](tests/fixtures/aerox5_receiver.json).

## Battery query: manual hardware test

With the standard 2.4 GHz receiver connected and the mouse awake, run as your
normal desktop user:

```sh
.venv/bin/aerox5-control-cli battery
```

After activating `.venv`, the equivalent command is `aerox5-control-cli battery`.
This command intentionally sends one documented battery query. The project owner
has confirmed that it works on the physical mouse. No hardware query was run
during implementation or automated tests of the status command.

The command enumerates only `1038:1852`, selects interface 3 with usage page
`0xffc0` and usage `0x0001`, and opens that returned path. It does not hardcode
`/dev/hidraw9`, access the other interfaces, or query the wired device. Missing
metadata, conflicting records, or multiple matching receivers result in
unavailable status before any interface is opened.

The exact HIDAPI output buffer is **`00 D2`**, two bytes total. `00` is HIDAPI's
synthetic ID prefix; `D2` is the complete query payload. There are no additional
padding bytes. The command performs one input read on the same handle with a
1000 ms timeout, then closes the handle. It performs no retries or feature-report
operations. See [the protocol specification](docs/battery-protocol.md).

Successful output is:

```text
Battery: 75%
Charging: no
```

Charging is `yes` when the response's charging bit is set. If unavailable, stdout
is exactly `Battery: unavailable`, a reason is written to stderr, and the exit
status is 1. Missing/asleep devices, timeouts, malformed replies, invalid battery
values, permission failures, and disconnects never become fabricated percentages.
Successful queries exit with status 0. The normal user needs access to the
selected hidraw node; permission failure is reported without elevating privileges
or changing permissions. This phase installs no udev rules.

## Device status

```sh
.venv/bin/aerox5-control-cli status
```

`status` displays the device name, connection type, VID/PID, selected interface,
HID path, available manufacturer/serial metadata, and battery/charging state.
It uses the same single `00 D2` query, selection checks, and 1000 ms read timeout
as `battery`. It introduces no new HID command and sends no feature reports.

When available, `USB device release (bcdDevice)` shows the raw hexadecimal
`release_number` from HIDAPI enumeration. This field describes the enumerated
receiver; it is not interpreted as mouse firmware or hardware revision.
`Connection: 2.4 GHz` describes the receiver mode, not proof of a live mouse link.

Public research established the existing battery/charging query. A firmware
getter in OpenRGB remains a research lead with unresolved framing, initialization,
and receiver/mouse version ownership questions. Firmware and hardware revision
are not queried or displayed. See [the evidence and decisions](docs/device-information.md).

On battery failure, available identity metadata remains visible alongside
`Battery: unavailable`; charging is omitted, the reason goes to stderr, and the
command exits 1. Selection failure also prints `Device: unavailable`. Success
exits 0, even when optional metadata is missing. `status` queries only the standard
`1038:1852` receiver; wired devices remain available through discovery commands.

## Safety and architecture

`inspect` only enumerates devices; `hid-info` additionally reads cached sysfs
metadata. Neither opens a HID handle or requests/sends reports. The explicit
`battery` and `status` commands open receiver interface 3 and send `00 D2`.
`polling set` uses the same selection checks and sends only its polling request.
`dpi set` sends only a sensitivity request, replacing 1-5 presets and selecting
the first (index 0). It does not change polling rate.
The application never sends feature reports, other setting commands, save,
reset, or firmware commands. Importing the application and requesting CLI help
do not import or initialize the HID backend.

The transport package contains generic HID enumeration, sysfs access, and managed
output/input report I/O. It knows no Aerox command bytes. The
`hid_descriptor` package parses bytes without I/O or Aerox protocol knowledge.
The protocol package encodes battery/polling/DPI requests, contains the verified
TrueMove Air lookup table, and strictly decodes battery replies. The devices
package owns Aerox interface selection, the transactions, structured device
status, and setting request results with opaque readback bytes.
Application services expose these operations; the CLI formats their results.
GTK UI and other settings remain future work.

## Active polling-rate control: manual hardware test

With the standard receiver connected and the mouse awake, run as your normal
desktop user from the project directory:

```sh
.venv/bin/aerox5-control-cli polling set 1000
```

Supported rates are 125, 250, 500, and 1000 Hz. For usage information:

```sh
.venv/bin/aerox5-control-cli polling --help
```

Each invocation validates its rate before HID discovery, selects only
`1038:1852`, interface 3, page `0xffc0`, usage `1`, and opens the returned path.
It writes one unnumbered output report and reads up to 64 bytes on the same
handle with a 1000 ms timeout, then closes. There is no automatic retry.

| Rate | Exact HIDAPI output buffer |
| --- | --- |
| 1000 Hz | `00 6B 00` |
| 500 Hz | `00 6B 01` |
| 250 Hz | `00 6B 02` |
| 125 Hz | `00 6B 03` |

No padding is added. `00` is HIDAPI's synthetic report-ID byte. No save command
(`11` / wireless `51`) or other setting is sent; no onboard persistence is
requested. A successful transport exchange prints:

```text
Polling-rate request sent: 1000 Hz
Readback received; active rate unverified.
```

Readback bytes are retained internally without interpreting them as an
acknowledgment or current rate. There is no `polling get` command or cached
polling value in `status`. Exit status 0 means the write, readback, and close
completed; it does not establish that the mouse applied the setting.

Invalid arguments exit 2 before hardware access. Selection, permission, write,
readback, or close failures exit 1 with a diagnostic on stderr. After a write
attempt the active rate may already have changed, even if readback fails; the
CLI reports that uncertainty and sends no retry or rollback. The project owner
has confirmed successful physical polling-rate tests. No hardware command was
executed during DPI development or automated tests. See
[the polling protocol and safety details](docs/polling-protocol.md).

## DPI presets: first manual hardware test

With the standard receiver connected and the mouse awake, run as your normal
desktop user from the project directory:

```sh
.venv/bin/aerox5-control-cli dpi set 800
```

This replaces the preset list with a single 800-DPI preset and requests selection
of index 0. For multiple presets or help:

```sh
.venv/bin/aerox5-control-cli dpi set 800 1600
.venv/bin/aerox5-control-cli dpi set 400 800 1200 2400 3200
.venv/bin/aerox5-control-cli dpi --help
```

Provide 1-5 integer values between 100 and 18000, in increments of 100. Input
order and duplicates are preserved. Invalid values such as 850 are rejected
without rounding, before HID discovery. The application uses an explicit
TrueMove Air lookup table covering all 180 values, checked against pinned public
protocol references. It does not use a simple `DPI / 100` byte conversion.

The exact HIDAPI output for `dpi set 800` is `00 6D 01 00 09`: synthetic ID,
wireless command, count, selected index, encoded value. No padding is added.
The command sends one output report to dynamically selected receiver interface
3, performs one read of up to 64 bytes with a 1000 ms timeout on the same handle,
and closes. No save/persistence, retry, polling change, or other command is sent.

Exit status 0 means the write/readback/close completed. Raw readback is retained
for diagnostics and has no assigned acknowledgment or configuration semantics.
The CLI reports requested values, not independently verified hardware state.
There is no `dpi get`, arbitrary active-index selection, or locally cached DPI
value in `status`. Invalid arguments exit 2; selection and I/O failures exit 1.
After a write attempt, the CLI reports that DPI may have changed even if the
readback fails. No DPI command was executed on the physical mouse during this
implementation. See [the complete DPI protocol and mapping](docs/dpi-protocol.md).

## Checks

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Every test replaces both `hidraw` and `hid` before any backend can load. Discovery
mocks expose only enumeration. Battery tests opt into a fake transport or strict
mock handles that allow only exact-path open, output write, timed read, and close;
the battery I/O fixture rejects any output other than `00 D2`. Polling tests opt
into a separate mock that permits only the four exact polling buffers above;
complete call-sequence assertions exclude additional commands, save operations,
and retries. Descriptor tests use captured/static fixtures and temporary sysfs
trees. Tests do not access physical HID devices or the real sysfs tree.
DPI tests use their own exact-packet allowlist and a separate reference fixture
to verify every supported DPI value. Tests never install or execute reference
projects and need no network access.

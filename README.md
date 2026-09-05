# aerox5-control

An independent Linux utility for the SteelSeries Aerox 5 Wireless. The current
implementation provides **read-only HID enumeration and descriptor inspection**
using python-hidapi and Linux's cached sysfs descriptors.
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
No interface is assumed to be the configuration interface. Receiver discovery
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
does not select an interface for communication. See
[the observed receiver interfaces](docs/hid-interfaces.md) and
[captured descriptor fixtures](tests/fixtures/aerox5_receiver.json).

## Safety and architecture

Only the selected backend's `enumerate(vendor_id, product_id)` is called. The
application also reads cached sysfs metadata for matching devices. It never
constructs a HID device handle, opens an interface, reads or sends reports,
changes settings, or performs firmware operations. Importing the application
and requesting CLI help do not import or initialize the HID backend.

The transport package contains generic HID enumeration and sysfs access. The
`hid_descriptor` package parses bytes without I/O or Aerox protocol knowledge.
The devices package contains the Aerox VID/PID mapping. Application services
coordinate discovery/inspection; the CLI formats the results. Protocol encoding
and GTK UI are reserved for later phases and are not dependencies of discovery.

## Checks

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Every test receives strict mocks for both `hidraw` and `hid` before discovery can
run. The mocks expose only enumeration; attempts to open devices or send reports
fail. Descriptor tests use captured/static byte fixtures and temporary sysfs
trees; every test redirects the default sysfs root into its temporary directory.
Tests do not access physical HID devices or the real sysfs tree.

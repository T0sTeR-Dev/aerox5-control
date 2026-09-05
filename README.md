# aerox5-control

An independent Linux utility for the SteelSeries Aerox 5 Wireless. The current
implementation provides **read-only HID enumeration** using python-hidapi.
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

The command enumerates SteelSeries HID entries and retains every entry matching:

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

## Safety and architecture

Only the selected backend's `enumerate(vendor_id, product_id)` is called. The
application never constructs a HID device handle, opens an interface, reads or sends reports,
changes settings, or performs firmware operations. Importing the application
and requesting CLI help do not import or initialize the HID backend.

The transport package contains generic HID metadata and enumeration. The devices
package contains the Aerox VID/PID mapping. Application services coordinate
discovery; the CLI formats the results. Protocol encoding and GTK UI are reserved
for later phases and are not dependencies of discovery.

## Checks

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Every test receives strict mocks for both `hidraw` and `hid` before discovery can
run. The mocks expose only enumeration; attempts to open devices or send reports
fail. Tests use synthetic enumeration records and do not access physical HID
devices.

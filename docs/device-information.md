# Read-only device information

Research reviewed on 2026-09-05. The project owner has confirmed successful
battery/charging queries on the physical `1038:1852` receiver, interface 3.
No hardware query was executed while implementing `status` or running its tests.

## Implemented scope

`aerox5-control-cli status` combines enumeration metadata with the existing
battery query. It adds **no new protocol command**. Firmware and hardware
revision are unsupported and omitted from CLI output; they are not guessed
from USB metadata, product strings, or published firmware release numbers.

| Information | Source | Request issued by this application | Validation / interpretation |
| --- | --- | --- | --- |
| Device, VID/PID, interface, HID path | HIDAPI enumeration | No HID report | Select only `1038:1852`, interface 3, page `0xffc0`, usage `1` |
| Connection | Known receiver PID `0x1852` | No HID report | `2.4 GHz` identifies the receiver mode; it does not prove a live radio link |
| Manufacturer, serial | Selected enumeration entry | No HID report | Omit missing/empty optional strings |
| USB device release | HIDAPI `release_number` | No HID report | Preserve a raw unsigned 16-bit integer; omit invalid/missing values |
| Battery, charging | Existing Aerox battery transaction | Output buffer **`00 D2`**, exactly two bytes | Response **`D2 value`**; level code `value & 0x7f` must be 1–21, percentage `(code - 1) * 5`, charging `bool(value & 0x80)` |

The release field is labeled **USB device release (bcdDevice)** and displayed in
hexadecimal. It belongs to the enumerated USB receiver, not necessarily the
paired mouse. HIDAPI describes this as a BCD device version; this application
does not convert it into a firmware or hardware revision. HIDAPI can return zero
when the field is unavailable, so even `0x0000` is only a raw reported value.

The battery transaction uses an unnumbered output report. The initial `00` is
HIDAPI's synthetic report-ID prefix, not part of the protocol payload. No padding
is added to the write. One read on the same handle requests up to 64 bytes with a
1000 ms timeout, followed by close. Exactly two response bytes are accepted, or
64 bytes only if bytes 2–63 are zero. Wrong headers, invalid lengths/padding,
invalid levels, and the `40 FF` asleep/off marker are unavailable. See the full
[battery specification](battery-protocol.md).

## Protocol evidence

The following primary sources were read as references only. No referenced
project was installed, imported, invoked, copied into this project, or added as
a build/runtime dependency.

- [Aerox_5 battery implementation, revision 26bbf07](https://github.com/LennardKittner/Aerox_5/blob/26bbf0798a8f7b22a1997d7c0e2395a47419d868/src/lib.rs)
  identifies interface 3 and the standard receiver, constructs exactly `00 D2`,
  and documents the two meaningful reply bytes, `D2` header, charging bit, level
  formula, and `40 FF` marker. This corroborates the existing battery transaction.
- [rivalcfg Aerox 5 wired profile, revision ffabd4c](https://github.com/flozz/rivalcfg/blob/ffabd4ce8ab7f60899d7d1e2e106ae447509fbb3/rivalcfg/devices/aerox5_wireless_wired.py)
  explicitly defines an output battery query `92`, a two-byte response, and the
  charging/percentage decoding. Its
  [wireless profile, revision 1300a4c](https://github.com/flozz/rivalcfg/blob/1300a4c817fef535bbfabb758a095067d7d5e447/rivalcfg/devices/aerox5_wireless_wireless.py)
  identifies `1038:1852`, interface 3, and applies bit `40` to the battery opcode,
  with a 64-byte readback. Neither profile provides a firmware getter.
  This is source research only; aerox5-control remains entirely independent.
- [openseries-gg Aerox 5 implementation, revision 1cceab2](https://github.com/PicoShot/openseries-gg/blob/1cceab28a8c3aacbaa4fc31d08a6eec8f7bb91f7/src/devices/mice/aerox_5.rs)
  independently implements receiver PID identification and the same wireless
  battery opcode, mask, and level formula. It provides no Aerox 5 firmware or
  hardware-revision getter. Its looser response acceptance is not adopted here.
- [HIDAPI 0.15 API definitions](https://github.com/libusb/hidapi/blob/hidapi-0.15.0/hidapi/hidapi.h)
  define enumeration metadata, the release field, and the synthetic report-ID
  prefix. Its [Linux backend](https://github.com/libusb/hidapi/blob/hidapi-0.15.0/linux/hid.c)
  obtains `release_number` from cached USB `bcdDevice` through udev.
  [python-hidapi's enumeration implementation](https://github.com/trezor/cython-hidapi/blob/master/hid.pyx)
  exposes that field in the enumeration dictionary. No additional device handle,
  feature report, or shell command is needed to read it.

## Firmware research lead: deferred

There **is** a public firmware-getter candidate in
[OpenRGB's shared Aerox 3/5/9 Wireless controller, revision 67a81f2](https://github.com/CalcProgrammer1/OpenRGB/blob/67a81f219d9b16767cfaf26f60bb8ed706296140/Controllers/SteelSeriesController/SteelSeriesAeroxWirelessController/SteelSeriesAeroxWirelessController.cpp).
`GetFirmwareVersion()` sends a 64-byte **feature** buffer containing `00 90`
followed by 62 zero bytes. It expects an input header `90` and treats the next
16 bytes as version text. This is a research lead, **not an implemented or
recommended test packet**.

The same controller constructor calls `SendInit()`, which sends a
sensitivity/software-mode-related feature report. The getter bypasses the
controller's wireless output-command transformation. It does not identify
whether the version belongs to the receiver or mouse, or validate that enough
response bytes arrived before copying version text. Its feature buffer is also
shorter than this receiver's captured 512-byte feature report.

Our assessment is that this does not yet establish a sufficiently verified,
standalone, configuration-preserving exchange for this exact receiver. It does
not prove initialization is necessary or that a short feature transfer is
invalid, either. Those questions remain open. We do not reproduce initialization,
change the report type/length, derive a wireless opcode, or probe either variant.

[fwupd's SteelSeries model map, revision b6c2938](https://github.com/fwupd/fwupd/blob/b6c293816276716d3e52382a5c251f86503e8699/plugins/steelseries/steelseries.quirk)
includes Aerox 3 Wireless devices but does not map `1852` or `1854`. It therefore
does not establish applicability of that model's version protocol to the Aerox 5.
No fwupd executable, service, or firmware-update functionality was accessed.

Before adding a firmware query, establish an Aerox 5-specific standalone
request/response capture or equivalent documented implementation, report type,
full framing and padding, version ownership (receiver/mouse), length, encoding,
and asleep/error replies. Any later capture session needs a separate scope that
keeps initialization, setting writes, and firmware-update traffic out of the
implemented transaction. No reliable independent hardware-revision or radio-link
query was established in the sources reviewed.

## Selection, failures, and manual use

Both `battery` and `status` enumerate only `1038:1852` and use one shared receiver
transaction. The exact returned path is opened only when interface/page/usage
match. Identical duplicate entries are accepted once; multiple paths or
conflicting metadata for the same path are rejected before opening. The wired
`1854` device remains discoverable with `inspect` and `hid-info`, but neither
`battery` nor `status` sends a query to it. No interface 0, 1, 2, or 4 is opened.

`Aerox5Status` in the device layer contains the selected `Aerox5Interface`, if
available, and the decoded `BatteryStatus`. Generic HID transport knows no Aerox
opcodes; protocol encoding/decoding remains in `protocol/aerox5.py`. The
application service exposes status and the CLI only formats the result.

When a query times out, permission is denied, a device disconnects, or a response
is invalid, status preserves any metadata obtained from enumeration, prints
`Battery: unavailable`, omits charging, reports a reason on stderr, and exits 1.
If selection fails, it prints `Device: unavailable` and `Battery: unavailable`.
It never reuses an earlier battery reading, retries, escalates privileges, or
changes permissions. A successful query exits 0. Missing optional release/serial
metadata and unsupported firmware do not turn a valid battery query into an error.

Run as your normal user from the project directory:

```sh
.venv/bin/aerox5-control-cli status
.venv/bin/aerox5-control-cli battery
.venv/bin/aerox5-control-cli inspect
.venv/bin/aerox5-control-cli hid-info
```

The first two commands each intentionally send exactly one `00 D2` battery
query. The other two perform enumeration/cached descriptor inspection only.
Tests replace both native HID modules and permit only `00 D2` in the opt-in I/O
mock. No new real-device command was executed for this phase.

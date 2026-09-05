# Aerox 5 Wireless receiver battery query

Scope: standard 2.4 GHz receiver `1038:1852` only, USB interface 3, usage page
`0xffc0`, usage `0x0001`. The interface selection was confirmed by the project
owner for Phase 3. The corresponding vendor-specific application and report
layout were captured in [Phase 2](hid-interfaces.md).
The project owner subsequently confirmed successful real battery/charging
queries. Both `battery` and `status` now share this same transaction; `status`
adds enumeration metadata without adding commands. See
[device-information research](device-information.md) for corroborating sources
and the firmware query deferral.

The USB interface number is distinct from an endpoint address. HIDAPI handles
endpoint selection. The program opens the exact path returned by enumeration,
which may differ from the previously observed `/dev/hidraw9`.

## Request

The supplied wired opcode is `BATTERY_QUERY_WIRED = 0x92`. The wireless command
sets `WIRELESS_COMMAND_FLAG = 0x40`, giving `0x92 | 0x40 = 0xd2`.
There is no wired battery execution path in this phase.

The unnumbered HID output query has a one-byte protocol payload:

```text
D2
```

The exact buffer passed to `hidapi.device.write()` is two bytes:

```text
00 D2
```

The first byte is HIDAPI's synthetic report-ID prefix. It is not a descriptor
field or an additional protocol byte. The query is sent as an output report;
there is no feature-report request. The transport does not add padding.

Although the descriptor declares 64-byte output reports, the documented battery
query uses this short buffer. The public
[Aerox_5 battery implementation](https://github.com/LennardKittner/Aerox_5/blob/main/src/lib.rs)
provides an independent implementation reference for the exact two-byte buffer,
interface 3, response header, second-byte battery value, and mouse-off marker.
It was inspected as a reference on 2026-09-05; no code was installed, imported,
invoked, or bundled. This project implements its own transport and decoder and
has no rivalcfg dependency.

HIDAPI's prefix convention is specified by its
[API documentation](https://github.com/libusb/hidapi/blob/hidapi-0.15.0/hidapi/hidapi.h).
A short or failed write is an error; the implementation never retries or sends
a second command.

## Response and strict validation

One read requests up to 64 bytes from the same open interface with a positive
1000 ms timeout. The meaningful response is:

| Byte index | Meaning |
| --- | --- |
| 0 | Battery response header `0xd2` |
| 1 | Bit 7: charging; bits 0–6: encoded battery level |

For `value = response[1]`:

```text
charging = bool(value & 0x80)
level_code = value & 0x7f
percentage = (level_code - 1) * 5
```

Only level codes 1 through 21 are accepted, giving percentages 0 through 100
in five-point increments. There is no clamping, underflow, or fallback to a
previous reading. Examples: `D2 10` means 75%, not charging; `D2 90` means 75%,
charging; `D2 01` means 0%; `D2 15` means 100%.

The decoder accepts exactly two bytes. It also accepts a full 64-byte input
report when bytes 2–63 are all zero. This is a conservative padding policy based
on the captured descriptor length, not a claim that the real reply padding has
been observed. Other lengths, nonzero trailing data, wrong headers, and invalid
level codes return unavailable. Input does not have HIDAPI's synthetic zero
prefix. A response beginning with the documented `40 FF` mouse-off marker is
unavailable as well, subject to the same length/padding checks.

The implementation does not drain reports or search through additional replies.
The first malformed/unrelated report ends this attempt as unavailable. It never
polls, retries the query, or reads another interface.

## Lifetime, results, and first manual test

Each call enumerates the standard receiver afresh. Selection requires exact
VID/PID, interface, and usage metadata. Duplicate identical entries sharing a
path produce one query. Multiple receiver paths or conflicting metadata produce
unavailable status without opening any handle.

An opened handle is closed on success, timeout, malformed input, and I/O failure.
Permission and disconnect errors become unavailable status with a diagnostic;
there is no privilege escalation or change to device permissions.

`BatteryStatus` contains `level` and `charging` for success. For unavailable
results both are `None`, and `reason` describes the failure. CLI stdout prints
either the percentage and charging state or `Battery: unavailable`. Failure
diagnostics go to stderr; exit codes are 0 for success, 1 for unavailable, and 2
for invalid CLI arguments.

No real battery command was executed while implementing status or running its
automated tests. With the mouse awake and receiver connected, manually run from
the project directory as the normal desktop user:

```sh
.venv/bin/aerox5-control-cli battery
```

The expected success format is:

```text
Battery: 75%
Charging: no
```

The numeric value above is illustrative; the CLI reports the current validated
response or an explicit unavailable state.

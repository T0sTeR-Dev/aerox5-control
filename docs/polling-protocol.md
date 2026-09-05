# Aerox 5 Wireless active polling-rate control

Scope: the standard 2.4 GHz receiver `1038:1852`, USB/HID interface 3, usage page
`0xffc0`, usage `0x0001`. The project owner has confirmed this configuration
interface, battery query, and polling control on the physical mouse. No hardware
commands were executed while implementing DPI or running automated tests.
Polling control changes only the active polling rate and sends no save command.

## Encoding and evidence

The task's supplied protocol specifies wired polling command `0x2b`, wireless
command flag `0x40`, and the four values below. These facts match the public
[Aerox 5 wired profile's polling-rate definition](https://github.com/flozz/rivalcfg/blob/ffabd4ce8ab7f60899d7d1e2e106ae447509fbb3/rivalcfg/devices/aerox5_wireless_wired.py)
and [wireless command transformation and readback length](https://github.com/flozz/rivalcfg/blob/1300a4c817fef535bbfabb758a095067d7d5e447/rivalcfg/devices/aerox5_wireless_wireless.py)
reviewed during the preceding protocol research phase. They are references only;
this project does not install, import, invoke, bundle, or depend on rivalcfg.

`0x2b | 0x40 = 0x6b`. The pure `encode_polling_rate(rate_hz)` function produces
only the wireless command and value. It accepts Python integers 125, 250, 500,
or 1000, and raises `ValueError` for other values or types, including booleans,
floats, and strings. The CLI parses integer text and restricts it to these four
choices before constructing a device operation.

| Rate | Value | Protocol payload | Exact HIDAPI write buffer |
| --- | --- | --- | --- |
| 1000 Hz | `00` | `6B 00` | **`00 6B 00`** |
| 500 Hz | `01` | `6B 01` | **`00 6B 01`** |
| 250 Hz | `02` | `6B 02` | **`00 6B 02`** |
| 125 Hz | `03` | `6B 03` | **`00 6B 03`** |

This is an unnumbered HID **output** report. HIDAPI requires the synthetic `00`
report-ID prefix; the generic transport adds it. There are exactly three bytes
in each write buffer, with **no padding**. The task establishes these minimal
buffers; neither the existing transport nor observed polling behavior establishes
a need for padding. The descriptor's 64-byte output layout alone is not used to
invent additional bytes. No feature-report operation is used.

The wired command exists only as an encoding constant; there is no wired polling
execution path. This polling operation emits only the wireless `6b` opcode.
It does not send save `11` / wireless `51`, persist to onboard memory, reset,
initialize other settings, or issue battery/status queries around this operation.
No persistence across reconnects or power cycles is promised.

## Transaction and readback

1. Encode/validate the rate before any enumeration, open, or write.
2. Enumerate only VID `1038`, PID `1852`. Select interface 3 with page `ffc0`
   and usage `1` using the same checks as battery/status.
3. Reject absent, multiple, or conflicting candidates before opening. Identical
   duplicate entries for the same path produce a single transaction.
4. Open the exact returned path, without hardcoding a hidraw number.
5. Attempt exactly one output write. Require the full three-byte write count.
6. On a successful write, request one input read of **up to 64 bytes**, with a
   **1000 ms** timeout on the same handle, then close the handle.

The existing generic HID transport validates native input byte values and length.
The device layer also checks the bytes/length contract for injected transports.
An empty input is a timeout; malformed native data and reads longer than the
requested maximum are failures. Any nonempty readback of 1–64 bytes is retained
as opaque `bytes`. Short readback, zero bytes within a nonempty report, and any
particular header do not receive undocumented interpretation. There is no
header comparison, ACK decoder, padding requirement, rate decoder, input drain,
or additional read loop for polling readback.

`PollingRateResult` in the device layer contains `requested_rate_hz`, the selected
interface if available, `write_attempted`, raw `readback` if obtained, and an
error if a transport/selection step failed. Its `completed` property refers only
to completing the transport exchange, including close. This is not confirmation
of the active rate. `requested_rate_hz` records the caller's request and is never
presented as a measured or queried hardware value. Readback remains available in
the result even if closing fails after a successful read.

The generic HID transport remains unchanged and knows no SteelSeries opcodes.
Protocol encoding belongs to `protocol/aerox5.py`; receiver selection and I/O
coordination belong to `devices/aerox5.py`; the application service and CLI expose
that operation. There is no current-rate getter or local polling-rate cache.

## Failure behavior and first manual test

The CLI exits 0 when the transport exchange completes, 1 on selection/I/O failure,
and 2 on invalid arguments. A failed attempt does not produce a success message.
Permission errors and disconnects are reported without root, permission changes,
or fallback interfaces. An opened handle is closed on both success and failure.

After any write attempt, failure may leave the active rate changed or unknown.
The CLI explicitly reports this when the write/readback/close fails. There is
no automatic retry, second configuration write, rollback, or save. A missing or
opaque readback cannot establish that the previous rate was retained.

With the receiver attached and the mouse awake, run as your normal desktop user
from the project directory for the first physical test:

```sh
.venv/bin/aerox5-control-cli polling set 1000
```

Equivalent with the environment activated: `aerox5-control-cli polling set 1000`.
For help without opening a device: `aerox5-control-cli polling --help`.
Other accepted commands replace `1000` with `500`, `250`, or `125`. No `get`,
save, or other setting subcommand exists.

## Automated verification

Tests use a polling-only FakeTransport or mocked native HIDAPI handles. The
autouse fixtures replace both `hidraw` and `hid`, and descriptor tests use
temporary sysfs trees. The opt-in polling mock accepts only the four exact
three-byte buffers above; battery tests keep their separate battery-only guard.

Tests cover every mapping and exact buffer, invalid values/types before hardware
access, strict interface selection, ambiguous devices, duplicate entries, one
write/read, raw readback retention, short writes, timeout, malformed native
readback, disconnect, permission denial, close failure, and absence of save or
unrelated commands. No test accesses the real receiver or changes the mouse.

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

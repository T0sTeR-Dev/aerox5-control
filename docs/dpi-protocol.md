# Aerox 5 Wireless DPI presets

Scope: standard 2.4 GHz receiver `1038:1852`, USB/HID interface 3,
usage page `0xffc0`, usage `0x0001`. Battery and polling control have been
physically confirmed by the project owner. **DPI control has not been executed
against the physical mouse during development or tests.**

## Request layout

The supplied Aerox 5 Wireless protocol defines wired sensitivity command
`0x2d` and the wireless flag `0x40`: `0x2d | 0x40 = 0x6d`.
The same command/profile facts were studied in the
[Aerox 5 wired profile](https://github.com/flozz/rivalcfg/blob/ffabd4ce8ab7f60899d7d1e2e106ae447509fbb3/rivalcfg/devices/aerox5_wireless_wired.py)
and [wireless profile](https://github.com/flozz/rivalcfg/blob/1300a4c817fef535bbfabb758a095067d7d5e447/rivalcfg/devices/aerox5_wireless_wireless.py)
during the preceding protocol research. Only the receiver execution path exists.

| Protocol byte offset | Meaning |
| --- | --- |
| 0 | Wireless sensitivity command `6D` |
| 1 | Preset count, 1 through 5 |
| 2 | Selected preset index, always `00` (first preset) |
| 3 onward | One verified TrueMove Air encoded byte per preset, in supplied order |

`encode_dpi_presets(presets)` returns these protocol bytes. The generic HID
transport then adds HIDAPI's synthetic `00` report-ID prefix for this
**unnumbered output report**. That prefix is not part of the Aerox payload or
a field in the descriptor. No padding or feature-report transfer is used.

| Presets (DPI) | Protocol payload | Exact HIDAPI write buffer |
| --- | --- | --- |
| 800 | `6D 01 00 09` | **`00 6D 01 00 09`** |
| 800 / 1600 | `6D 02 00 09 12` | **`00 6D 02 00 09 12`** |
| 400 / 800 / 1200 / 2400 / 3200 | `6D 05 00 04 09 0D 1B 26` | **`00 6D 05 00 04 09 0D 1B 26`** |

These write buffers are 5, 6, and 9 bytes respectively. Presets are not sorted
or deduplicated. Replacing a preset list always requests index 0; arbitrary
active-preset selection is not implemented.

## Verified TrueMove Air mapping

The mapping is not `DPI / 100`. The runtime implementation in
[protocol/truemove_air.py](../src/aerox5_control/protocol/truemove_air.py)
contains explicit known bytes and an immutable lookup table. No byte is
interpolated or extrapolated.

On 2026-09-05, all 180 DPI/byte pairs were extracted as numeric protocol facts
from the [published TrueMove Air table, revision c10fab0](https://github.com/flozz/rivalcfg/blob/c10fab0f6f327d3734cdc55b67b9db0669248ef5/rivalcfg/devices/dpi/truemove_air.py).
Every pair was cross-checked against the separately implemented encoding in
[openseries-gg's Aerox 5 implementation, revision 1cceab2](https://github.com/PicoShot/openseries-gg/blob/1cceab28a8c3aacbaa4fc31d08a6eec8f7bb91f7/src/devices/mice/aerox_5.rs):
**180 matches, zero mismatches**. This is verification against public protocol
references, not a claim of testing all values on physical hardware.

The separate [reference fixture](../tests/fixtures/truemove_air.json) records
every DPI/hex pair and source provenance. Tests compare all runtime entries and
encoded single-preset packets against it, checking complete domain coverage,
unique keys, unique encoded values, and byte bounds. The fixture is not
generated from the runtime lookup table. Runtime code uses a lookup rather than
the comparison implementation's algorithm.

Only protocol facts were retained. No rivalcfg code was installed, imported,
invoked, or bundled; no dependency was added. Tests read local numeric fixtures
and never retrieve or execute upstream code.

Each row below lists ten bytes corresponding, left to right, to the ten
100-DPI steps in the stated range:

| DPI range (step 100) | Encoded bytes in increasing DPI order |
| --- | --- |
| 100–1000 | `00 02 03 04 05 06 07 09 0A 0B` |
| 1100–2000 | `0C 0D 0E 10 11 12 13 14 16 17` |
| 2100–3000 | `18 19 1A 1B 1D 1E 1F 20 21 23` |
| 3100–4000 | `25 26 27 28 29 2A 2C 2D 2E 2F` |
| 4100–5000 | `30 32 33 34 35 36 38 39 3A 3B` |
| 5100–6000 | `3C 3E 3F 40 41 42 44 45 46 47` |
| 6100–7000 | `48 4A 4B 4C 4D 4E 50 51 52 53` |
| 7100–8000 | `54 56 57 58 59 5A 5C 5D 5E 5F` |
| 8100–9000 | `60 62 63 64 65 66 68 69 6A 6B` |
| 9100–10000 | `6C 6E 6F 70 71 72 74 75 76 77` |
| 10100–11000 | `78 7A 7B 7C 7D 7E 80 81 82 83` |
| 11100–12000 | `84 86 87 88 89 8A 8C 8D 8E 8F` |
| 12100–13000 | `90 92 93 94 95 96 98 99 9A 9B` |
| 13100–14000 | `9C 9E 9F A0 A1 A2 A4 A5 A6 A7` |
| 14100–15000 | `A8 AA AB AC AD AE B0 B1 B2 B3` |
| 15100–16000 | `B4 B5 B6 B7 B8 B9 BA BB BC BD` |
| 16100–17000 | `BF C0 C2 C3 C4 C5 C6 C7 C9 CA` |
| 17100–18000 | `CB CC CD CF D0 D1 D2 D3 D5 D6` |

## Validation and execution

The API accepts an ordered sequence such as a list or tuple containing 1–5
Python integers. Text/byte containers, unordered containers, booleans, floats,
non-integers, empty lists, and more than five presets are rejected. Every DPI
must be present in the verified table: 100 through 18000 in steps of 100.
That discrete set is the established protocol mapping, so 850 cannot be rounded
to a nearby value. A missing lookup entry is rejected with no arithmetic fallback.
The validated list is snapshotted as a tuple before any enumeration or write.

The CLI parses integer tokens and performs protocol validation before creating
a hardware operation. The device method independently validates before hardware
access for direct API callers. The generic HID transport knows no DPI meanings.

One `set_dpi_presets` call:

1. Validates and encodes the complete list.
2. Enumerates only `1038:1852` and applies the existing strict interface/page/usage
   selection. Absent, multiple, or conflicting candidates are rejected before
   opening. Identical duplicate entries on one path produce one operation.
3. Opens the exact returned path. No hidraw number is hardcoded, and interfaces
   0, 1, 2, and 4 are never opened.
4. Attempts exactly one sensitivity output write and requires its full length.
5. On successful write, performs exactly one read of up to 64 bytes on the same
   handle with a 1000 ms timeout, then closes.

The device layer shares the existing setting transaction logic with polling,
but the DPI operation never calls the polling setter, battery query, or status
service. There are no save, reset, firmware, RGB, timer, button, or other setting
commands in this transaction. In particular, **no save opcode `11` or wireless
`51` is emitted** and settings are **not persisted to onboard memory in this
phase**. No persistence across reconnects or power cycles is promised.

A DPI data byte can numerically equal a different command opcode: for example,
6800 DPI encodes as `51` and 9000 DPI as `6B`. Those bytes occur after the
`6D count 00` header and are sensor values, not save or polling commands.

## Readback and result semantics

Native input values and size are checked by the HID transport. The device also
checks that an injected transport returns bytes of length 1–64. Empty input is
a timeout; malformed data or excessive length is failure. Nonempty readback
is retained unchanged, including zeros, without interpreting a header, ACK,
current DPI, selected index, or settings. There are no read loops or retries.

`DpiPresetsResult` contains the immutable `requested_presets`, selected interface
when available, `write_attempted`, raw `readback`, and `error`. Its `completed`
property means write/readback/close completed, not that the device acknowledged
or applied the list. Raw bytes remain available if close fails after a read.
Requested values are not cached or presented as confirmed device state.
There is no `dpi get` command.

The CLI exits 0 for a completed exchange, 1 for selection/I/O failure, and 2 for
invalid arguments. It prints only a failure diagnostic when a transaction fails.
After any write attempt, it reports that DPI may already have changed. It
does not retry, roll back, save, elevate privileges, or try another interface.
Handles close on success, timeout, disconnect, and other I/O failures.

## First manual test

With the receiver attached and the mouse awake, run from the project directory
as your normal desktop user:

```sh
.venv/bin/aerox5-control-cli dpi set 800
```

This replaces the preset list with one 800-DPI entry and requests index 0.
Successful transport output is:

```text
DPI preset request sent: 800
Requested selected preset: 0 (first)
Readback received; active DPI presets unverified.
```

Other supported examples and help:

```sh
.venv/bin/aerox5-control-cli dpi set 800 1600
.venv/bin/aerox5-control-cli dpi set 400 800 1200 2400 3200
.venv/bin/aerox5-control-cli dpi --help
```

All tests use FakeTransport or native HIDAPI mocks. Both HID modules are replaced
before loading, and mocks permit only exact known DPI packets for DPI operations.
Complete call-sequence assertions prohibit additional writes, polling, save,
battery queries, and feature reports. The comprehensive mapping checks perform
no I/O against a mouse. No real DPI command was executed during this phase.

# Aerox 5 Wireless HID interface observations

This document records Phase 2's descriptor-only observations. For Phase 3, the
project owner confirmed interface 3 as the standard receiver's configuration
interface, supported by public battery-query research. The implementation now
uses that selection for the [documented battery query](battery-protocol.md) and
the separate [active polling-rate operation](polling-protocol.md).
The project owner subsequently confirmed that the battery query works on the
physical mouse. No real query was run while implementing the status command or
running its tests.

Observed on 2026-09-05 on Arch Linux using the 2.4 GHz receiver, USB
`1038:1852`. Targeted HIDAPI enumeration reported five distinct HID paths and
five entries. All five resolved to the same USB device parent. Manufacturer was
`SteelSeries`, product was `SteelSeries Aerox 5 Wireless`, and serial numbers
were unavailable. No `1038:1854` wired device was enumerated.

The implementation was exercised through `aerox5-control-cli hid-info` as UID
1000. Descriptor data came from the kernel's cached sysfs files. No HID handles
were opened, no input/output/feature reports were requested or sent, and no
settings were changed. Device-node permissions were not needed or tested.

## Receiver layout

Sizes below are descriptor-declared report bytes, including padding. A dash means
that the descriptor declares no report of that type. These are not endpoint
maximum packet sizes. All five descriptors omit Report ID items: their reports
are **unnumbered**, with no report ID byte on the wire.

| USB interface | Observed HID path | Application page / usage | Application | Descriptor bytes | Input bytes | Output bytes | Feature bytes |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| 0 | `/dev/hidraw6` | `0x0001 / 0x0002` | Mouse | 98 | 12 | — | — |
| 1 | `/dev/hidraw7` | `0x0001 / 0x0006` | Keyboard | 59 | 33 | 1 | — |
| 2 | `/dev/hidraw8` | `0x000c / 0x0001` | Consumer Control | 25 | 4 | — | — |
| 3 | `/dev/hidraw9` | `0xffc0 / 0x0001` | Vendor-specific | 37 | 64 | 64 | 512 |
| 4 | `/dev/hidraw10` | `0xffc1 / 0x0001` | Vendor-specific | 21 | 64 | — | — |

The HID path numbers can change after reconnecting. Descriptor inspection uses
enumeration metadata; `battery`, `status`, and `polling set` require interface 3
and open its enumerated path.

Interface 0 describes eight buttons, 16-bit X/Y movement, an 8-bit wheel,
8-bit Consumer AC Pan, and five bytes on vendor page `0xffc1`: 96 bits total.
Its top application remains a normal Mouse despite those vendor-specific fields.

Interface 1 describes eight modifier bits plus a 256-bit keyboard bitmap: 264
input bits, or 33 bytes. Its output report contains three LED bits plus five
padding bits. This demonstrates why output-report presence alone does not imply
a SteelSeries configuration interface.

Interface 2 describes two 16-bit consumer values: four input bytes.

## Configuration candidate: Phase 2 inference, later confirmed for battery

Interface 3 is the strongest candidate among these five interfaces because its
application page is vendor-specific (`0xffc0`) and it declares both output and
feature reports. Inside the application, its fields use vendor page `0xffc1`:

| Report type | Field usage | Report size × count | Payload bytes | Report ID |
| --- | --- | --- | ---: | --- |
| Input | `0xffc1 / 0x00f0` | 8 bits × 64 | 64 | Unnumbered |
| Output | `0xffc1 / 0x00f1` | 8 bits × 64 | 64 | Unnumbered |
| Feature | `0xffc1 / 0x00f2` | 8 bits × 512 | 512 | Unnumbered |

`0xf0`, `0xf1`, and `0xf2` are Usage values, **not report IDs or command opcodes**.
No command meanings have been inferred from them.

Interface 4 is also vendor-specific, but advertises only a 64-byte input report.
Its purpose is unknown; descriptor evidence alone cannot establish whether it
carries status, events, or another kind of data.

The Phase 2 interface 3 conclusion was a structural inference. Subsequent public
research and the owner's successful battery test confirm it for that transaction.
Descriptors alone do not establish command formats, configuration
semantics, persistence, acknowledgments, or safe values. Active polling rate is
now the only implemented setting, based on the separately documented protocol.
Phase 3's battery query is documented separately. The wired device's layout
remains unverified; synthetic wired tests exercise ID handling only.

## Sources and reproducibility

The byte-for-byte receiver descriptors are stored in
[`tests/fixtures/aerox5_receiver.json`](../tests/fixtures/aerox5_receiver.json),
with capture provenance and no serial numbers. Tests assert all five layouts,
standard/vendor application classification, and the candidate inference.

Linux documents cached descriptor inspection through sysfs in its
[HID descriptor introduction](https://docs.kernel.org/hid/hidintro.html).
HIDAPI's descriptor getter operates on a device handle; using sysfs avoids
opening one. The Python binding's implementation is available
[upstream](https://github.com/trezor/cython-hidapi/blob/master/hid.pyx).
Neither hid-tools commands nor its Python package were installed in the inspected
environment. This phase adds no such dependency and does not parse shell output.

The pure parser follows the short-item/global/local/main-item and report-layout
rules in the [USB HID 1.11 specification](https://www.usb.org/sites/default/files/hid1_11.pdf),
sections 6.2.2 and 8. It deliberately rejects unsupported forms rather than
presenting incomplete sizes. Usage labels use the
[USB HID Usage Tables](https://usb.org/hid).

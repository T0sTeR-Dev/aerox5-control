"""Verified TrueMove Air DPI/byte facts; no calculated sensor encoding.

The ordered bytes cover every 100-DPI step from 100 through 18000. See
docs/dpi-protocol.md and tests/fixtures/truemove_air.json for pinned sources
and the independent, complete mapping cross-check.
"""

from types import MappingProxyType

MIN_DPI = 100
MAX_DPI = 18000
DPI_STEP = 100

# Each row holds ten explicit known values, in increasing DPI order.
_ENCODED_VALUES = bytes.fromhex(
    "00 02 03 04 05 06 07 09 0a 0b"  # 100-1000
    " 0c 0d 0e 10 11 12 13 14 16 17"  # 1100-2000
    " 18 19 1a 1b 1d 1e 1f 20 21 23"  # 2100-3000
    " 25 26 27 28 29 2a 2c 2d 2e 2f"  # 3100-4000
    " 30 32 33 34 35 36 38 39 3a 3b"  # 4100-5000
    " 3c 3e 3f 40 41 42 44 45 46 47"  # 5100-6000
    " 48 4a 4b 4c 4d 4e 50 51 52 53"  # 6100-7000
    " 54 56 57 58 59 5a 5c 5d 5e 5f"  # 7100-8000
    " 60 62 63 64 65 66 68 69 6a 6b"  # 8100-9000
    " 6c 6e 6f 70 71 72 74 75 76 77"  # 9100-10000
    " 78 7a 7b 7c 7d 7e 80 81 82 83"  # 10100-11000
    " 84 86 87 88 89 8a 8c 8d 8e 8f"  # 11100-12000
    " 90 92 93 94 95 96 98 99 9a 9b"  # 12100-13000
    " 9c 9e 9f a0 a1 a2 a4 a5 a6 a7"  # 13100-14000
    " a8 aa ab ac ad ae b0 b1 b2 b3"  # 14100-15000
    " b4 b5 b6 b7 b8 b9 ba bb bc bd"  # 15100-16000
    " bf c0 c2 c3 c4 c5 c6 c7 c9 ca"  # 16100-17000
    " cb cc cd cf d0 d1 d2 d3 d5 d6"  # 17100-18000
)

TRUEMOVE_AIR_DPI_VALUES = MappingProxyType(
    dict(zip(range(MIN_DPI, MAX_DPI + 1, DPI_STEP), _ENCODED_VALUES, strict=True))
)


def encode_dpi_value(dpi: int) -> int:
    """Return an explicitly verified byte; never round or interpolate."""
    if type(dpi) is not int or dpi not in TRUEMOVE_AIR_DPI_VALUES:
        raise ValueError(
            "DPI must be a verified integer from 100 through 18000 in steps of 100"
        )
    return TRUEMOVE_AIR_DPI_VALUES[dpi]

"""Encode/decode the Engine DJ `Track.beatData` blob (Engine library schema v2).

Layout (as implemented in libdjinterop, engine/v2/beat_data_blob.cpp):

    blob = uint32 BE (uncompressed length) + zlib stream

    uncompressed:
        double BE   sample_rate
        double BE   samples
        uint8       is_beatgrid_set
        int64 BE    default grid marker count, then markers
        int64 BE    adjusted grid marker count, then markers
        bytes       extra (real files carry 9 zero bytes)

    marker (24 bytes, little-endian):
        double LE   sample_offset
        int64 LE    beat_number
        int32 LE    number_of_beats  (beats until next marker)
        int32 LE    unknown          (0 in practice)
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

HEADER_LEN = 33
MARKER_LEN = 24
_MARKER = struct.Struct("<dqii")


@dataclass
class Marker:
    sample_offset: float
    beat_number: int
    number_of_beats: int
    unknown: int = 0


@dataclass
class BeatData:
    sample_rate: float
    samples: float
    is_beatgrid_set: int
    default_grid: list[Marker] = field(default_factory=list)
    adjusted_grid: list[Marker] = field(default_factory=list)
    extra: bytes = b"\x00" * 9


def decompress(blob: bytes) -> bytes:
    if len(blob) < 4:
        raise ValueError("beatData blob shorter than 4 bytes")
    size = struct.unpack(">I", blob[:4])[0]
    if size == 0:
        return b""
    raw = zlib.decompress(blob[4:])
    if len(raw) != size:
        raise ValueError(f"length prefix {size} != decompressed {len(raw)}")
    return raw


def compress(raw: bytes) -> bytes:
    return struct.pack(">I", len(raw)) + zlib.compress(raw)


def _read_grid(raw: bytes, pos: int) -> tuple[list[Marker], int]:
    (count,) = struct.unpack_from(">q", raw, pos)
    pos += 8
    if count < 0 or len(raw) - pos < count * MARKER_LEN:
        raise ValueError("beat grid is missing data")
    markers = []
    for _ in range(count):
        markers.append(Marker(*_MARKER.unpack_from(raw, pos)))
        pos += MARKER_LEN
    return markers, pos


def _write_grid(grid: list[Marker]) -> bytes:
    out = struct.pack(">q", len(grid))
    for m in grid:
        out += _MARKER.pack(m.sample_offset, m.beat_number, m.number_of_beats, m.unknown)
    return out


def decode_raw(raw: bytes) -> BeatData:
    if len(raw) < HEADER_LEN:
        raise ValueError("beat data shorter than 33 bytes")
    sample_rate, samples = struct.unpack_from(">dd", raw, 0)
    is_set = raw[16]
    default, pos = _read_grid(raw, 17)
    adjusted, pos = _read_grid(raw, pos)
    return BeatData(sample_rate, samples, is_set, default, adjusted, raw[pos:])


def encode_raw(bd: BeatData) -> bytes:
    return (
        struct.pack(">dd", bd.sample_rate, bd.samples)
        + bytes([bd.is_beatgrid_set & 0xFF])
        + _write_grid(bd.default_grid)
        + _write_grid(bd.adjusted_grid)
        + bd.extra
    )


def decode(blob: bytes | None) -> BeatData | None:
    if not blob:
        return None
    raw = decompress(blob)
    if not raw:
        return None
    return decode_raw(raw)


def encode(bd: BeatData) -> bytes:
    return compress(encode_raw(bd))


def roundtrip_ok(blob: bytes) -> bool:
    """True if our codec reproduces the uncompressed bytes exactly.

    Used as a safety gate: we never write a track whose existing blob we
    cannot reproduce byte-for-byte, because that would mean the format on
    this machine differs from what this tool understands.
    """
    try:
        raw = decompress(blob)
        return encode_raw(decode_raw(raw)) == raw
    except Exception:
        return False


def grid_bpm(grid: list[Marker], sample_rate: float) -> float | None:
    """Average BPM described by a grid (first to last marker)."""
    if len(grid) < 2 or sample_rate <= 0:
        return None
    a, b = grid[0], grid[-1]
    beats = b.beat_number - a.beat_number
    span = (b.sample_offset - a.sample_offset) / sample_rate
    if beats <= 0 or span <= 0:
        return None
    return 60.0 * beats / span


def make_grid(
    downbeat_s: float, period_s: float, duration_s: float, sample_rate: float
) -> list[Marker]:
    """Constant-tempo grid with two markers spanning the whole track.

    Beat n sits at downbeat_s + n * period_s; beat 0 (and every multiple of 4)
    is a bar start. Markers are placed on bar boundaries before the start and
    after the end of the track, which matches how Engine stores its own grids.
    """
    import math

    n_start = math.floor(-downbeat_s / period_s)
    n_start = 4 * math.floor(n_start / 4) - 4
    n_end = math.ceil((duration_s - downbeat_s) / period_s)
    n_end = 4 * math.ceil(n_end / 4) + 4

    def off(n: int) -> float:
        return (downbeat_s + n * period_s) * sample_rate

    return [
        Marker(off(n_start), n_start, n_end - n_start, 0),
        Marker(off(n_end), n_end, 0, 0),
    ]

import sqlite3
import struct
import zlib

import numpy as np
import pytest
import soundfile as sf

from enginegrid import beatdata
from enginegrid.analyze import fit_grid
from enginegrid.cli import main


def engine_style_blob(sr=44100.0, samples=44100.0 * 180, bpm=120.0, start=-1000.0):
    """Blob built by hand exactly as libdjinterop lays it out."""
    per = 60 / bpm * sr
    markers = [(start, -4, 400, 0), (start + 400 * per, 396, 0, 0)]
    raw = struct.pack(">dd", sr, samples) + b"\x01"
    for _ in range(2):
        raw += struct.pack(">q", len(markers))
        for m in markers:
            raw += struct.pack("<dqii", *m)
    raw += b"\x00" * 9
    return struct.pack(">I", len(raw)) + zlib.compress(raw), raw


def test_roundtrip_exact():
    blob, raw = engine_style_blob()
    assert beatdata.roundtrip_ok(blob)
    bd = beatdata.decode(blob)
    assert bd.sample_rate == 44100 and len(bd.adjusted_grid) == 2
    assert beatdata.encode_raw(bd) == raw
    assert beatdata.grid_bpm(bd.adjusted_grid, bd.sample_rate) == pytest.approx(120)


def test_unknown_format_rejected():
    raw = b"\x00" * 40
    assert not beatdata.roundtrip_ok(struct.pack(">I", 999) + zlib.compress(raw))


def test_make_grid_hits_beats():
    sr, per, down = 44100.0, 60 / 174, 0.37
    g = beatdata.make_grid(down, per, 300, sr)
    assert g[0].sample_offset < 0 and g[1].sample_offset / sr > 300
    assert g[0].beat_number % 4 == 0
    assert beatdata.grid_bpm(g, sr) == pytest.approx(174)
    # beat 0 must land exactly on the downbeat
    t0 = g[0].sample_offset / sr - g[0].beat_number * per
    assert t0 == pytest.approx(down)


def test_fit_grid_with_jitter_and_outliers():
    rng = np.random.default_rng(0)
    per = 60 / 128
    beats = 0.81 + per * np.arange(400) + rng.normal(0, 0.005, 400)
    beats = np.delete(beats, [10, 50, 51])  # missed beats
    beats = np.append(beats, [33.3, 77.7])  # false beats
    downs = 0.81 + per * np.arange(2, 400, 4)  # bars start at beat index 2
    fit = fit_grid(beats, downs, 200, "beat_this")
    assert fit.bpm == 128
    assert fit.confidence > 0.9
    k = round((fit.downbeat_s - (0.81 + 2 * per)) / per)
    assert k % 4 == 0 and abs(fit.downbeat_s - (0.81 + 2 * per) - k * per) < 0.003


def make_click_track(path, bpm, offset, seconds=40, sr=44100):
    y = np.zeros(int(seconds * sr), np.float32)
    per = 60 / bpm
    t = np.arange(int(0.03 * sr)) / sr
    for i, bt in enumerate(np.arange(offset, seconds, per)):
        amp = 1.0 if i % 4 == 0 else 0.5
        f = 60 if i % 4 == 0 else 1000
        click = amp * np.sin(2 * np.pi * f * t) * np.exp(-t * 80)
        s = int(bt * sr)
        y[s : s + len(click)] += click[: len(y) - s]
    sf.write(path, y, sr)


def test_end_to_end(tmp_path):
    lib = tmp_path / "Engine Library"
    (lib / "Database2").mkdir(parents=True)
    music = tmp_path / "Music"
    music.mkdir()
    specs = [(128.0, 0.25), (174.0, 0.11), (95.0, 0.6)]
    db = lib / "Database2" / "m.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE Track (id INTEGER PRIMARY KEY, path TEXT, title TEXT, artist TEXT,"
                " bpm INTEGER, bpmAnalyzed REAL, beatData BLOB, isBeatGridLocked INTEGER)")
    for i, (bpm, off) in enumerate(specs, 1):
        make_click_track(music / f"t{i}.wav", bpm, off)
        # wrong existing grid: 120 BPM starting at 0
        blob, _ = engine_style_blob(samples=44100.0 * 40, bpm=120.0, start=0.0)
        con.execute("INSERT INTO Track VALUES (?,?,?,?,?,?,?,0)",
                    (i, f"../Music/t{i}.wav", f"T{i}", "A", 120, 120.0, blob))
    con.commit()
    con.close()

    report = tmp_path / "r.csv"
    assert main(["--library", str(lib), "--backend", "librosa", "--jobs", "1",
                 "--report", str(report), "--apply"]) == 0
    assert any(p.name.startswith("backup-gridfix-") for p in (lib / "Database2").iterdir())

    con = sqlite3.connect(db)
    for (tid, bpm_an, bpm_i, blob, locked), (bpm, off) in zip(
        con.execute("SELECT id, bpmAnalyzed, bpm, beatData, isBeatGridLocked FROM Track ORDER BY id"),
        specs,
    ):
        assert bpm_an == pytest.approx(bpm, abs=0.05), tid
        assert bpm_i == round(bpm) and locked == 1
        bd = beatdata.decode(blob)
        assert beatdata.roundtrip_ok(blob)
        per = 60 / bpm
        m = bd.adjusted_grid[0]
        t_beat0 = m.sample_offset / bd.sample_rate - m.beat_number * per
        err = (t_beat0 - off) % per
        assert min(err, per - err) < 0.005, (tid, t_beat0, off)
        bar = 4 * per
        e = (t_beat0 - off) % bar
        assert min(e, bar - e) < 0.005, ("downbeat on wrong beat of the bar", tid)

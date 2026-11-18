"""engine-grid-fix: re-detect beat grids for a whole Engine DJ library.

Default run is a dry run: it analyses every track and writes a CSV report.
Add --apply to write the new grids (a backup of m.db is made first).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from . import beatdata, library
from .analyze import GridFit, analyze


def _engine_running() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        out = subprocess.run(["pgrep", "-if", "Engine DJ"], capture_output=True, text=True)
        return bool(out.stdout.strip())
    except Exception:
        return False


def _cache_key(p: Path) -> str:
    st = p.stat()
    return f"{p}|{st.st_size}|{int(st.st_mtime)}"


def _job(path: str, backend: str):
    try:
        fit = analyze(path, backend)
        return path, (asdict(fit) if fit else None), None
    except Exception as e:  # keep going on broken files
        return path, None, f"{type(e).__name__}: {e}"


def _phase_shift_ms(old: beatdata.BeatData, fit: GridFit) -> float | None:
    """How far the old grid's beats sit from the new grid's beats, in ms."""
    grid = old.adjusted_grid or old.default_grid
    if not grid or old.sample_rate <= 0:
        return None
    t = grid[0].sample_offset / old.sample_rate
    d = (t - fit.downbeat_s) % fit.period_s
    d = min(d, fit.period_s - d)
    return 1000.0 * d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine-grid-fix", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", default=str(library.DEFAULT_MAC_LIBRARY),
                    help="'Engine Library' folder (Mac default: ~/Music/Engine Library)")
    ap.add_argument("--apply", action="store_true", help="write the new grids")
    ap.add_argument("--backend", choices=["librosa", "beat_this", "auto"], default="librosa",
                    help="librosa (default, tested) or beat_this (experimental, needs torch)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--limit", type=int, default=0, help="only the first N tracks (testing)")
    ap.add_argument("--min-confidence", type=float, default=0.7,
                    help="below this the track has unsteady tempo: left for manual fixing")
    ap.add_argument("--include-locked", action="store_true",
                    help="also touch tracks whose grid you locked in Engine")
    ap.add_argument("--no-lock", action="store_true",
                    help="do not lock fixed grids (Engine may re-analyse over them)")
    ap.add_argument("--report", default="gridfix-report.csv")
    args = ap.parse_args(argv)

    db = library.find_db(Path(args.library))
    if args.apply and _engine_running():
        print("Close Engine DJ Desktop first: it keeps m.db open and would overwrite changes.")
        return 2

    con = library.connect(db)
    rows = library.tracks(con)
    if args.limit:
        rows = rows[: args.limit]
    print(f"Library: {db}  tracks: {len(rows)}")

    cache_file = db.parent / "gridfix-cache.json"
    try:
        cache = json.loads(cache_file.read_text())
    except Exception:
        cache = {}

    todo, audio_of = [], {}
    for r in rows:
        a = library.resolve_audio(db, r.path)
        audio_of[r.id] = a
        if a and _cache_key(a) not in cache:
            todo.append(str(a))

    if todo:
        print(f"Analysing {len(todo)} tracks with {args.jobs} worker(s)...")
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futs = [ex.submit(_job, p, args.backend) for p in todo]
            for i, f in enumerate(as_completed(futs), 1):
                p, fit, err = f.result()
                cache[_cache_key(Path(p))] = {"fit": fit, "error": err}
                if i % 10 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}", flush=True)
                    cache_file.write_text(json.dumps(cache))
        cache_file.write_text(json.dumps(cache))

    report, changes = [], []
    for r in rows:
        a = audio_of[r.id]
        rec = {"id": r.id, "artist": r.artist or "", "title": r.title or "", "path": r.path,
               "old_bpm": round(r.bpm_analyzed, 2) if r.bpm_analyzed else "",
               "new_bpm": "", "shift_ms": "", "confidence": "", "action": ""}
        if a is None:
            rec["action"] = "skip: audio file not found"
            report.append(rec)
            continue
        entry = cache.get(_cache_key(a), {})
        if entry.get("error") or not entry.get("fit"):
            rec["action"] = f"skip: analysis failed {entry.get('error') or ''}".strip()
            report.append(rec)
            continue
        fit = GridFit(**entry["fit"])
        rec.update(new_bpm=round(fit.bpm, 2), confidence=round(fit.confidence, 2))

        if r.beat_blob and not beatdata.roundtrip_ok(r.beat_blob):
            rec["action"] = "skip: unknown beatData format (not touched)"
            report.append(rec)
            continue
        old = beatdata.decode(r.beat_blob)
        if old:
            shift = _phase_shift_ms(old, fit)
            rec["shift_ms"] = round(shift, 1) if shift is not None else ""
        if r.locked and not args.include_locked:
            rec["action"] = "skip: grid locked in Engine"
        elif fit.confidence < args.min_confidence:
            rec["action"] = "manual: tempo not steady"
        else:
            old_bpm = r.bpm_analyzed or 0
            shift = rec["shift_ms"] if rec["shift_ms"] != "" else 999
            if abs(old_bpm - fit.bpm) < 0.02 and shift < 10:
                rec["action"] = "ok: grid already good"
            else:
                rec["action"] = "fix"
                changes.append((r, old, fit))
        report.append(rec)

    out = Path(args.report)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(report[0].keys()) if report else ["id"])
        w.writeheader()
        w.writerows(report)

    summary = {}
    for rec in report:
        k = rec["action"].split(":")[0]
        summary[k] = summary.get(k, 0) + 1
    print("Summary:", ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
    print(f"Report: {out.resolve()}")

    if not args.apply:
        print("Dry run. Check the report, then run again with --apply.")
        return 0
    if not changes:
        print("Nothing to write.")
        return 0

    bdir = library.backup(db)
    print(f"Backup: {bdir}")
    with con:
        for r, old, fit in changes:
            sr = old.sample_rate if old and old.sample_rate > 0 else 44100.0
            samples = old.samples if old and old.samples > 0 else fit.duration_s * sr
            grid = beatdata.make_grid(fit.downbeat_s, fit.period_s, samples / sr, sr)
            new = beatdata.BeatData(
                sample_rate=sr, samples=samples, is_beatgrid_set=1,
                default_grid=grid, adjusted_grid=[beatdata.Marker(**vars(m)) for m in grid],
                extra=old.extra if old else b"\x00" * 9,
            )
            library.write_grid(con, r.id, beatdata.encode(new), fit.bpm, lock=not args.no_lock)
    print(f"Wrote {len(changes)} grids. Open Engine DJ Desktop and sync to your USB stick.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

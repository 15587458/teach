"""Access to an Engine DJ library (Engine Library/Database2/m.db)."""

from __future__ import annotations

import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAC_LIBRARY = Path.home() / "Music" / "Engine Library"


@dataclass
class TrackRow:
    id: int
    path: str
    title: str | None
    artist: str | None
    bpm_analyzed: float | None
    locked: bool
    beat_blob: bytes | None


def find_db(library: Path) -> Path:
    library = Path(library).expanduser()
    for cand in (library / "Database2" / "m.db", library / "m.db", library):
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        f"m.db not found under {library}. Point --library at the 'Engine Library' folder "
        "(on the Mac or on the USB stick)."
    )


def backup(db: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest_dir = db.parent / f"backup-gridfix-{stamp}"
    dest_dir.mkdir()
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(db) + suffix)
        if src.exists():
            shutil.copy2(src, dest_dir / src.name)
    return dest_dir


class _Con(sqlite3.Connection):
    cols: set


def connect(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db, timeout=2, factory=_Con)
    con.row_factory = sqlite3.Row
    cols = {r["name"] for r in con.execute("PRAGMA table_info(Track)")}
    needed = {"id", "path", "beatData", "bpmAnalyzed"}
    missing = needed - cols
    if missing:
        raise RuntimeError(
            f"Track table lacks {sorted(missing)}: this is not an Engine DJ 2.x+ library."
        )
    con.execute("PRAGMA busy_timeout=2000")
    con.cols = cols
    return con


def tracks(con: sqlite3.Connection) -> list[TrackRow]:
    has_lock = "isBeatGridLocked" in con.cols  # type: ignore[attr-defined]
    sql = (
        "SELECT id, path, title, artist, bpmAnalyzed, beatData"
        + (", isBeatGridLocked" if has_lock else "")
        + " FROM Track WHERE path IS NOT NULL AND path != ''"
    )
    out = []
    for r in con.execute(sql):
        out.append(
            TrackRow(
                r["id"], r["path"], r["title"], r["artist"], r["bpmAnalyzed"],
                bool(r["isBeatGridLocked"]) if has_lock else False, r["beatData"],
            )
        )
    return out


def resolve_audio(db: Path, track_path: str) -> Path | None:
    """Track.path is stored relative to the 'Engine Library' folder."""
    p = Path(track_path)
    if p.is_absolute():
        return p if p.exists() else None
    for base in (db.parent.parent, db.parent):
        cand = (base / p).resolve()
        if cand.exists():
            return cand
    return None


def write_grid(con, track_id: int, blob: bytes, bpm: float, lock: bool) -> None:
    cols = con.cols  # type: ignore[attr-defined]
    sets = ["beatData = ?", "bpmAnalyzed = ?"]
    args: list = [blob, bpm]
    if "bpm" in cols:
        sets.append("bpm = ?")
        args.append(int(round(bpm)))
    if lock and "isBeatGridLocked" in cols:
        sets.append("isBeatGridLocked = 1")
    args.append(track_id)
    con.execute(f"UPDATE Track SET {', '.join(sets)} WHERE id = ?", args)

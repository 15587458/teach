"""Beat analysis: detect beats per track and fit a constant-tempo grid.

Every track gets its own tempo, so no global BPM range has to be set.
Two backends:

* ``beat_this`` (CPJKU, 2024): neural beat + downbeat tracker. EXPERIMENTAL:
  not yet tested with this tool. Opt-in via --backend beat_this.
  Should get the bar start right more often than librosa.
* ``librosa``: lighter fallback. Good tempo, downbeat is a guess
  (strongest-onset phase), so the bar may be off by 1-3 beats.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class GridFit:
    bpm: float
    period_s: float
    downbeat_s: float  # time of a bar start (beat 0)
    duration_s: float
    confidence: float  # share of detected beats within 40 ms of the grid
    backend: str


def _have_beat_this() -> bool:
    try:
        import beat_this.inference  # noqa: F401

        return True
    except Exception:
        return False


_BT_MODEL = None


def detect_beats(path: str, backend: str = "auto"):
    """Return (beats_s, downbeats_s or None, duration_s, backend_name)."""
    if backend == "auto":
        backend = "beat_this" if _have_beat_this() else "librosa"

    if backend == "beat_this":
        global _BT_MODEL
        from beat_this.inference import File2Beats

        if _BT_MODEL is None:
            _BT_MODEL = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
        beats, downbeats = _BT_MODEL(path)
        import soundfile as sf

        try:
            duration = sf.info(path).duration
        except Exception:
            import librosa

            duration = librosa.get_duration(path=path)
        return np.asarray(beats, float), np.asarray(downbeats, float), duration, "beat_this"

    import librosa

    y, sr = librosa.load(path, sr=22050, mono=True)
    duration = len(y) / sr
    onset = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
    _, beat_frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, tightness=400)
    beats = librosa.frames_to_time(beat_frames, sr=sr)
    # Downbeat guess: phase (mod 4) with the strongest low-frequency energy.
    downbeats = None
    if len(beats) >= 16:
        S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
        low = S[: int(150 / (sr / 2048))].sum(axis=0)
        idx = np.clip(librosa.time_to_frames(beats, sr=sr, hop_length=512), 0, len(low) - 1)
        e = low[idx]
        phase = int(np.argmax([e[k::4].mean() for k in range(4)]))
        downbeats = beats[phase::4]
    return beats, downbeats, duration, "librosa"


def fit_grid(
    beats: np.ndarray,
    downbeats: np.ndarray | None,
    duration: float,
    backend: str,
    snap: float = 0.03,
    min_bpm: float = 60.0,
    max_bpm: float = 200.0,
) -> GridFit | None:
    """Robust constant-tempo fit through detected beat times."""
    beats = np.sort(np.asarray(beats, float))
    if len(beats) < 8:
        return None

    diffs = np.diff(beats)
    med = float(np.median(diffs))
    close = diffs[np.abs(diffs - med) < 0.1 * med]
    period = float(close.mean()) if len(close) else med
    for _ in range(3):  # iterative least squares, dropping outliers
        # Beat indices from consecutive gaps: robust to missed/extra beats and
        # does not drift on long tracks when the first period guess is off.
        steps = np.maximum(np.round(diffs / period), 0)
        n = np.concatenate([[0.0], np.cumsum(steps)])
        A = np.vstack([np.ones_like(n), n]).T
        resid_mask = np.ones(len(beats), bool)
        for _ in range(3):
            coef, *_ = np.linalg.lstsq(A[resid_mask], beats[resid_mask], rcond=None)
            r = np.abs(A @ coef - beats)
            resid_mask = r < max(0.04, 3 * np.median(r))
        period = float(coef[1])

    bpm = 60.0 / period
    # Octave safety for the fallback backend only; beat_this is reliable.
    if backend != "beat_this":
        while bpm < min_bpm:
            bpm *= 2
        while bpm > max_bpm:
            bpm /= 2
    # Most produced music sits on an integer (or .5) BPM.
    for step in (1.0, 0.5):
        cand = round(bpm / step) * step
        if abs(cand - bpm) < snap:
            bpm = cand
            break
    period = 60.0 / bpm

    # Phase: median offset of beats relative to the fixed-period grid.
    n = np.round((beats - beats[0]) / period)
    phase = float(np.median(beats - n * period))
    grid_n = np.round((beats - phase) / period)
    err = np.abs(beats - (phase + grid_n * period))
    confidence = float(np.mean(err < 0.04))

    # Choose which grid beat is the bar start.
    anchor = phase
    if downbeats is not None and len(downbeats) >= 2:
        k = np.round((np.asarray(downbeats) - phase) / period).astype(int) % 4
        best = int(np.bincount(k, minlength=4).argmax())
        anchor = phase + best * period
    # Move the anchor to the first bar start inside the track.
    anchor -= 4 * period * math.floor(anchor / (4 * period))

    return GridFit(bpm, period, anchor, duration, confidence, backend)


def refine_phase(path: str, fit: GridFit, window_s: float = 0.04) -> GridFit:
    """Nudge the grid (within +/- window_s) onto the sharpest transients.

    Beat trackers work on 10-23 ms frames, which is audible when beatmatching.
    Here a fine onset envelope (~3 ms hop) is sampled at every grid position
    and the offset with the highest mean onset strength wins. The window is
    kept small so the grid cannot jump onto off-beat hi-hats.
    """
    import librosa

    sr, hop = 44100, 128
    y, _ = librosa.load(path, sr=sr, mono=True)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, n_fft=1024,
                                       aggregate=np.median, center=True)
    frame_s = hop / sr
    grid = fit.downbeat_s + fit.period_s * np.arange(
        -math.floor(fit.downbeat_s / fit.period_s),
        math.floor((fit.duration_s - fit.downbeat_s) / fit.period_s),
    )
    best_off, best_score = 0.0, -1.0
    for off in np.arange(-window_s, window_s + 1e-9, 0.001):
        idx = np.round((grid + off) / frame_s).astype(int)
        idx = idx[(idx >= 0) & (idx < len(env))]
        if len(idx) == 0:
            continue
        score = float(env[idx].mean())
        if score > best_score:
            best_off, best_score = float(off), score
    down = fit.downbeat_s + best_off
    down -= 4 * fit.period_s * math.floor(down / (4 * fit.period_s))
    return GridFit(fit.bpm, fit.period_s, down, fit.duration_s, fit.confidence, fit.backend)


def analyze(path: str, backend: str = "auto", refine: bool = True) -> GridFit | None:
    beats, downbeats, duration, used = detect_beats(path, backend)
    fit = fit_grid(beats, downbeats, duration, used)
    if fit and refine:
        fit = refine_phase(path, fit)
    return fit

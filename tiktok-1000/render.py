"""Рендер TikTok-ролика «Как заработать первые $1000» (1080x1920, 30 fps).

Запуск:  python3 voices.py && python3 render.py   ->  out/first_1000.mp4
Опции:   --preview T1,T2,...  — сохранить кадры в build/preview/ вместо видео
"""
import math
import os
import random
import subprocess
import sys
import wave
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import chars
from script import GOAL, LINES, SCENES, START_MONEY

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(ROOT, "out")
W, H, FPS, SR = 1080, 1920, 30, 44100
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

FEET_Y = 1650
COUNTER_Y = 200
HEADER_Y = 318
PROPS_Y = 622
BUBBLE_BOTTOM = 1062

ACCENT = {"max": (20, 160, 150), "liza": (235, 80, 90), "nar": (255, 196, 0)}
NAMES = {"max": "МАКС", "liza": "ЛИЗА", "nar": "ГОЛОС"}


# ----------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease_out_back(x, s=1.70158):
    x = clamp(x) - 1
    return x * x * ((s + 1) * x + s) + 1


def ease_out_cubic(x):
    return 1 - (1 - clamp(x)) ** 3


def ease_in_cubic(x):
    return clamp(x) ** 3


def ease_in_out(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out_bounce(x):
    x = clamp(x)
    n, d = 7.5625, 2.75
    if x < 1 / d:
        return n * x * x
    if x < 2 / d:
        x -= 1.5 / d
        return n * x * x + 0.75
    if x < 2.5 / d:
        x -= 2.25 / d
        return n * x * x + 0.9375
    x -= 2.625 / d
    return n * x * x + 0.984375


def lerp(a, b, t):
    return a + (b - a) * t


# ----------------------------------------------------------------- fonts / glyphs
@lru_cache(maxsize=64)
def font(size, weight=900):
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Rubik-{weight}.ttf"), size)


@lru_cache(maxsize=1)
def _efont():
    return ImageFont.truetype(EMOJI_FONT, 109)


def is_emoji_char(ch):
    o = ord(ch)
    return o >= 0x2300 or o in (0xFE0F, 0x20E3)


def is_emoji_word(w):
    return any(is_emoji_char(c) for c in w)


@lru_cache(maxsize=512)
def emoji(e, size):
    im = Image.new("RGBA", (220, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), e, font=_efont(), embedded_color=True)
    im = im.crop(im.getbbox())
    s = size / max(im.size)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)


def paste(dst, src, x, y):
    """alpha_composite с обрезкой по краям; x, y — левый верхний угол."""
    x, y = int(round(x)), int(round(y))
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(src.width, W - x), min(src.height, H - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    if (sx0, sy0, sx1, sy1) != (0, 0, src.width, src.height):
        src = src.crop((sx0, sy0, sx1, sy1))
    dst.alpha_composite(src, (x + sx0, y + sy0))


def paste_c(dst, src, cx, cy, scale=1.0, alpha=1.0, angle=0.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    if abs(scale - 1) > 1e-3:
        src = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.BILINEAR)
    if angle:
        src = src.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999:
        src = src.copy()
        a = src.getchannel("A").point(lambda v: int(v * alpha))
        src.putalpha(a)
    paste(dst, src, cx - src.width / 2, cy - src.height / 2)


def text_img(txt, size, weight=900, fill=(255, 255, 255), stroke=0, stroke_fill=(30, 20, 40), shadow=True):
    f = font(size, weight)
    bb = f.getbbox(txt, stroke_width=stroke)
    w, h = bb[2] - bb[0] + 20, bb[3] - bb[1] + 24
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((10 - bb[0], 16 - bb[1]), txt, font=f, fill=(0, 0, 0, 110),
                                stroke_width=stroke, stroke_fill=(0, 0, 0, 110))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)))
    d.text((10 - bb[0], 10 - bb[1]), txt, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    return im


# ----------------------------------------------------------------- timeline
def read_wav(path):
    with wave.open(path) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return a


def build_timeline():
    t = 0.45
    prev_scene = None
    tl = []
    scene_start = {}
    for i, ln in enumerate(LINES):
        a = read_wav(os.path.join(BUILD, "voice", f"{i:02d}.wav"))
        dur = len(a) / SR
        if ln["scene"] != prev_scene:
            if prev_scene is not None:
                t += 0.55
            scene_start[ln["scene"]] = 0.0 if prev_scene is None else t - 0.4
            prev_scene = ln["scene"]
        # огибающая для липсинка (на кадр)
        hop = SR // FPS
        n = int(math.ceil(len(a) / hop))
        env = np.array([np.sqrt(np.mean(a[k * hop:(k + 1) * hop] ** 2) + 1e-9) for k in range(n)])
        ref = np.percentile(env, 85) + 1e-6
        env = np.clip(env / ref, 0, 1.2)
        tl.append(dict(i=i, start=t, dur=dur, end=t + dur, env=env, audio=a, **ln))
        gap = 0.32
        if ln["tts"].endswith("..."):
            gap = 0.7
        t += dur + gap
    end_card = t + 0.1
    total = end_card + 3.6
    return tl, scene_start, end_card, total


TL, SCENE_START, END_CARD, TOTAL = build_timeline()
SCENE_IDS = [s["id"] for s in SCENES]
SCENE_BY_ID = {s["id"]: s for s in SCENES}


def events():
    """Абсолютные события: money, props, jump, sneaker, stop, confetti, tags."""
    ev = []
    for ln in TL:
        for off, kind, arg in ln.get("fx", []):
            at = ln["start"] + off if off >= 0 else ln["end"] + off
            ev.append((at, kind, arg, ln))
    ev.sort(key=lambda e: e[0])
    return ev


EVENTS = events()
MONEY = []  # (t, from, to)
_m = START_MONEY
for at, kind, arg, _ in EVENTS:
    if kind == "money":
        MONEY.append((at, _m, _m + arg, arg))
        _m += arg
STOP_T = next(at for at, k, _, _ in EVENTS if k == "stop")
CONFETTI_T = next(at for at, k, _, _ in EVENTS if k == "confetti")
SNEAKER_T = next(at for at, k, _, _ in EVENTS if k == "sneaker")


def scene_at(t):
    cur = SCENE_IDS[0]
    for sid in SCENE_IDS:
        if t >= SCENE_START[sid]:
            cur = sid
    return cur


def line_at(t):
    """Текущая реплика (держится до начала следующей)."""
    cur = None
    for ln in TL:
        if t >= ln["start"] - 0.05:
            cur = ln
    return cur


# ----------------------------------------------------------------- background
@lru_cache(maxsize=16)
def gradient(sid):
    c1, c2 = SCENE_BY_ID[sid]["bg"]
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(-1, 1, W)[None, :]
    g = np.clip(y * 0.85 + x * 0.12 + 0.05, 0, 1)[..., None]
    img = np.array(c1)[None, None] * (1 - g) + np.array(c2)[None, None] * g
    # мягкое пятно света и виньетка
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W * 0.5) / W) ** 2 + ((yy - H * 0.38) / H) ** 2)
    img = img * (1.12 - 0.55 * d[..., None] ** 1.5)
    img += np.clip(0.35 - d, 0, 1)[..., None] * 60
    return np.clip(img, 0, 255).astype(np.uint8)


@lru_cache(maxsize=8)
def bokeh_sprite(r):
    s = r * 2
    yy, xx = np.mgrid[0:s, 0:s]
    d = np.sqrt((xx - r) ** 2 + (yy - r) ** 2) / r
    a = np.clip(1 - d, 0, 1) ** 1.4 * 70
    im = np.zeros((s, s, 4), np.uint8)
    im[..., :3] = 255
    im[..., 3] = a.astype(np.uint8)
    return Image.fromarray(im, "RGBA")


_rng = random.Random(7)
BOKEH = [(_rng.uniform(0, W), _rng.uniform(0, H), _rng.choice([40, 60, 90, 130]), _rng.uniform(15, 45),
          _rng.uniform(0, 6.28)) for _ in range(14)]
DOLLARS = [(_rng.uniform(0, W), _rng.uniform(0, H), _rng.uniform(60, 140), _rng.uniform(20, 50),
            _rng.uniform(-25, 25)) for _ in range(7)]


@lru_cache(maxsize=4)
def dollar_glyph(size):
    return text_img("$", size, 900, fill=(255, 255, 255, 38), shadow=False)


def draw_background(t):
    sid = scene_at(t)
    idx = SCENE_IDS.index(sid)
    base = gradient(sid)
    ts = SCENE_START[sid]
    if idx > 0 and t < ts + 0.5:
        p = ease_in_out((t - ts) / 0.5)
        prev = gradient(SCENE_IDS[idx - 1])
        base = (prev * (1 - p) + base * p).astype(np.uint8)
    im = Image.fromarray(base, "RGB").convert("RGBA")
    for x, y, r, sp, ph in BOKEH:
        yy = (y - t * sp) % (H + 300) - 150
        xx = x + math.sin(t * 0.5 + ph) * 30
        paste(im, bokeh_sprite(r), xx - r, yy - r)
    for x, y, sz, sp, ang in DOLLARS:
        yy = (y - t * sp) % (H + 300) - 150
        g = dollar_glyph(int(sz))
        paste_c(im, g, x + math.sin(t * 0.7 + x) * 20, yy, angle=ang + math.sin(t + y) * 8)
    return im


@lru_cache(maxsize=1)
def floor_shadow():
    im = Image.new("RGBA", (360, 70), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((10, 10, 350, 60), fill=(0, 0, 0, 70))
    return im.filter(ImageFilter.GaussianBlur(8))


# ----------------------------------------------------------------- header
@lru_cache(maxsize=16)
def header_img(sid):
    sc = SCENE_BY_ID[sid]
    parts = []
    if sc["step"]:
        f = font(44, 900)
        tw = int(f.getlength(sc["step"]))
        pill = Image.new("RGBA", (tw + 60, 72), (0, 0, 0, 0))
        d = ImageDraw.Draw(pill)
        d.rounded_rectangle((0, 0, tw + 59, 71), radius=36, fill=(255, 214, 10))
        d.text(((tw + 60) / 2, 37), sc["step"], font=f, fill=(35, 25, 45), anchor="mm")
        parts.append(pill)
    size = 96
    while font(size).getlength(sc["title"]) > 960:
        size -= 4
    parts.append(text_img(sc["title"], size, 900, stroke=7))
    parts.append(text_img(sc["sub"], 40, 700, fill=(255, 255, 255, 235), stroke=3))
    wd = max(p.width for p in parts)
    ht = sum(p.height for p in parts) - 8 * (len(parts) - 1)
    im = Image.new("RGBA", (wd, ht), (0, 0, 0, 0))
    y = 0
    for p in parts:
        im.alpha_composite(p, ((wd - p.width) // 2, y))
        y += p.height - 8
    return im


def draw_header(im, t):
    sid = scene_at(t)
    idx = SCENE_IDS.index(sid)
    ts = SCENE_START[sid]
    nxt = SCENE_START[SCENE_IDS[idx + 1]] if idx + 1 < len(SCENE_IDS) else 1e9
    h = header_img(sid)
    cx = W / 2
    scale = 1.0
    if idx == 0:
        scale = ease_out_back((t - 0.0) / 0.45, 2.2) if t < 0.45 else 1.0
    else:
        p = (t - ts - 0.15) / 0.55
        cx = lerp(W * 1.6, W / 2, ease_out_back(p, 1.2))
    if t > nxt - 0.35:
        cx -= ease_in_cubic((t - (nxt - 0.35)) / 0.35) * W * 1.2
    # лёгкое «дыхание» заголовка
    scale *= 1 + 0.015 * math.sin(t * 3.0)
    paste_c(im, h, cx, HEADER_Y + h.height / 2, scale=max(scale, 0.01))


# ----------------------------------------------------------------- props
@lru_cache(maxsize=32)
def tag_img(txt):
    f = font(50, 900)
    tw = int(f.getlength(txt))
    im = Image.new("RGBA", (tw + 44, 76), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, tw + 43, 75), radius=20, fill=(46, 204, 113), outline=(255, 255, 255), width=4)
    d.text(((tw + 44) / 2, 39), txt, font=f, fill=(255, 255, 255), anchor="mm")
    return im


def props_state(t):
    """Активная группа props (с моментом появления) и предыдущая (для исчезновения)."""
    groups = [(at, arg, ln) for at, k, arg, ln in EVENTS if k == "props"]
    # смена сцены тоже убирает props
    cur, prev = None, None
    for g in groups:
        if t >= g[0]:
            prev, cur = cur, g
    if cur and scene_at(t) != cur[2]["scene"]:
        prev, cur = cur, None
    return cur, prev


def draw_props(im, t):
    if t >= END_CARD + 0.15:
        return
    cur, prev = props_state(t)
    xs = [230, 540, 850]

    def draw_group(g, mode):
        at, items, ln = g
        for k, e in enumerate(items):
            t0 = at + k * 0.14
            if mode == "in":
                s = ease_out_back((t - t0) / 0.4, 2.4)
                a = 1.0
            else:
                end = max(at + 0.5, next_change(at))
                s = 1 - ease_in_cubic((t - end) / 0.25)
                a = s
            if s <= 0:
                continue
            fy = math.sin(t * 2.4 + k * 1.7) * 12
            ang = math.sin(t * 1.8 + k) * 7
            paste_c(im, emoji(e, 125), xs[k], PROPS_Y + fy, scale=s, alpha=a, angle=ang)

    if prev:
        draw_group(prev, "out")
    if cur:
        draw_group(cur, "in")

    # ценники на шаге 2
    for at, k, arg, ln in EVENTS:
        if k == "tags" and scene_at(t) == ln["scene"]:
            for j, tg in enumerate(arg):
                t0 = at + 0.35 + j * 0.45
                if t < t0:
                    continue
                s = ease_out_back((t - t0) / 0.35, 2.5)
                paste_c(im, tag_img(tg), xs[j] + 55, PROPS_Y + 50 + math.sin(t * 3 + j) * 5, scale=s,
                        angle=-10 + j * 8)


def next_change(at):
    """Когда группа props, появившаяся в at, сменяется (следующая группа или смена сцены)."""
    later = [a for a, k, _, _ in EVENTS if k == "props" and a > at + 1e-6]
    sc = scene_at(at)
    idx = SCENE_IDS.index(sc)
    nxt_scene = SCENE_START[SCENE_IDS[idx + 1]] if idx + 1 < len(SCENE_IDS) else 1e9
    return min(later[0] if later else 1e9, nxt_scene)


# ----------------------------------------------------------------- sneaker / stop gag
def draw_gag(im, t, shake):
    if t < SNEAKER_T or scene_at(t) != "twist":
        return
    gone = next(a for a, k, _, _ in EVENTS if k == "props" and a > STOP_T)
    if t > gone + 0.3:
        return
    out = 1 - ease_in_cubic((t - gone) / 0.3) if t > gone else 1
    s = ease_out_back((t - SNEAKER_T) / 0.5, 2.0) * out
    ang = math.sin(t * 4) * 10 if t < STOP_T else 0
    paste_c(im, emoji("👟", 200), W / 2, PROPS_Y - 10, scale=s, angle=ang)
    if t < STOP_T:
        for k in range(5):
            ph = (t * 1.6 + k / 5) % 1
            a = math.sin(ph * math.pi)
            r = 170
            ax = W / 2 + math.cos(k * 1.3 + 1) * r
            ay = PROPS_Y - 10 + math.sin(k * 2.1) * r * 0.6
            paste_c(im, emoji("✨", 70), ax, ay, scale=0.6 + 0.6 * a, alpha=a)
    else:
        # красный крест + штамп СТОП
        p = (t - STOP_T)
        paste_c(im, emoji("❌", 220), W / 2, PROPS_Y - 10, scale=ease_out_back(p / 0.25, 3) * out)


def draw_stamp(im, t):
    p = t - STOP_T
    if 0 <= p < 1.6:
        sc = lerp(2.6, 1.0, ease_out_cubic(p / 0.22)) if p < 0.22 else 1.0
        a = clamp(p / 0.08) * (1 - clamp((p - 1.3) / 0.3))
        paste_c(im, stamp_img(), W / 2, 1330, scale=sc, alpha=a, angle=-8)


@lru_cache(maxsize=1)
def stamp_img():
    f = font(150, 900)
    tw = int(f.getlength("СТОП!"))
    im = Image.new("RGBA", (tw + 90, 230), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 8, tw + 82, 222), radius=30, outline=(230, 30, 50), width=16, fill=(255, 255, 255, 230))
    d.text(((tw + 90) / 2, 118), "СТОП!", font=f, fill=(230, 30, 50), anchor="mm")
    return im


# ----------------------------------------------------------------- characters
def blink_at(t, seed):
    r = random.Random(seed)
    tt = r.uniform(0.5, 2.0)
    while tt < t + 0.2:
        if tt <= t < tt + 0.13:
            return True
        tt += r.uniform(2.2, 4.2)
    return False


def char_state(name, t):
    ln = line_at(t)
    emo, pose, mouth, look = "normal", "idle", 0, 0
    bounce = 0.0
    if ln:
        speaking = ln["speaker"] == name and ln["start"] <= t < ln["end"]
        if ln["speaker"] == name:
            emo, pose = ln["emo"], ln["pose"]
        elif ln["speaker"] == "nar":
            emo = ln.get("other", "normal") if name == "max" else "normal"
            if ln["scene"] == "final":
                emo = "happy"
        else:
            emo = ln.get("other", "normal")
            look = 1  # смотрит на говорящего (для Лизы спрайт отражён)
            if emo == "think":
                pose = "think"
        if speaking:
            k = int((t - ln["start"]) * FPS)
            if k < len(ln["env"]):
                v = ln["env"][k]
                mouth = int(round(clamp(v) * 5))
                bounce = v * 9
    # позы финала / концовки
    if t >= END_CARD:
        emo, pose, mouth = "happy", "wave", 0
    return emo, pose, mouth, look, bounce


def char_x(name, t):
    liza_in = TL[1]["start"] - 0.75
    if name == "max":
        if t < liza_in:
            return W / 2
        return lerp(W / 2, 300, ease_out_back((t - liza_in) / 0.7, 1.4))
    return lerp(W + 300, 770, ease_out_back((t - liza_in) / 0.7, 1.3))


def jump_offset(name, t):
    off = 0.0
    for at, k, arg, _ in EVENTS:
        if k == "jump" and arg in (name, "both"):
            p = (t - at) / 0.5
            if 0 <= p <= 1:
                off -= math.sin(p * math.pi) * 85
    if name == "max":
        # эффектное появление в начале: падение сверху с отскоком
        if t < 0.55:
            off -= (1 - ease_out_bounce(t / 0.55)) * 900
    if STOP_T <= t < STOP_T + 0.35 and name == "max":
        off += math.sin((t - STOP_T) / 0.35 * math.pi) * 20  # присел от испуга
    return off


def draw_characters(im, t):
    for name in ("max", "liza"):
        x = char_x(name, t)
        if x > W + 250:
            continue
        emo, pose, mouth, look, bounce = char_state(name, t)
        blink = blink_at(t, 11 if name == "max" else 23)
        breathe = math.sin(t * 2.6 + (0 if name == "max" else 1.4)) * 5
        sp = chars.sprite(name, emo, pose, mouth, blink, look, flip=(name == "liza"))
        jy = jump_offset(name, t)
        sh = floor_shadow()
        ss = clamp(1 + jy / 600, 0.4, 1)
        paste_c(im, sh, x, FEET_Y - 8, scale=ss)
        paste(im, sp, x - chars.SW / 2, FEET_Y - chars.FEET + breathe - bounce + jy)


# ----------------------------------------------------------------- speech bubble (karaoke)
def word_timings(ln):
    words = ln["cap"].split()
    wts = []
    for w in words:
        if is_emoji_word(w) and not any(c.isalnum() for c in w):
            wts.append(0.0)
            continue
        base = sum(1 for c in w if c.isalnum()) + 1.5
        if w[-1] in ",.!?…:" or w.endswith("..."):
            base += 3
        wts.append(base)
    tot = sum(wts) or 1
    acc, out = 0.0, []
    for wt in wts:
        out.append(acc / tot * ln["dur"])
        acc += wt
    return words, out


def split_runs(w):
    runs, cur, cur_e = [], "", None
    i = 0
    while i < len(w):
        ch = w[i]
        e = is_emoji_char(ch)
        if ch in "️⃣" and runs is not None:
            e = True
        if cur_e is None or e == cur_e:
            cur += ch
        else:
            runs.append((cur, cur_e))
            cur = ch
        cur_e = e
        i += 1
    if cur:
        runs.append((cur, cur_e))
    return runs


FS = 56


def word_width(w, f):
    tot = 0
    for txt, e in split_runs(w):
        tot += int(FS * 1.08) * len([c for c in txt if c not in "️⃣"]) if e else f.getlength(txt)
    return tot


@lru_cache(maxsize=64)
def bubble_layout(i):
    ln = TL[i]
    words, _ = word_timings(ln)
    f = font(FS, 800)
    maxw = 860
    space = f.getlength(" ")
    lines, cur, cw = [], [], 0
    for k, w in enumerate(words):
        ww = word_width(w, f)
        if cur and cw + space + ww > maxw:
            lines.append(cur)
            cur, cw = [], 0
        cur.append((k, w, ww))
        cw += (space if cw else 0) + ww
    if cur:
        lines.append(cur)
    widths = [sum(x[2] for x in l) + space * (len(l) - 1) for l in lines]
    return lines, widths, space


@lru_cache(maxsize=1024)
def bubble_img(i, cur_word):
    ln = TL[i]
    lines, widths, space = bubble_layout(i)
    f = font(FS, 800)
    lh = int(FS * 1.22)
    pad_x, pad_y = 44, 38
    bw = int(max(widths)) + pad_x * 2
    bh = lh * len(lines) + pad_y * 2 - 6
    nar = ln["speaker"] == "nar"
    acc = ACCENT[ln["speaker"]]
    tag_h = 50
    im = Image.new("RGBA", (bw + 30, bh + tag_h + 30), (0, 0, 0, 0))
    # тень
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((15, tag_h // 2 + 22, bw + 15, tag_h // 2 + bh + 22), radius=46,
                                         fill=(0, 0, 0, 90))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im)
    y0 = tag_h // 2 + 8
    if nar:
        d.rounded_rectangle((15, y0, bw + 15, y0 + bh), radius=46, fill=(25, 20, 40, 235),
                            outline=acc, width=5)
    else:
        d.rounded_rectangle((15, y0, bw + 15, y0 + bh), radius=46, fill=(255, 255, 255, 250),
                            outline=(40, 30, 45), width=5)
    # бейдж с именем
    tf = font(30, 900)
    label = ("🎙 " if False else "") + NAMES[ln["speaker"]]
    lw = int(tf.getlength(label)) + 40
    d.rounded_rectangle((40, 6, 40 + lw, 6 + tag_h), radius=25, fill=acc, outline=(40, 30, 45), width=4)
    d.text((40 + lw / 2, 6 + tag_h / 2 + 2), label, font=tf, fill=(40, 30, 45) if nar else (255, 255, 255),
           anchor="mm")
    # текст
    base_col = (255, 255, 255) if nar else (40, 30, 45)
    dim_col = (150, 145, 170) if nar else (175, 170, 185)
    hi_col = (255, 210, 0) if nar else acc
    y = y0 + pad_y - 6
    for l, wd in zip(lines, widths):
        x = 15 + (bw - wd) / 2
        for k, w, ww in l:
            col = base_col if k < cur_word else hi_col if k == cur_word else dim_col
            xx = x
            for txt, e in split_runs(w):
                if e:
                    for ch in txt:
                        if ch in "️⃣":
                            continue
                        em = emoji(ch, int(FS * 0.95))
                        if k > cur_word:
                            em = em.copy()
                            em.putalpha(em.getchannel("A").point(lambda v: v // 3))
                        im.alpha_composite(em, (int(xx), int(y + FS * 0.08)))
                        xx += int(FS * 1.08)
                else:
                    d.text((xx, y), txt, font=f, fill=col)
                    xx += f.getlength(txt)
            x += ww + space
        y += lh
    return im


def draw_bubble(im, t):
    ln = line_at(t)
    if not ln or t >= END_CARD:
        return
    words, times = word_timings(ln)
    tau = t - ln["start"]
    cur = 0
    for k, wt in enumerate(times):
        if tau >= wt:
            cur = k
    if tau >= ln["dur"] - 0.05:
        cur = len(words)
    # emoji-«слова» подсвечиваются вместе с предыдущим словом
    while cur < len(words) and cur > 0 and is_emoji_word(words[cur]) and not any(c.isalnum() for c in words[cur]):
        cur += 1
    b = bubble_img(ln["i"], cur)
    sx = char_x(ln["speaker"], t) if ln["speaker"] != "nar" else W / 2
    cx = clamp(sx, b.width / 2 + 25, W - b.width / 2 - 25)
    p = (t - ln["start"] + 0.05) / 0.25
    s = ease_out_back(p, 2.0)
    cy = BUBBLE_BOTTOM - b.height / 2
    floaty = math.sin(t * 2.2) * 4
    paste_c(im, b, cx, cy + floaty + (1 - s) * 40, scale=lerp(0.6, 1.0, s), alpha=clamp(p * 2))
    if ln["speaker"] != "nar" and p >= 1.0:
        d = ImageDraw.Draw(im)
        edge = cy + floaty + b.height / 2 - 47
        bx = clamp(sx, cx - b.width / 2 + 90, cx + b.width / 2 - 90)
        tip = (sx + (30 if ln["speaker"] == "max" else -30), edge + 58)
        l, r = (bx - 26, edge - 3), (bx + 26, edge - 3)
        d.polygon([l, r, tip], fill=(255, 255, 255))
        d.line([l, tip, r], fill=(40, 30, 45), width=5, joint="curve")


# ----------------------------------------------------------------- money counter + coins
def money_value(t):
    v = START_MONEY
    for at, a, b, _ in MONEY:
        if t >= at:
            v = lerp(a, b, ease_out_cubic((t - at - 0.55) / 1.1))
    return v


@lru_cache(maxsize=1)
def coin_img():
    s = 3
    im = Image.new("RGBA", (80 * s, 80 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((4 * s, 4 * s, 76 * s, 76 * s), fill=(255, 200, 30), outline=(170, 110, 0), width=5 * s)
    d.ellipse((14 * s, 14 * s, 66 * s, 66 * s), outline=(255, 235, 140), width=3 * s)
    d.text((40 * s, 42 * s), "$", font=font(44 * s, 900), fill=(170, 110, 0), anchor="mm")
    return im.resize((80, 80), Image.LANCZOS)


def draw_counter(im, t):
    v = money_value(t)
    pop = 0.0
    gold = False
    for at, a, b, add in MONEY:
        p = t - at - 0.55
        if 0 <= p < 1.4:
            pop = max(pop, math.sin(clamp(p / 0.35) * math.pi) * 0.14)
            gold = p < 1.2
    done = v >= GOAL
    num = f"${int(round(v))}"
    col = (255, 215, 0) if (gold or done) else (255, 90, 90) if v < 10 else (255, 255, 255)
    f = font(92, 900)
    tw = int(f.getlength(num))
    pw = max(tw + 190, 420)
    panel = Image.new("RGBA", (pw, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle((0, 0, pw - 1, 149), radius=75, fill=(20, 15, 35, 190),
                        outline=(255, 215, 0) if done else (255, 255, 255, 120), width=5)
    panel.alpha_composite(emoji("💰", 86), (34, 30))
    d.text((140, 76), num, font=f, fill=col, anchor="lm", stroke_width=3, stroke_fill=(20, 15, 35))
    s = 1 + pop + (0.04 * math.sin(t * 8) if done else 0)
    paste_c(im, panel, W / 2, COUNTER_Y, scale=s)
    # прогресс-бар
    bw, bh = 560, 26
    bar = Image.new("RGBA", (bw + 8, bh + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(bar)
    d.rounded_rectangle((0, 0, bw + 7, bh + 7), radius=17, fill=(20, 15, 35, 170))
    fr = clamp(v / GOAL)
    if fr > 0.01:
        d.rounded_rectangle((4, 4, 4 + max(bh, int(bw * fr)), 4 + bh), radius=13,
                            fill=(255, 215, 0) if done else (46, 230, 130))
    paste_c(im, bar, W / 2, COUNTER_Y + 100)
    lab = goal_label()
    paste_c(im, lab, W / 2 + bw / 2 + 4 - lab.width / 2 + 60, COUNTER_Y + 100)

    # монетки, летящие в счётчик, и «+N$»
    coin = coin_img()
    for at, a, b, add in MONEY:
        for k in range(10):
            t0 = at + k * 0.055
            p = (t - t0) / 0.65
            if 0 <= p <= 1:
                r = random.Random(int(at * 100) + k)
                sx, sy = r.uniform(250, 830), r.uniform(1000, 1250)
                ex, ey = W / 2 - 150, COUNTER_Y
                cx_, cy_ = lerp(sx, ex, 0.5) + r.uniform(-300, 300), min(sy, ey) - r.uniform(50, 250)
                q = ease_in_cubic(p) * 0.6 + p * 0.4
                x = (1 - q) ** 2 * sx + 2 * (1 - q) * q * cx_ + q * q * ex
                y = (1 - q) ** 2 * sy + 2 * (1 - q) * q * cy_ + q * q * ey
                paste_c(im, coin, x, y, scale=lerp(1.1, 0.55, p), angle=p * 360 * (1 if k % 2 else -1))
        p = (t - at - 0.55) / 1.3
        if 0 <= p <= 1:
            lb = plus_img(add)
            paste_c(im, lb, W / 2 + 330, COUNTER_Y - 10 - p * 90, scale=ease_out_back(p * 4, 2.5),
                    alpha=1 - clamp((p - 0.7) / 0.3))


@lru_cache(maxsize=1)
def goal_label():
    return text_img("", 10, shadow=False)


@lru_cache(maxsize=16)
def plus_img(add):
    return text_img(f"+{add}$", 70, 900, fill=(70, 255, 150), stroke=5, stroke_fill=(10, 60, 30))


# ----------------------------------------------------------------- confetti
_cr = random.Random(99)
CONF = []
for k in range(170):
    side = k % 2
    CONF.append(dict(
        x0=-40 if side == 0 else W + 40, y0=_cr.uniform(1100, 1500),
        vx=(_cr.uniform(400, 1100)) * (1 if side == 0 else -1), vy=-_cr.uniform(1300, 2300),
        delay=_cr.uniform(0, 0.35), rot=_cr.uniform(0, 360), vr=_cr.uniform(-720, 720),
        col=_cr.choice([(255, 214, 10), (255, 89, 94), (138, 201, 38), (25, 130, 196), (106, 76, 147),
                        (255, 255, 255), (255, 146, 76)]),
        w=_cr.uniform(14, 24), h=_cr.uniform(24, 40), sway=_cr.uniform(0, 6.28)))


def draw_confetti(im, t, t0):
    if t < t0:
        return
    d = ImageDraw.Draw(im)
    for c in CONF:
        tt = t - t0 - c["delay"]
        if tt < 0:
            continue
        drag = 1.6
        vx = c["vx"] * math.exp(-drag * tt)
        x = c["x0"] + c["vx"] / drag * (1 - math.exp(-drag * tt)) + math.sin(tt * 3 + c["sway"]) * 30 * clamp(tt)
        # вертикаль: бросок вверх, затем медленное падение
        vt = 380
        y = c["y0"] + (c["vy"] + vt) / drag * (1 - math.exp(-drag * tt)) - vt * tt * -1 * 1
        y = c["y0"] + (c["vy"] - vt) / drag * (1 - math.exp(-drag * tt)) + vt * tt
        if y > H + 50:
            continue
        a = math.radians(c["rot"] + c["vr"] * tt)
        flip = abs(math.cos(tt * 6 + c["sway"]))
        hw, hh = c["w"] / 2 * (0.3 + 0.7 * flip), c["h"] / 2
        ca, sa = math.cos(a), math.sin(a)
        pts = [(x + ca * px - sa * py, y + sa * px + ca * py) for px, py in
               ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
        d.polygon(pts, fill=c["col"])
        _ = vx


# ----------------------------------------------------------------- end card
@lru_cache(maxsize=1)
def end_card_img():
    parts = [text_img("Какой шаг попробуешь", 64, 900, stroke=5),
             text_img("первым? Пиши в комменты 👇".replace("👇", ""), 64, 900, stroke=5)]
    w = max(p.width for p in parts) + 120
    im = Image.new("RGBA", (w, 330), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, 329), radius=50, fill=(20, 15, 35, 215), outline=(255, 215, 0), width=6)
    y = 40
    for p in parts:
        im.alpha_composite(p, ((w - p.width) // 2, y))
        y += p.height + 4
    sub = text_img("❤️ Сохрани, чтобы не потерять".replace("❤️ ", ""), 42, 700, fill=(255, 215, 0), shadow=False)
    im.alpha_composite(sub, ((w - sub.width) // 2, 250))
    return im


def draw_end_card(im, t):
    if t < END_CARD:
        return
    p = (t - END_CARD) / 0.5
    c = end_card_img()
    paste_c(im, c, W / 2, 800, scale=ease_out_back(p, 1.8), alpha=clamp(p * 2))
    fy = math.sin((t - END_CARD) * 6) * 14
    paste_c(im, emoji("👇", 120), W / 2, 1010 + fy, scale=ease_out_back((t - END_CARD - 0.35) / 0.4, 2.5))
    paste_c(im, emoji("❤️", 80), W / 2 - 330, 615 + fy * 0.5, scale=ease_out_back((t - END_CARD - 0.5) / 0.4))
    paste_c(im, emoji("🔥", 80), W / 2 + 330, 615 - fy * 0.5, scale=ease_out_back((t - END_CARD - 0.6) / 0.4))


# ----------------------------------------------------------------- frame
def render_frame(t):
    im = draw_background(t)
    draw_header(im, t)
    draw_props(im, t)
    draw_gag(im, t, 0)
    draw_confetti(im, t, CONFETTI_T)
    draw_characters(im, t)
    draw_stamp(im, t)
    draw_bubble(im, t)
    draw_counter(im, t)
    draw_end_card(im, t)
    # вспышка при смене сцены
    for sid in SCENE_IDS[1:]:
        ts = SCENE_START[sid]
        if ts - 0.05 <= t < ts + 0.3:
            a = int(110 * (1 - clamp((t - ts + 0.05) / 0.35)))
            im.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, a)))
    if t >= CONFETTI_T and t < CONFETTI_T + 0.3:
        a = int(150 * (1 - (t - CONFETTI_T) / 0.3))
        im.alpha_composite(Image.new("RGBA", (W, H), (255, 240, 180, a)))
    out = im.convert("RGB")
    # тряска камеры на «Стоп!»
    if STOP_T <= t < STOP_T + 0.45:
        k = 1 - (t - STOP_T) / 0.45
        dx = int(math.sin(t * 90) * 22 * k)
        dy = int(math.cos(t * 77) * 16 * k)
        arr = np.roll(np.asarray(out), (dy, dx), axis=(0, 1))
        out = Image.fromarray(arr)
    # «зум-панч» камеры на ключевых моментах
    zoom = 1.0
    for at in [CONFETTI_T] + [m[0] + 0.55 for m in MONEY]:
        p = (t - at) / 0.35
        if 0 <= p <= 1:
            zoom = max(zoom, 1 + 0.035 * math.sin(p * math.pi))
    if zoom > 1.0005:
        zw, zh = int(W / zoom), int(H / zoom)
        out = out.crop(((W - zw) // 2, (H - zh) // 2, (W - zw) // 2 + zw, (H - zh) // 2 + zh)).resize((W, H),
                                                                                                       Image.BILINEAR)
    return out


# ----------------------------------------------------------------- audio
def synth_audio():
    n = int(TOTAL * SR) + SR
    tt = np.arange(n) / SR
    voice = np.zeros(n, np.float32)
    for ln in TL:
        s = int(ln["start"] * SR)
        voice[s:s + len(ln["audio"])] += ln["audio"] * 0.95

    # ---- музыка: лёгкий поп-бит 108 BPM, Am F C G
    bpm = 108
    beat = 60 / bpm
    music = np.zeros(n, np.float32)
    rng = np.random.default_rng(3)

    def add(sig, at, buf=music, gain=1.0):
        s = int(at * SR)
        if s >= n:
            return
        e = min(n, s + len(sig))
        buf[s:e] += sig[:e - s] * gain

    def tone(freq, dur, kind="sine", decay=6.0, attack=0.005):
        t_ = np.arange(int(dur * SR)) / SR
        if kind == "sine":
            w = np.sin(2 * np.pi * freq * t_)
        elif kind == "pluck":
            w = (np.sin(2 * np.pi * freq * t_) + 0.35 * np.sin(4 * np.pi * freq * t_) +
                 0.12 * np.sin(6 * np.pi * freq * t_))
        elif kind == "bass":
            w = np.sin(2 * np.pi * freq * t_) + 0.25 * np.sin(6 * np.pi * freq * t_)
        elif kind == "pad":
            w = sum(np.sin(2 * np.pi * freq * (1 + dt) * t_ + ph) for dt, ph in ((0, 0), (0.004, 1), (-0.004, 2)))
            w = w / 3
        elif kind == "brass":
            w = sum(np.sin(2 * np.pi * freq * h * t_) / h ** 1.2 for h in range(1, 8))
        env = np.minimum(1, t_ / attack) * np.exp(-decay * t_)
        return (w * env).astype(np.float32)

    def note(m):
        return 440 * 2 ** ((m - 69) / 12)

    prog = [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [55, 60, 64]), (55, [55, 59, 62])]
    kick_t = np.arange(int(0.3 * SR)) / SR
    kick = (np.sin(2 * np.pi * (45 * kick_t + 60 * (1 - np.exp(-kick_t * 25)) / 25 * 1.0) * 1) *
            np.exp(-kick_t * 9)).astype(np.float32)
    kick = np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-kick_t * 30)) / SR).astype(np.float32) * np.exp(
        -kick_t * 8).astype(np.float32)
    clap = (rng.standard_normal(int(0.18 * SR)) * np.exp(-np.arange(int(0.18 * SR)) / SR * 22)).astype(np.float32)
    clap = np.diff(clap, prepend=0).astype(np.float32) * 0.7
    hat = rng.standard_normal(int(0.05 * SR)).astype(np.float32)
    hat = np.diff(np.diff(hat, prepend=0), prepend=0) * np.exp(-np.arange(len(hat)) / SR * 90).astype(np.float32)
    hat = hat.astype(np.float32) * 0.18

    pump = np.ones(n, np.float32)
    bar = 4 * beat
    nbars = int(TOTAL / bar) + 2
    intro_end = TL[2]["start"] + 1.2  # бит «включается» на «Поехали!»
    for b in range(nbars):
        t0 = b * bar
        root, ch = prog[b % 4]
        full = t0 >= intro_end - 0.01
        # pad всегда
        for m in ch:
            add(tone(note(m + 12), bar + 0.3, "pad", decay=0.6, attack=0.25), t0, gain=0.05)
        for k in range(4):
            tb = t0 + k * beat
            if full:
                add(kick, tb, gain=0.55)
                s = int(tb * SR)
                L = int(0.25 * SR)
                if s < n:
                    e = min(n, s + L)
                    pump[s:e] = np.minimum(pump[s:e], 0.55 + 0.45 * (np.arange(e - s) / L))
                if k in (1, 3):
                    add(clap, tb, gain=0.35)
                add(hat, tb + beat / 2)
                add(tone(note(root - 12), beat * 0.45, "bass", decay=5), tb, gain=0.22)
                add(tone(note(root - 12), beat * 0.4, "bass", decay=6), tb + beat / 2, gain=0.16)
            # арпеджио 8-ми
            for j in range(2):
                m = ch[(k * 2 + j) % 3] + 12 + (12 if (k * 2 + j) % 4 == 3 else 0)
                add(tone(note(m), 0.35, "pluck", decay=9), tb + j * beat / 2, gain=0.07 if full else 0.05)

    # ---- эффекты
    sfx = np.zeros(n, np.float32)

    def whoosh(at, dur=0.55, gain=0.35):
        L = int(dur * SR)
        x = rng.standard_normal(L).astype(np.float32)
        y = np.zeros(L, np.float32)
        acc = 0.0
        cut = np.concatenate([np.linspace(0.02, 0.35, L // 2), np.linspace(0.35, 0.03, L - L // 2)])
        for i in range(L):
            acc += cut[i] * (x[i] - acc)
            y[i] = acc
        env = np.sin(np.linspace(0, np.pi, L)) ** 2
        add(y * env, at - dur / 2, sfx, gain)

    def coin(at, gain=0.16):
        add(tone(1975, 0.08, decay=20), at, sfx, gain)
        add(tone(2637, 0.35, decay=10), at + 0.07, sfx, gain)

    def pop(at, gain=0.18):
        L = int(0.09 * SR)
        t_ = np.arange(L) / SR
        f = 380 + 900 * t_ / 0.09
        add((np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t_ * 35)).astype(np.float32), at, sfx, gain)

    def thump(at, gain=0.7):
        L = int(0.45 * SR)
        t_ = np.arange(L) / SR
        y = np.sin(2 * np.pi * np.cumsum(40 + 120 * np.exp(-t_ * 18)) / SR) * np.exp(-t_ * 7)
        y[:300] += rng.standard_normal(300) * np.linspace(1, 0, 300) * 0.6
        add(y.astype(np.float32), at, sfx, gain)

    def scratch(at, gain=0.25):
        L = int(0.42 * SR)
        t_ = np.arange(L) / SR
        f = 300 + 900 * np.abs(np.sin(t_ / 0.42 * np.pi * 2.5))
        ph = np.cumsum(f) / SR
        y = (2 * (ph % 1) - 1) * 0.6 + rng.standard_normal(L) * 0.25
        add((y * np.sin(t_ / 0.42 * np.pi)).astype(np.float32), at, sfx, gain)

    def fanfare(at, gain=0.22):
        for k, m in enumerate([72, 76, 79]):
            add(tone(note(m), 0.25, "brass", decay=5, attack=0.01), at + k * 0.11, sfx, gain)
        for m in (72, 76, 79, 84):
            add(tone(note(m), 1.6, "brass", decay=1.6, attack=0.02), at + 0.33, sfx, gain * 0.6)

    def sparkle(at, dur, gain=0.06):
        r = random.Random(5)
        x = at
        while x < at + dur:
            add(tone(r.uniform(2500, 4200), 0.25, decay=14), x, sfx, gain)
            x += r.uniform(0.07, 0.16)

    for sid in SCENE_IDS[1:]:
        whoosh(SCENE_START[sid] + 0.1)
    for at, k, arg, ln in EVENTS:
        if k == "props":
            for j in range(len(arg)):
                pop(at + j * 0.14 + 0.05)
        elif k == "tags":
            for j in range(len(arg)):
                pop(at + 0.35 + j * 0.45, 0.14)
                coin(at + 0.4 + j * 0.45, 0.07)
        elif k == "money":
            for j in range(10):
                coin(at + j * 0.055 + 0.6, 0.06)
            coin(at + 0.62, 0.2)
        elif k == "jump":
            pop(at + 0.02, 0.1)
    sparkle(SNEAKER_T + 0.1, STOP_T - SNEAKER_T - 0.15)
    scratch(STOP_T - 0.12)
    thump(STOP_T + 0.02)
    fanfare(CONFETTI_T)
    whoosh(CONFETTI_T, 0.4, 0.25)
    whoosh(END_CARD + 0.1, 0.5, 0.25)
    coin(END_CARD + 0.4, 0.15)
    # падение Макса в начале
    thump(0.42, 0.35)

    # ---- огибающая музыки: стоп-эффект, финал, дакинг под голос
    gain = np.ones(n, np.float32) * 0.8
    s0, s1 = int((STOP_T - 0.1) * SR), int((STOP_T + 1.3) * SR)
    gain[s0:s1] = 0.0
    fade = int(0.5 * SR)
    gain[s1:s1 + fade] *= np.linspace(0, 1, fade)
    f0 = int(CONFETTI_T * SR)
    gain[f0:] *= 1.15
    gain[int((TOTAL - 1.5) * SR):] *= np.linspace(1, 0, n - int((TOTAL - 1.5) * SR))
    env = np.abs(voice)
    k = int(0.02 * SR)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    # медленное отпускание
    rel = np.exp(-1 / (0.25 * SR))
    sm = np.zeros_like(env)
    acc = 0.0
    step = 64
    for i in range(0, n, step):
        v = env[i]
        acc = v if v > acc else acc * rel ** step
        sm[i:i + step] = acc
    duck = 1 - 0.6 * np.clip(sm / 0.08, 0, 1)
    mix = voice + music * pump * gain * duck * 0.72 + sfx
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    mix = mix / (np.max(np.abs(mix)) + 1e-9) * 0.93
    mix = mix[:int(TOTAL * SR)]
    pcm = (mix * 32767).astype(np.int16)
    path = os.path.join(BUILD, "mix.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


# ----------------------------------------------------------------- video
def render_chunk(args):
    k, f0, f1 = args
    path = os.path.join(BUILD, f"part_{k}.mp4")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                          "-crf", "18", "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        p.stdin.write(render_frame(fi / FPS).tobytes())
    p.stdin.close()
    p.wait()
    return path


def main():
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    if "--preview" in sys.argv:
        ts = [float(x) for x in sys.argv[sys.argv.index("--preview") + 1].split(",")]
        pd = os.path.join(BUILD, "preview")
        os.makedirs(pd, exist_ok=True)
        for t in ts:
            render_frame(t).save(os.path.join(pd, f"f_{t:06.2f}.png"))
        print("timeline:", {s: round(v, 2) for s, v in SCENE_START.items()}, "end", round(END_CARD, 2),
              "total", round(TOTAL, 2))
        return
    nf = int(TOTAL * FPS)
    print(f"duration {TOTAL:.1f}s, {nf} frames")
    audio = synth_audio()
    workers = os.cpu_count() or 2
    per = math.ceil(nf / (workers * 3))
    chunks = [(k, s, min(nf, s + per)) for k, s in enumerate(range(0, nf, per))]
    with Pool(workers) as pool:
        parts = pool.map(render_chunk, chunks)
    lst = os.path.join(BUILD, "parts.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")
    out = os.path.join(OUT, "first_1000.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest",
                    "-movflags", "+faststart", out], check=True)
    for p in parts:
        os.remove(p)
    print("saved", out)


if __name__ == "__main__":
    main()

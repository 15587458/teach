"""Процедурные персонажи Макс и Лиза. Рисуются в 2x и сглаживаются уменьшением."""
import math
from functools import lru_cache

from PIL import Image, ImageDraw

SW, SH = 440, 720          # размер спрайта (1x)
FEET = 705                 # линия ступней в спрайте
SS = 3                     # суперсэмплинг

CHARS = {
    "max": dict(skin=(255, 213, 170), skin2=(236, 180, 140), hair=(74, 46, 30),
                top=(30, 190, 180), top2=(20, 150, 145), pants=(45, 58, 100),
                shoe=(250, 250, 250), shoe2=(230, 60, 70), glasses=False),
    "liza": dict(skin=(247, 203, 168), skin2=(228, 168, 132), hair=(46, 26, 34),
                 top=(255, 107, 107), top2=(220, 75, 85), pants=(70, 64, 130),
                 shoe=(255, 200, 60), shoe2=(240, 150, 20), glasses=True),
}

OUTLINE = (40, 30, 45)


@lru_cache(maxsize=8)
def _font(size):
    import os
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(os.path.dirname(__file__), "assets", "fonts", "Rubik-900.ttf"), size)


def _s(v):
    return [int(round(x * SS)) for x in v]


class Pen:
    def __init__(self, d):
        self.d = d

    def ell(self, box, fill, ow=5):
        self.d.ellipse(_s(box), fill=fill, outline=OUTLINE if ow else None, width=ow * SS)

    def rr(self, box, r, fill, ow=5):
        self.d.rounded_rectangle(_s(box), radius=r * SS, fill=fill,
                                 outline=OUTLINE if ow else None, width=ow * SS)

    def line(self, pts, fill, w):
        p = [tuple(_s(q)) for q in pts]
        self.d.line(p, fill=fill, width=int(w * SS), joint="curve")
        r = w * SS / 2
        for x, y in (p[0], p[-1]):
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def limb(self, pts, fill, w):
        self.line(pts, OUTLINE, w + 10)
        self.line(pts, fill, w)

    def arc(self, box, a0, a1, fill, w):
        self.d.arc(_s(box), a0, a1, fill=fill, width=int(w * SS))

    def poly(self, pts, fill, ow=5):
        self.d.polygon([tuple(_s(q)) for q in pts], fill=fill)
        if ow:
            self.d.line([tuple(_s(q)) for q in pts + [pts[0]]], fill=OUTLINE, width=ow * SS, joint="curve")

    def pie(self, box, a0, a1, fill):
        self.d.pieslice(_s(box), a0, a1, fill=fill)

    def chord(self, box, a0, a1, fill):
        self.d.chord(_s(box), a0, a1, fill=fill)


# Позы рук: (плечо -> локоть -> кисть) для левой и правой руки (с точки зрения зрителя)
def _arms(pose):
    L0, R0 = (138, 445), (302, 445)
    poses = {
        "idle": ([L0, (112, 520), (118, 595)], [R0, (328, 520), (322, 595)]),
        "wave": ([L0, (112, 520), (118, 595)], [R0, (370, 410), (385, 320)]),
        "cheer": ([L0, (85, 380), (70, 290)], [R0, (355, 380), (370, 290)]),
        "point": ([L0, (112, 520), (118, 595)], [R0, (372, 470), (420, 430)]),
        "stop": ([L0, (112, 520), (118, 595)], [R0, (380, 430), (410, 360)]),
        "think": ([L0, (112, 520), (118, 595)], [R0, (330, 520), (268, 400)]),
        "shrug": ([L0, (75, 470), (50, 400)], [R0, (365, 470), (390, 400)]),
    }
    return poses.get(pose, poses["idle"])


@lru_cache(maxsize=4096)
def sprite(name, emo="normal", pose="idle", mouth=0, blink=False, look=0, flip=False):
    c = CHARS[name]
    img = Image.new("RGBA", (SW * SS, SH * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = Pen(d)
    cx = SW / 2

    # --- волосы сзади (Лиза) ---
    if name == "liza":
        p.rr((86, 190, 354, 520), 110, c["hair"])

    # --- ноги и обувь ---
    for x in (178, 262):
        p.rr((x - 26, 600, x + 26, FEET - 22), 20, c["pants"])
        p.ell((x - 42, FEET - 46, x + 46, FEET), c["shoe"])
        p.arc((x - 34, FEET - 40, x + 38, FEET - 8), 200, 340, c["shoe2"], 7)

    larm, rarm = _arms(pose)
    # --- рука сзади (левая) ---
    p.limb(larm, c["top"], 38)
    p.ell((larm[-1][0] - 22, larm[-1][1] - 22, larm[-1][0] + 22, larm[-1][1] + 22), c["skin"])

    # --- туловище ---
    p.rr((118, 405, 322, 632), 70, c["top"])
    p.chord((118 + 6, 540, 322 - 6, 640), 0, 180, c["top2"])
    if name == "max":
        # капюшон-воротник и шнурки
        p.arc((160, 380, 280, 470), 20, 160, c["top2"], 12)
        p.line([(200, 450), (196, 510)], (245, 245, 245), 6)
        p.line([(240, 450), (244, 510)], (245, 245, 245), 6)
        # логотип $
        p.ell((192, 520, 248, 576), (255, 215, 64), 4)
        d.text(_s((220, 549)), "$", fill=OUTLINE, font=_font(40 * SS), anchor="mm")
    else:
        p.chord((170, 395, 270, 460), 0, 180, c["skin"])
        p.arc((170, 395, 270, 460), 0, 180, OUTLINE, 5)
        p.ell((212, 470, 228, 486), (255, 230, 120), 3)  # кулон

    # --- рука спереди (правая) ---
    p.limb(rarm, c["top"], 38)
    hx, hy = rarm[-1]
    hr = 30 if pose == "stop" else 22
    p.ell((hx - hr, hy - hr, hx + hr, hy + hr), c["skin"])
    if pose == "point":
        p.limb([(hx, hy), (hx + 28, hy - 14)], c["skin"], 12)

    # --- голова ---
    hcx, hcy, R = cx, 285, 132
    p.ell((hcx - R - 14, hcy - 20, hcx - R + 18, hcy + 28), c["skin"])   # уши
    p.ell((hcx + R - 18, hcy - 20, hcx + R + 14, hcy + 28), c["skin"])
    p.ell((hcx - R, hcy - R, hcx + R, hcy + R), c["skin"])

    # --- волосы спереди ---
    if name == "max":
        top = [(hcx - R - 4, hcy - 20), (hcx - R + 10, hcy - 95), (hcx - 70, hcy - 150),
               (hcx - 40, hcy - 128), (hcx - 10, hcy - 168), (hcx + 20, hcy - 135),
               (hcx + 60, hcy - 165), (hcx + 80, hcy - 120), (hcx + R + 6, hcy - 90),
               (hcx + R + 4, hcy - 15), (hcx + 95, hcy - 55), (hcx + 40, hcy - 75),
               (hcx - 20, hcy - 62), (hcx - 80, hcy - 70)]
        p.poly(top, c["hair"])
    else:
        hb = (hcx - R - 6, hcy - R - 8, hcx + R + 6, hcy + R - 64)
        p.chord(hb, 180, 360, c["hair"])
        p.rr((hcx - R - 8, hcy - 60, hcx - R + 26, hcy + 40), 16, c["hair"], 0)
        p.rr((hcx + R - 26, hcy - 60, hcx + R + 8, hcy + 40), 16, c["hair"], 0)
        p.ell((hcx - 52, hcy - R - 80, hcx + 52, hcy - R + 20), c["hair"])   # пучок
        p.arc(hb, 180, 360, OUTLINE, 5)
        p.ell((hcx - 30, hcy - R - 4, hcx + 30, hcy - R + 16), (255, 107, 107), 3)  # резинка

    # --- лицо ---
    ey = hcy + 10
    exs = (hcx - 48, hcx + 48)
    lx = look * 9
    # румянец
    for ex in exs:
        bx = ex + (-18 if ex < hcx else 18)
        bl = tuple(int(a * 0.45 + b * 0.55) for a, b in zip(c["skin"], (255, 120, 130)))
        d.ellipse(_s((bx - 22, ey + 38, bx + 22, ey + 58)), fill=bl)

    if blink or emo == "happy":
        for ex in exs:
            if emo == "happy":
                p.arc((ex - 22, ey - 12, ex + 22, ey + 22), 200, 340, OUTLINE, 7)
            else:
                p.arc((ex - 22, ey - 18, ex + 22, ey + 10), 20, 160, OUTLINE, 7)
    else:
        big = 1.25 if emo == "shock" else 1.0
        for ex in exs:
            w, h = 24 * big, 29 * big
            p.ell((ex - w, ey - h, ex + w, ey + h), (255, 255, 255), 5)
            pr = 10 if emo == "shock" else 15
            px, py = ex + lx, ey + 3
            if emo == "smirk":
                d.chord(_s((ex - w + 2, ey - h, ex + w - 2, ey + h)), 180, 360, fill=c["skin"])
                p.line([(ex - w, ey - 2), (ex + w, ey - 2)], OUTLINE, 5)
                py = ey + 10
            d.ellipse(_s((px - pr, py - pr, px + pr, py + pr)), fill=OUTLINE)
            d.ellipse(_s((px - pr * 0.2 + 3, py - pr * 0.7, px + pr * 0.4 + 3, py - pr * 0.1)),
                      fill=(255, 255, 255))

    # брови
    brow = {"normal": (0, 0), "happy": (-6, 0), "shock": (-18, 0), "angry": (4, 14),
            "sad": (-4, -12), "think": (-10, 8), "smirk": (-4, 6)}[emo if emo in
           ("normal", "happy", "shock", "angry", "sad", "think", "smirk") else "normal"]
    by = ey - 48 + brow[0] + (9 if name == "liza" else 0)
    for i, ex in enumerate(exs):
        tilt = brow[1] * (1 if i == 0 else -1)
        if emo == "think" and i == 0:
            tilt = -tilt
        p.line([(ex - 22, by - tilt / 2), (ex + 22, by + tilt / 2)], c["hair"] if name == "max" else OUTLINE, 9)

    if c["glasses"] and not (blink or emo == "happy"):
        for ex in exs:
            p.arc((ex - 36, ey - 36, ex + 36, ey + 36), 0, 360, (90, 40, 120), 6)
        p.arc((hcx - 14, ey - 16, hcx + 14, ey + 4), 200, 340, (90, 40, 120), 6)

    # нос
    p.arc((hcx - 10, ey + 22, hcx + 10, ey + 40), 0, 180, c["skin2"], 6)

    # рот
    my = hcy + 78
    m = mouth / 5.0
    if emo == "shock" and m < 0.3:
        m = 0.5
    if m <= 0.05:
        if emo in ("sad",):
            p.arc((hcx - 26, my, hcx + 26, my + 30), 200, 340, OUTLINE, 7)
        elif emo == "smirk":
            p.arc((hcx - 20, my - 26, hcx + 40, my + 10), 30, 130, OUTLINE, 7)
        elif emo == "angry":
            p.line([(hcx - 22, my + 4), (hcx + 22, my + 4)], OUTLINE, 7)
        else:
            p.arc((hcx - 30, my - 24, hcx + 30, my + 14), 20, 160, OUTLINE, 7)
    else:
        mw = 26 + 8 * m if emo != "shock" else 18 + 6 * m
        mh = 8 + 30 * m
        top_y = my - 4
        if emo in ("happy", "smirk", "normal", "think") and emo != "shock":
            # улыбчивый открытый рот: плоский верх, круглый низ
            p.chord((hcx - mw, top_y - mh * 0.6, hcx + mw, top_y + mh * 1.2), 0, 180, (120, 30, 45))
            d.chord(_s((hcx - mw * 0.6, top_y + mh * 0.45, hcx + mw * 0.6, top_y + mh * 1.15)), 0, 180,
                    fill=(240, 110, 120))
            p.arc((hcx - mw, top_y - mh * 0.6, hcx + mw, top_y + mh * 1.2), 0, 180, OUTLINE, 6)
            p.line([(hcx - mw, top_y + mh * 0.3), (hcx + mw, top_y + mh * 0.3)], OUTLINE, 6)
        else:
            p.ell((hcx - mw, top_y, hcx + mw, top_y + mh + 6), (120, 30, 45), 6)
            d.ellipse(_s((hcx - mw * 0.5, top_y + mh * 0.5, hcx + mw * 0.5, top_y + mh + 2)),
                      fill=(240, 110, 120))

    out = img.resize((SW, SH), Image.LANCZOS)
    if flip:
        out = out.transpose(Image.FLIP_LEFT_RIGHT)
    return out


if __name__ == "__main__":
    import sys
    sheet = Image.new("RGBA", (SW * 5, SH * 2), (120, 160, 230, 255))
    combos = [("normal", "idle", 0), ("happy", "cheer", 3), ("shock", "shrug", 2),
              ("smirk", "point", 0), ("angry", "stop", 4)]
    for j, n in enumerate(("max", "liza")):
        for i, (e, po, mo) in enumerate(combos):
            s = sprite(n, e, po, mo, False, 1 if n == "max" else -1, flip=(n == "liza"))
            sheet.alpha_composite(s, (i * SW, j * SH))
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "sheet.png")

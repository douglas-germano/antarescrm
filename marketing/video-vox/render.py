"""Renderiza o vídeo estilo Vox do Antares CRM.

Uso: python3 render.py [--preview SEGUNDOS] [--only N]
Gera frames com Pillow, envia ao ffmpeg e mixa narração, trilha e efeitos (Epidemic Sound).
Se existir images/cenaNN.png (ex.: gerada no ChatGPT), ela vira o fundo da cena.
"""
import argparse
import json
import math
import random
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
AUDIO = ROOT / "audio"
IMAGES = ROOT / "images"
OUT = ROOT / "out"
W, H, FPS = 1920, 1080, 30

CREAM = (243, 235, 221)
INK = (24, 22, 20)
YELLOW = (255, 212, 0)
GREEN = (37, 211, 102)
RED = (226, 61, 45)
NAVY = (14, 22, 48)
GRAY = (170, 162, 150)
BLUE = (52, 183, 241)

AVENIR_C = "/System/Library/Fonts/Avenir Next Condensed.ttc"
AVENIR = "/System/Library/Fonts/Avenir Next.ttc"
GEORGIA = "/System/Library/Fonts/Supplemental/Georgia.ttf"
GEORGIA_I = "/System/Library/Fonts/Supplemental/Georgia Italic.ttf"


@lru_cache(None)
def font(kind, size):
    if kind == "head":
        return ImageFont.truetype(AVENIR_C, size, index=8)
    if kind == "bold":
        return ImageFont.truetype(AVENIR, size, index=0)
    if kind == "med":
        return ImageFont.truetype(AVENIR, size, index=5)
    if kind == "serif":
        return ImageFont.truetype(GEORGIA, size)
    if kind == "serif_i":
        return ImageFont.truetype(GEORGIA_I, size)
    raise ValueError(kind)


# ---------- tempo e easing ----------

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(t, start, dur):
    return clamp((t - start) / dur) if dur > 0 else float(t >= start)


def ease(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def back(x):
    x = clamp(x)
    c1, c3 = 1.9, 2.9
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a, b, x):
    return a + (b - a) * x


# ---------- textura e sprites ----------

def make_paper():
    rng = np.random.default_rng(7)
    base = np.ones((H, W, 3), np.float32) * np.array(CREAM, np.float32)
    noise = rng.normal(0, 1, (H // 4, W // 4)).astype(np.float32)
    noise = np.array(Image.fromarray(((noise + 3) * 40).clip(0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32)
    base += (noise[..., None] - 120) * 0.06
    fine = rng.normal(0, 4, (H, W, 1)).astype(np.float32)
    base += fine
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    base *= (1 - 0.18 * clamp_arr(d - 0.55))[..., None]
    return Image.fromarray(base.clip(0, 255).astype(np.uint8))


def clamp_arr(a):
    return np.clip(a, 0, 1)


def make_grain(seed):
    rng = np.random.default_rng(seed)
    g = rng.normal(128, 10, (H // 2, W // 2)).clip(0, 255).astype(np.uint8)
    return Image.fromarray(g).resize((W, H), Image.NEAREST).convert("L")


PAPER = None
GRAINS = []


def shadowed(sprite, offset=(10, 14), blur=14, alpha=90):
    w, h = sprite.size
    pad = blur * 3
    out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    mask = sprite.split()[3].point(lambda v: alpha if v > 0 else 0)
    sh = Image.new("RGBA", sprite.size, (40, 30, 20, 0))
    sh.putalpha(mask)
    out.alpha_composite(sh, (pad + offset[0], pad + offset[1]))
    out = out.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(sprite, (pad, pad))
    return out


def paste(img, sprite, cx, cy, scale=1.0, rot=0.0, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    s = sprite
    if abs(scale - 1) > 0.01:
        s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.BICUBIC)
    if abs(rot) > 0.05:
        s = s.rotate(rot, Image.BICUBIC, expand=True)
    if alpha < 0.99:
        a = s.split()[3].point(lambda v: int(v * alpha))
        s = s.copy()
        s.putalpha(a)
    img.alpha_composite(s, (int(cx - s.width / 2), int(cy - s.height / 2)))


def rounded(w, h, r, fill, outline=None, width=0):
    s = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(s).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=fill, outline=outline, width=width)
    return s


def torn_card(w, h, fill=(252, 248, 240), seed=1):
    """Recorte de papel com borda irregular."""
    rng = random.Random(seed)
    pts = []
    step = 18
    for x in range(0, w, step):
        pts.append((x, rng.uniform(0, 7)))
    for y in range(0, h, step):
        pts.append((w - rng.uniform(0, 7), y))
    for x in range(w, 0, -step):
        pts.append((x, h - rng.uniform(0, 7)))
    for y in range(h, 0, -step):
        pts.append((rng.uniform(0, 7), y))
    s = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(s).polygon(pts, fill=fill)
    return s


@lru_cache(None)
def sprite(name):
    """Sprites desenhados uma vez e reaproveitados."""
    if name == "phone":
        s = rounded(420, 820, 60, INK)
        d = ImageDraw.Draw(s)
        d.rounded_rectangle((22, 22, 398, 798), 44, fill=(236, 229, 221))
        d.rounded_rectangle((150, 36, 270, 64), 14, fill=INK)
        d.rectangle((22, 80, 398, 170), fill=(18, 140, 126))
        d.ellipse((44, 98, 104, 158), fill=(220, 220, 220))
        d.text((120, 104), "Cliente novo", font=font("bold", 30), fill="white")
        d.text((120, 140), "online", font=font("med", 22), fill=(200, 240, 230))
        return shadowed(s)
    if name == "bubble_in":
        s = rounded(330, 120, 22, "white")
        d = ImageDraw.Draw(s)
        d.text((24, 22), "Oi, quanto custa?", font=font("med", 32), fill=INK)
        d.text((240, 78), "14:02", font=font("med", 22), fill=GRAY)
        return s
    if name == "bubble_out":
        s = rounded(330, 120, 22, (217, 253, 211))
        d = ImageDraw.Draw(s)
        d.text((24, 22), "Oi! Te explico já 🙂".replace("🙂", ""), font=font("med", 32), fill=INK)
        d.text((196, 78), "14:03", font=font("med", 22), fill=GRAY)
        for dx in (0, 12):
            d.line([(272 + dx, 92), (280 + dx, 100), (294 + dx, 82)], fill=BLUE, width=4)
        return s
    if name.startswith("store"):
        state = name.split(":")[1]
        body = {"off": (215, 207, 194), "green": GREEN, "folder": GREEN, "gray": (200, 192, 180)}[state]
        s = Image.new("RGBA", (150, 170), (0, 0, 0, 0))
        d = ImageDraw.Draw(s)
        d.rectangle((14, 60, 136, 160), fill=body, outline=INK, width=4)
        for i in range(5):
            c = INK if i % 2 == 0 else (250, 246, 238)
            d.polygon([(10 + i * 26, 30), (36 + i * 26, 30), (36 + i * 26, 64), (10 + i * 26, 64)], fill=c)
        d.rectangle((10, 30, 140, 64), outline=INK, width=4)
        d.rectangle((58, 100, 92, 160), fill=(250, 246, 238), outline=INK, width=4)
        if state == "folder":
            d.rounded_rectangle((92, 0, 148, 44), 6, fill=YELLOW, outline=INK, width=4)
            d.rectangle((92, 0, 116, 10), fill=YELLOW, outline=INK, width=4)
        return shadowed(s, (5, 7), 6, 70)
    if name == "bubble_green":
        s = rounded(120, 70, 20, GREEN)
        ImageDraw.Draw(s).text((26, 4), "...", font=font("head", 44), fill="white")
        return s
    if name == "bucket":
        s = Image.new("RGBA", (460, 420), (0, 0, 0, 0))
        d = ImageDraw.Draw(s)
        d.polygon([(20, 40), (440, 40), (380, 410), (80, 410)], fill=(150, 150, 156), outline=INK)
        for i in range(6):
            d.line([(60 + i * 68, 60), (110 + i * 50, 400)], fill=(130, 130, 136), width=6)
        d.ellipse((20, 14, 440, 66), fill=(110, 110, 116), outline=INK, width=5)
        for (x, y) in [(150, 300), (240, 330), (320, 290), (200, 220), (290, 200)]:
            d.ellipse((x - 18, y - 18, x + 18, y + 18), fill=INK)
        return shadowed(s)
    if name == "hbr":
        s = torn_card(760, 430, seed=5)
        d = ImageDraw.Draw(s)
        d.text((48, 40), "Harvard Business Review", font=font("serif_i", 40), fill=(150, 20, 30))
        d.line((48, 100, 712, 100), fill=INK, width=3)
        d.text((48, 120), "The Short Life of", font=font("serif", 62), fill=INK)
        d.text((48, 192), "Online Sales Leads", font=font("serif", 62), fill=INK)
        d.text((48, 300), "Oldroyd, McElheran e Elkington · março de 2011", font=font("serif_i", 28), fill=(90, 84, 76))
        d.text((48, 346), "Teste com 2.241 empresas dos EUA", font=font("serif", 28), fill=(90, 84, 76))
        return shadowed(s)
    if name == "post_it":
        s = Image.new("RGBA", (300, 300), (255, 226, 80, 255))
        d = ImageDraw.Draw(s)
        d.text((26, 60), "ligar pro", font=font("serif_i", 46), fill=(40, 40, 120))
        d.text((26, 120), "cliente", font=font("serif_i", 46), fill=(40, 40, 120))
        d.text((26, 180), "amanhã!!", font=font("serif_i", 46), fill=(40, 40, 120))
        return shadowed(s)
    if name == "envelope":
        s = torn_card(380, 250, (250, 250, 250), seed=9)
        d = ImageDraw.Draw(s)
        d.line([(10, 10), (190, 140), (370, 10)], fill=INK, width=6)
        d.rectangle((40, 170, 340, 220), fill=(232, 236, 245))
        d.text((54, 176), "Proposta_v3_FINAL.pdf", font=font("med", 28), fill=INK)
        return shadowed(s)
    if name == "insta":
        s = rounded(300, 300, 70, (225, 48, 108))
        d = ImageDraw.Draw(s)
        d.rounded_rectangle((60, 60, 240, 240), 50, outline="white", width=18)
        d.ellipse((105, 105, 195, 195), outline="white", width=18)
        d.ellipse((190, 80, 214, 104), fill="white")
        return shadowed(s)
    if name == "mini_phone":
        s = rounded(220, 400, 34, INK)
        d = ImageDraw.Draw(s)
        d.rounded_rectangle((14, 14, 206, 386), 24, fill=(236, 229, 221))
        for i, w in enumerate([150, 120, 160, 100]):
            x = 30 if i % 2 == 0 else 190 - w
            d.rounded_rectangle((x, 60 + i * 76, x + w, 110 + i * 76), 14, fill="white" if i % 2 == 0 else (217, 253, 211))
        return shadowed(s)
    if name == "star":
        s = Image.new("RGBA", (360, 360), (0, 0, 0, 0))
        d = ImageDraw.Draw(s)
        pts = []
        for i in range(16):
            r = 170 if i % 2 == 0 else 46
            a = math.pi / 8 * i - math.pi / 2
            pts.append((180 + r * math.cos(a), 180 + r * math.sin(a)))
        d.polygon(pts, fill=YELLOW)
        return s
    raise KeyError(name)


# ---------- primitivas de desenho ----------

def text(img, xy, s, f, fill=INK, anchor="la", alpha=1.0):
    if alpha <= 0.01:
        return
    if alpha >= 0.99:
        ImageDraw.Draw(img).text(xy, s, font=f, fill=fill, anchor=anchor)
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, s, font=f, fill=fill + (int(255 * alpha),), anchor=anchor)
    img.alpha_composite(layer)


def marker(img, box, p, color=YELLOW):
    """Marca-texto animado da esquerda para a direita."""
    if p <= 0:
        return
    x0, y0, x1, y1 = box
    xe = x0 + (x1 - x0) * ease_out(p)
    ImageDraw.Draw(img).polygon([(x0 - 8, y0 + 6), (xe + 8, y0), (xe + 4, y1), (x0 - 4, y1 + 4)], fill=color)


def headline(img, xy, s, size, t, start, mark=None, color=INK, anchor="la"):
    """Título que sobe com fade; opcionalmente com marca-texto atrás."""
    p = ease_out(prog(t, start, 0.45))
    if p <= 0:
        return
    f = font("head", size)
    x, y = xy
    y = y + (1 - p) * 30
    if mark is not None:
        bb = ImageDraw.Draw(img).textbbox((x, y), s, font=f, anchor=anchor)
        marker(img, (bb[0] - 6, bb[1] - 4, bb[2] + 6, bb[3] + 8), prog(t, mark, 0.5))
    text(img, (x, y), s, f, color, anchor, alpha=p)


def source(img, s, t, start=0.6):
    text(img, (70, H - 70), s, font("serif_i", 28), (90, 84, 76), "ls", alpha=ease(prog(t, start, 0.6)))


def hand_circle(img, cx, cy, rx, ry, p, color=RED, width=9, seed=3):
    if p <= 0:
        return
    rng = random.Random(seed)
    n = int(80 * ease_out(p))
    pts = []
    for i in range(n + 1):
        a = -math.pi / 2 + 2.15 * math.pi * i / 80
        wob = 1 + 0.04 * math.sin(i * 0.7 + rng.random())
        pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a)))
    if len(pts) > 1:
        ImageDraw.Draw(img).line(pts, fill=color, width=width, joint="curve")


def stamp(img, cx, cy, s, t, start, color=RED, rot=-8):
    p = prog(t, start, 0.25)
    if p <= 0:
        return
    f = font("head", 74)
    bb = ImageDraw.Draw(img).textbbox((0, 0), s, font=f)
    w, h = bb[2] - bb[0] + 60, bb[3] - bb[1] + 50
    sp = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(sp)
    d.rectangle((4, 4, w - 5, h - 5), outline=color, width=8)
    d.text((w / 2, h / 2), s, font=f, fill=color, anchor="mm")
    paste(img, sp, cx, cy, scale=lerp(1.8, 1.0, ease_out(p)), rot=rot, alpha=p)


def clock(img, cx, cy, r, hours):
    d = ImageDraw.Draw(img)
    d.ellipse((cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8), fill=INK)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(252, 248, 240))
    for i in range(12):
        a = i * math.pi / 6
        d.line((cx + r * 0.82 * math.cos(a), cy + r * 0.82 * math.sin(a), cx + r * 0.93 * math.cos(a), cy + r * 0.93 * math.sin(a)), fill=INK, width=6)
    am = (hours % 1) * 2 * math.pi - math.pi / 2
    ah = (hours % 12) / 12 * 2 * math.pi - math.pi / 2
    d.line((cx, cy, cx + r * 0.75 * math.cos(am), cy + r * 0.75 * math.sin(am)), fill=INK, width=8)
    d.line((cx, cy, cx + r * 0.5 * math.cos(ah), cy + r * 0.5 * math.sin(ah)), fill=RED, width=12)
    d.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), fill=INK)


# ---------- cenas ----------
# Cada cena recebe (img, t, D): t = segundos desde o início da cena, D = duração.
# VO começa em LEAD segundos (ver TIMELINE).

def scene1(img, t, D):
    v = t - 0.5
    paste(img, sprite("phone"), 640, 560, scale=lerp(0.9, 1.0, ease_out(prog(t, 0, 1))), rot=-4)
    p = back(prog(v, 0.6, 0.4))
    paste(img, sprite("bubble_in"), 600, 380, scale=p, rot=-4)
    hrs = 14.03 + 6 * ease(prog(v, 3.8, D - 4.3))
    clock(img, 1380, 380, 150, hrs)
    hh = int(hrs)
    mm = int((hrs - hh) * 60)
    text(img, (1380, 600), f"{hh:02d}:{mm:02d}", font("head", 96), INK, "mt", alpha=ease(prog(v, 3.8, 0.4)))
    headline(img, (1380, 760), "SEM RESPOSTA", 92, v, 5.0, mark=5.2, anchor="mt")


def store_grid(img, t, states, y0=430):
    for i, st in enumerate(states):
        x = 330 + i * 140
        p = back(prog(t, 0.1 + i * 0.06, 0.4))
        paste(img, sprite("store:" + st), x, y0, scale=0.85 * p)


def scene2(img, t, D):
    v = t - 0.5
    states = ["green" if v > 2.6 + i * 0.22 and i < 8 else "off" for i in range(10)]
    store_grid(img, t, states)
    headline(img, (W / 2, 640), "8 EM CADA 10", 150, v, 2.4, mark=3.0, anchor="mt")
    headline(img, (W / 2, 830), "empresas que vendem online vendem pelo WhatsApp", 56, v, 3.4, anchor="mt")
    source(img, "Fonte: Cetic.br — TIC Empresas 2025 (indicador E2C)", t, 3.5)


def scene3(img, t, D):
    v = t - 0.5
    states = ["folder" if (i in (1, 5, 8) and v > 1.8) else ("gray" if v > 1.0 else "green") for i in range(10)]
    store_grid(img, t, states)
    headline(img, (W / 2, 640), "SÓ 3 EM CADA 10", 150, v, 1.4, mark=2.4, anchor="mt")
    headline(img, (W / 2, 830), "pequenas empresas usam um CRM", 56, v, 2.2, anchor="mt")
    source(img, "Fonte: Cetic.br — TIC Empresas 2025 (indicador G2-3: pequenas empresas, 29%)", t, 2.0)


def scene4(img, t, D):
    v = t - 0.5
    paste(img, sprite("bucket"), 700, 560, scale=ease_out(prog(t, 0, 0.6)))
    rng = random.Random(11)
    for k in range(14):
        t0 = k * 0.28 + rng.random() * 0.2
        lt = t - t0
        if lt < 0:
            continue
        x = 620 + rng.uniform(-120, 160)
        if lt < 0.7:
            y = lerp(60, 470, lt / 0.7)
        else:
            y = 470 + (lt - 0.7) * 520
            x += (lt - 0.7) * rng.uniform(-80, 80)
        if y < H + 60:
            paste(img, sprite("bubble_green"), x, y, rot=rng.uniform(-20, 20))
    headline(img, (1150, 380), "MEMÓRIA", 150, v, 1.3)
    headline(img, (1150, 540), "VAZA.", 150, v, 1.9, mark=2.2)


def scene5(img, t, D):
    v = t - 0.5
    p = ease_out(prog(t, 0, 0.6))
    paste(img, sprite("hbr"), lerp(-400, 560, p), 380, rot=-3)
    # 2.241 empresas
    n = int(2241 * ease(prog(v, 2.0, 1.6)))
    if v > 2.0:
        text(img, (560, 700), f"{n:,}".replace(",", ".") + " empresas", font("head", 84), INK, "mt", alpha=ease(prog(v, 2.0, 0.3)))
    headline(img, (1180, 250), "23%", 220, v, 5.1, mark=5.4)
    headline(img, (1180, 500), "nunca responderam", 64, v, 5.5)
    if v > 7.8:
        hrs = 2 + 40 * ease(prog(v, 7.9, 2.6))
        clock(img, 1300, 760, 120, hrs)
        text(img, (1460, 760), f"{int(hrs)} h", font("head", 130), RED, "lm", alpha=ease(prog(v, 7.9, 0.3)))
        text(img, (1460, 850), "tempo médio de resposta", font("med", 32), INK, "lt", alpha=ease(prog(v, 8.5, 0.4)))
    source(img, "Fonte: Oldroyd, McElheran e Elkington, Harvard Business Review, 2011", t, 1.0)


def scene6(img, t, D):
    v = t - 0.5
    d = ImageDraw.Draw(img)
    base = 860
    d.line((260, base, 1100, base), fill=INK, width=6)
    h5 = 600 * ease_out(prog(v, 1.9, 0.8))
    h30 = 600 / 21 * ease_out(prog(v, 2.6, 0.5))
    d.rectangle((340, base - h5, 560, base), fill=GREEN, outline=INK, width=5)
    d.rectangle((760, base - h30, 980, base), fill=GRAY, outline=INK, width=5)
    text(img, (450, base + 20), "5 min", font("head", 60), INK, "mt")
    text(img, (870, base + 20), "30 min", font("head", 60), INK, "mt")
    headline(img, (1240, 300), "ATÉ", 90, v, 3.0)
    headline(img, (1240, 390), "21×", 260, v, 3.3, color=RED)
    hand_circle(img, 1420, 540, 230, 150, prog(v, 4.0, 0.7))
    headline(img, (1240, 760), "mais chance de qualificar", 52, v, 4.6)
    headline(img, (1240, 830), "o cliente", 52, v, 4.7)
    source(img, "Fonte: Lead Response Management Study (Oldroyd / InsideSales), 2007 — mais de 15 mil leads", t, 2.2)


def scene7(img, t, D):
    v = t - 0.5
    items = [("mini_phone", 420, 400, -10, 1.0), ("envelope", 980, 300, 6, 3.0), ("insta", 1500, 420, 12, 2.2), ("post_it", 1150, 720, -7, 6.3)]
    pts = []
    for i, (nm, x, y, r, st) in enumerate(items):
        p = back(prog(v, st, 0.45))
        if p <= 0:
            continue
        jit = math.sin(t * 7 + i) * 6 * clamp((v - 4) / 2) if nm != "post_it" else 0
        paste(img, sprite(nm), x + jit, y + jit / 2, scale=p, rot=r + jit / 3)
        pts.append((x, y))
    # linhas de lápis ligando tudo
    lp = prog(v, 4.2, 2.0)
    if lp > 0 and len(pts) >= 3:
        d = ImageDraw.Draw(img)
        chain = pts + [pts[0]]
        total = len(chain) - 1
        upto = lp * total
        for k in range(int(math.ceil(upto))):
            a, b = chain[k], chain[k + 1]
            f = clamp(upto - k)
            d.line((a[0], a[1], lerp(a[0], b[0], f), lerp(a[1], b[1], f)), fill=(70, 70, 80), width=5)
    for i, (qx, qy) in enumerate([(700, 200), (1280, 560), (300, 800), (1700, 760)]):
        text(img, (qx, qy), "?", font("head", 140), RED, "mm", alpha=ease(prog(v, 5.0 + i * 0.15, 0.3)))


def scene8(img, t, D):
    # fundo azul-noite entra como cortina, estrela e logo
    p = ease(prog(t, 0, 0.7))
    ImageDraw.Draw(img).rectangle((0, 0, W * p, H), fill=NAVY)
    if t > 0.6:
        rng = random.Random(4)
        d = ImageDraw.Draw(img)
        for _ in range(120):
            x, y = rng.uniform(0, W), rng.uniform(0, H)
            a = 0.4 + 0.6 * abs(math.sin(t * 2 + x))
            c = int(140 * a)
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(c + 80, c + 80, c + 100))
    sp = back(prog(t, 1.0, 0.7))
    paste(img, sprite("star"), W / 2, 420, scale=sp * 1.0, rot=t * 12)
    text(img, (W / 2, 690), "ANTARES CRM", font("head", 150), (255, 255, 255), "mt", alpha=ease(prog(t, 1.6, 0.5)))


def channel_chip(label, color):
    f = font("head", 46)
    w = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(label, font=f)) + 70
    s = rounded(w, 84, 42, color)
    ImageDraw.Draw(s).text((w / 2, 42), label, font=f, fill="white", anchor="mm")
    return shadowed(s, (5, 7), 8, 70)


CHIPS = None


def scene9(img, t, D):
    global CHIPS
    v = t - 0.5
    d = ImageDraw.Draw(img)
    if CHIPS is None:
        CHIPS = [channel_chip(*c) for c in [("WhatsApp", GREEN), ("Instagram", (225, 48, 108)), ("E-mail", (60, 90, 200)), ("SMS", (120, 120, 130))]]
    if v < 4.7:
        # canais entram numa caixa de entrada única
        box = (1060, 260, 1720, 820)
        d.rounded_rectangle(box, 30, fill=(252, 248, 240), outline=INK, width=6)
        text(img, (1390, 300), "CAIXA DE ENTRADA", font("head", 60), INK, "mt")
        for i, chip in enumerate(CHIPS):
            p = ease(prog(v, 0.3 + i * 0.5, 0.9))
            x = lerp(380, 1390, p)
            y = lerp(250 + i * 180, 420 + i * 95, p)
            paste(img, chip, x, y, scale=lerp(1.1, 0.85, p))
        headline(img, (120, 900), "Tudo numa caixa de entrada só", 64, v, 0.6, mark=1.2)
    elif v < 7.3:
        lv = v - 4.7
        cols = ["Novo", "Conversa", "Proposta", "Ganho"]
        for i, c in enumerate(cols):
            x = 160 + i * 420
            d.rounded_rectangle((x, 200, x + 380, 820), 24, fill=(232, 224, 210), outline=INK, width=4)
            text(img, (x + 190, 230), c.upper(), font("head", 54), INK, "mt")
            for k in range(3 - (i == 3)):
                d.rounded_rectangle((x + 24, 320 + k * 150, x + 356, 440 + k * 150), 16, fill="white", outline=INK, width=3)
                d.rectangle((x + 24, 320 + k * 150, x + 40, 440 + k * 150), fill=GREEN)
        mp = ease(prog(lv, 0.5, 1.2))
        mx = lerp(160 + 24, 160 + 420 * 2 + 24, mp)
        d.rounded_rectangle((mx, 620, mx + 332, 740), 16, fill=(255, 246, 200), outline=INK, width=5)
        text(img, (mx + 30, 650), "Maria · Orçamento", font("bold", 32), INK)
        headline(img, (W / 2, 900), "Cada conversa vira um negócio no funil", 64, lv, 0.1, mark=0.5, anchor="mt")
    elif v < 13.6:
        lv = v - 7.3
        alerts = [("Aguardando resposta há 2 h", "Maria Souza · WhatsApp", 1.4),
                  ("Sem próxima ação", "Clínica Bem Estar · R$ 4.800", 3.0),
                  ("Retorno atrasado", "João Lima · ligar ontem 16h", 4.8)]
        text(img, (W / 2, 140), "PRECISA DE ATENÇÃO HOJE", font("head", 76), INK, "mt", alpha=ease(prog(lv, 0, 0.4)))
        for i, (title, sub, st) in enumerate(alerts):
            p = back(prog(lv, st, 0.4))
            if p <= 0:
                continue
            y = 330 + i * 200
            card = torn_card(1200, 160, seed=20 + i)
            dd = ImageDraw.Draw(card)
            dd.ellipse((40, 50, 100, 110), fill=[RED, (240, 150, 0), RED][i])
            dd.text((70, 80), "!", font=font("head", 52), fill="white", anchor="mm")
            dd.text((140, 34), title, font=font("head", 58), fill=INK)
            dd.text((140, 104), sub, font=font("med", 30), fill=(90, 84, 76))
            card = shadowed(card)
            paste(img, card, W / 2, y, scale=p)
            marker(img, (W / 2 - 470, y + 60, W / 2 + 470, y + 72), prog(lv, st + 0.4, 0.5))
    elif v < 17.1:
        lv = v - 13.6
        fx = ease_out(prog(lv, 0, 0.5))
        card = torn_card(520, 600, seed=31)
        dd = ImageDraw.Draw(card)
        dd.text((40, 40), "Fale com a gente", font=font("head", 50), fill=INK)
        for k, lab in enumerate(["Nome", "WhatsApp", "E-mail"]):
            dd.text((40, 130 + k * 120), lab, font=font("med", 26), fill=(90, 84, 76))
            dd.rounded_rectangle((40, 165 + k * 120, 480, 215 + k * 120), 10, outline=INK, width=3)
        dd.rounded_rectangle((40, 510, 480, 570), 14, fill=GREEN)
        dd.text((260, 540), "ENVIAR", font=font("head", 36), fill="white", anchor="mm")
        paste(img, shadowed(card), lerp(-300, 520, fx), 520, rot=-3)
        for i, lab in enumerate(["+ Contato criado", "+ Negócio no funil", "+ Automação disparada"]):
            p = back(prog(lv, 1.0 + i * 0.5, 0.4))
            if p > 0:
                paste(img, channel_chip(lab, [INK, GREEN, (60, 90, 200)][i]), 1300, 330 + i * 170, scale=p)
            if p > 0.5:
                d.line((800, 520, 1040, 330 + i * 170), fill=INK, width=4)
    else:
        lv = v - 17.1
        # agenda
        d.rounded_rectangle((560, 180, 1360, 800), 28, fill=(252, 248, 240), outline=INK, width=6)
        d.rectangle((560, 180, 1360, 280), fill=RED)
        text(img, (960, 230), "AGENDE SEU HORÁRIO", font("head", 56), (255, 255, 255), "mm")
        for k in range(15):
            x = 610 + (k % 5) * 145
            y = 320 + (k // 5) * 150
            pick = k == 7
            fill = YELLOW if pick and lv > 0.6 else "white"
            d.rounded_rectangle((x, y, x + 125, y + 120), 14, fill=fill, outline=INK, width=3)
            text(img, (x + 62, y + 60), f"{9 + k % 5}h", font("head", 44), INK, "mm")
        if lv > 0.9:
            stamp(img, 1340, 760, "MARCADO", lv, 0.9, GREEN, rot=-10)


def scene10(img, t, D):
    v = t - 0.5
    if v < 6.6:
        paste(img, sprite("phone"), 760, 560, rot=-4)
        paste(img, sprite("bubble_in"), 720, 380, rot=-4)
        paste(img, sprite("bubble_out"), 820, 530, scale=back(prog(v, 0.4, 0.4)), rot=-4)
        headline(img, (1120, 340), "Seu próximo cliente", 76, v, 0.3)
        headline(img, (1120, 440), "já mandou mensagem.", 76, v, 1.2, mark=1.8)
        headline(img, (1120, 640), "Alguém vai", 76, v, 4.6)
        headline(img, (1120, 740), "lembrar dele?", 76, v, 5.0, color=RED)
    else:
        lv = v - 6.6
        p = ease(prog(lv, 0, 0.6))
        ImageDraw.Draw(img).rectangle((0, 0, W, H * p), fill=NAVY)
        paste(img, sprite("star"), W / 2, 330, scale=0.6 * back(prog(lv, 0.3, 0.6)), rot=t * 10)
        text(img, (W / 2, 520), "ANTARES CRM", font("head", 140), (255, 255, 255), "mt", alpha=ease(prog(lv, 0.5, 0.5)))
        text(img, (W / 2, 700), "Nenhum cliente esquecido.", font("bold", 56), YELLOW, "mt", alpha=ease(prog(lv, 0.9, 0.5)))
        text(img, (W / 2, 800), "antares.douglasgermano.com", font("med", 40), (220, 220, 230), "mt", alpha=ease(prog(lv, 1.3, 0.5)))


SCENES = [scene1, scene2, scene3, scene4, scene5, scene6, scene7, scene8, scene9, scene10]
LEAD = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.2, 0.5, 0.5]
TAIL = [1.0, 0.8, 0.8, 1.4, 1.0, 0.9, 1.0, 1.0, 0.8, 4.0]


def vo_duration(i):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(AUDIO / "vo" / f"cena{i:02d}.mp3")], capture_output=True, text=True).stdout
    return float(out)


def build_timeline():
    tl, start = [], 0.0
    for i in range(10):
        vd = vo_duration(i + 1)
        dur = LEAD[i] + vd + TAIL[i]
        tl.append({"scene": i + 1, "start": round(start, 3), "dur": round(dur, 3), "vo_at": round(start + LEAD[i], 3)})
        start += dur
    return tl


@lru_cache(None)
def plate(i):
    p = IMAGES / f"cena{i:02d}.png"
    if not p.exists():
        return None
    im = Image.open(p).convert("RGB")
    s = max(W * 1.12 / im.width, H * 1.12 / im.height)
    return im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)


def frame(tl, gt, frame_no):
    idx = max(i for i, s in enumerate(tl) if s["start"] <= gt + 1e-6)
    sc = tl[idx]
    t = gt - sc["start"]
    img = PAPER.copy().convert("RGBA")
    pl = plate(idx + 1)
    if pl is not None:
        k = t / sc["dur"]
        ox = int((pl.width - W) * (0.2 + 0.6 * k))
        oy = int((pl.height - H) * 0.5)
        img.paste(pl.crop((ox, oy, ox + W, oy + H)).convert("RGBA"), (0, 0))
        veil = Image.new("RGBA", (W, H), CREAM + (70,))
        img.alpha_composite(veil)
    SCENES[idx](img, t, sc["dur"])
    # transição: varrida de papel nos primeiros 0,35 s (exceto cena 1)
    if idx > 0 and t < 0.35 and idx not in (7,):
        p = ease(t / 0.35)
        ImageDraw.Draw(img).rectangle((W * p, 0, W, H), fill=CREAM)
    # fade de entrada/saída do vídeo
    total = tl[-1]["start"] + tl[-1]["dur"]
    rgb = img.convert("RGB")
    g = GRAINS[(frame_no // 2) % len(GRAINS)]
    rgb = Image.blend(rgb, Image.merge("RGB", (g, g, g)), 0.05)
    fade = min(clamp(gt / 0.5), clamp((total - gt) / 0.8))
    if fade < 1:
        rgb = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), rgb, fade)
    return rgb


SFX = [
    # (cena, segundos após o início da cena, efeito, volume)
    (1, 1.1, "notificacao", 0.8), (1, 4.2, "tique_lento", 0.5), (1, 5.5, "carimbo", 0.9),
    (2, 0.0, "papel", 0.6), (2, 0.2, "pop", 0.5), (2, 3.1, "pop_ui", 0.6), (2, 3.6, "pop_ui", 0.5), (2, 4.1, "pop_ui", 0.5),
    (3, 0.0, "papel", 0.6), (3, 2.3, "carimbo", 0.8),
    (4, 0.0, "whoosh", 0.4), (4, 2.4, "rabisco", 0.6),
    (5, 0.0, "papel", 0.7), (5, 2.5, "maquina_escrever", 0.5), (5, 5.6, "carimbo", 0.8), (5, 8.4, "tique_rapido", 0.45),
    (6, 0.0, "whoosh", 0.4), (6, 2.4, "pop", 0.5), (6, 3.8, "riser", 0.35), (6, 4.5, "rabisco", 0.6),
    (7, 1.5, "papel", 0.6), (7, 2.7, "pop_ui", 0.5), (7, 3.5, "papel", 0.6), (7, 4.7, "rabisco", 0.6), (7, 5.6, "glitch", 0.35), (7, 6.8, "pop", 0.5),
    (8, 0.0, "riser", 0.6), (8, 1.5, "whoosh", 0.5),
    (9, 0.8, "pop_ui", 0.5), (9, 1.3, "pop_ui", 0.5), (9, 1.8, "pop_ui", 0.5), (9, 2.3, "pop_ui", 0.5), (9, 5.2, "whoosh", 0.4),
    (9, 7.8, "pop", 0.5), (9, 9.2, "pop", 0.5), (9, 11.0, "pop", 0.5), (9, 14.1, "papel", 0.6), (9, 15.1, "pop_ui", 0.5),
    (9, 15.6, "pop_ui", 0.5), (9, 16.1, "pop_ui", 0.5), (9, 18.5, "carimbo", 0.8),
    (10, 0.9, "notificacao", 0.8), (10, 7.1, "whoosh", 0.5),
]


def mix_audio(tl, total, dst):
    inputs, filters, labels = [], [], []
    cut = tl[7]["start"] + 0.6
    inputs += ["-i", str(AUDIO / "music" / "vestige.wav"), "-i", str(AUDIO / "music" / "observatory.wav")]
    filters.append(f"[0:a]atrim=0:{cut + 1.5},afade=t=in:d=1.0,afade=t=out:st={cut - 0.5}:d=2.0,volume=0.22[m1]")
    filters.append(f"[1:a]atrim=0:{total - cut + 0.5},afade=t=in:d=1.2,afade=t=out:st={total - cut - 3.0}:d=3.0,volume=0.26,adelay={int(cut * 1000)}|{int(cut * 1000)}[m2]")
    labels += ["[m1]", "[m2]"]
    n = 2
    for s in tl:
        inputs += ["-i", str(AUDIO / "vo" / f"cena{s['scene']:02d}.mp3")]
        ms = int(s["vo_at"] * 1000)
        filters.append(f"[{n}:a]aresample=48000,volume=1.6,adelay={ms}|{ms}[v{n}]")
        labels.append(f"[v{n}]")
        n += 1
    for sc, off, name, vol in SFX:
        inputs += ["-i", str(AUDIO / "sfx" / f"{name}.wav")]
        ms = int((tl[sc - 1]["start"] + off) * 1000)
        filters.append(f"[{n}:a]aresample=48000,volume={vol * 0.7},adelay={ms}|{ms}[s{n}]")
        labels.append(f"[s{n}]")
        n += 1
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,atrim=0:{total},loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-ar", "48000", str(dst)]
    subprocess.run(cmd, check=True)


def main():
    global PAPER, GRAINS
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", action="store_true", help="salva um quadro do meio de cada cena")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    PAPER = make_paper()
    GRAINS = [make_grain(s) for s in range(4)]
    tl = build_timeline()
    total = tl[-1]["start"] + tl[-1]["dur"]
    (OUT / "timeline.json").write_text(json.dumps(tl, indent=1))
    if args.stills:
        for s in tl:
            for frac in (0.45, 0.85):
                gt = s["start"] + s["dur"] * frac
                frame(tl, gt, 0).save(OUT / f"still_{s['scene']:02d}_{int(frac * 100)}.jpg", quality=80)
        return
    audio = OUT / "mix.wav"
    mix_audio(tl, total, audio)
    video = OUT / "antares-vox.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", str(audio), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
                           "-movflags", "+faststart", str(video)], stdin=subprocess.PIPE)
    nframes = int(total * FPS)
    for f in range(nframes):
        ff.stdin.write(frame(tl, f / FPS, f).tobytes())
        if f % 300 == 0:
            print(f"{f}/{nframes}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("ok", video, round(total, 1), "s")


if __name__ == "__main__":
    main()

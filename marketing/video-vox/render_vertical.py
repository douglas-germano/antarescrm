"""Versão vertical (1080×1920) do vídeo Vox do Antares CRM.

Reaproveita narração, trilha, efeitos e utilitários de render.py.
Imagens das cenas: images/vertical/cenaNN.png (geradas no ChatGPT). Logo: brand/antares-mark.png.
Uso: python3 render_vertical.py [--stills]
"""
import argparse
import json
import math
import random
import subprocess
from functools import lru_cache

from PIL import Image, ImageDraw

import render as r
from render import (CREAM, GRAY, GREEN, INK, RED, YELLOW, back, clamp, ease, ease_out, font, lerp, marker, paste, prog,
                    rounded, shadowed, sprite, stamp, text, torn_card)

W, H, FPS = 1080, 1920, 30
r.W, r.H = W, H
BRAND = (230, 0, 0)
IMG_DIR = r.ROOT / "images" / "vertical"
OUT = r.OUT
PLATE_BOX = (60, 150, 1020, 1150)  # área da ilustração


@lru_cache(None)
def mark(size):
    return Image.open(r.ROOT / "brand" / "antares-mark.png").convert("RGBA").resize((size, size), Image.LANCZOS)


@lru_cache(None)
def plate_src(i):
    p = IMG_DIR / f"cena{i:02d}.png"
    if not p.exists():
        return None
    return Image.open(p).convert("RGB")


@lru_cache(None)
def plate_mask(w, h, seed):
    return torn_card(w, h, (255, 255, 255), seed=seed).split()[3]


@lru_cache(None)
def fade_panel():
    """Degradê creme na base para os textos ficarem legíveis sobre a ilustração."""
    a = Image.new("L", (1, H), 0)
    for y in range(H):
        a.putpixel((0, y), int(255 * 0.94 * clamp((y - 1000) / 260)))
    panel = Image.new("RGBA", (W, H), CREAM + (255,))
    panel.putalpha(a.resize((W, H)))
    return panel


def plate(img, i, t, D, box=None, rot=0, enter=0.0):
    """Ilustração do ChatGPT em tela cheia (9:16), com zoom lento (Ken Burns)."""
    src = plate_src(i)
    if src is None:
        return
    z = 1.0 + 0.07 * clamp(t / max(D, 0.1))
    s = max(W / src.width, H / src.height) * z
    rs = src.resize((int(src.width * s), int(src.height * s)), Image.BICUBIC)
    ox, oy = (rs.width - W) // 2, int((rs.height - H) * 0.3)
    img.paste(rs.crop((ox, oy, ox + W, oy + H)).convert("RGBA"), (0, 0))
    img.alpha_composite(fade_panel())


def source(img, s, t, start=0.6):
    f = font("serif_i", 24)
    words, lines, cur = s.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if ImageDraw.Draw(img).textlength(trial, font=f) > W - 120 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    lines.append(cur)
    for k, ln in enumerate(reversed(lines)):
        text(img, (W / 2, H - 90 - k * 32), ln, f, (90, 84, 76), "ms", alpha=ease(prog(t, start, 0.6)))


def head(img, y, s, size, t, start, mark_at=None, color=INK):
    r.headline(img, (W / 2, y), s, size, t, start, mark=mark_at, color=color, anchor="mt")


def store_row(img, t, states, y):
    for i, st in enumerate(states):
        x = 90 + i * 100
        paste(img, sprite("store:" + st), x, y, scale=0.55 * back(prog(t, 0.1 + i * 0.05, 0.4)))


def clock(img, cx, cy, rad, hrs):
    r.clock(img, cx, cy, rad, hrs)


# ---------- cenas (t = segundos desde o início da cena; VO começa em 0,5 s) ----------

def scene1(img, t, D):
    v = t - 0.5
    plate(img, 1, t, D)
    p = back(prog(v, 0.6, 0.4))
    paste(img, sprite("bubble_in"), 540, 1240, scale=1.3 * p, rot=-3)
    hrs = 14.03 + 6 * ease(prog(v, 3.8, D - 4.3))
    hh, mm = int(hrs), int((hrs - int(hrs)) * 60)
    text(img, (540, 1420), f"{hh:02d}:{mm:02d}", font("head", 120), INK, "mt", alpha=ease(prog(v, 3.8, 0.4)))
    head(img, 1580, "SEM RESPOSTA", 120, v, 5.0, mark_at=5.2)


def scene2(img, t, D):
    v = t - 0.5
    plate(img, 2, t, D)
    store_row(img, t, ["green" if v > 2.6 + i * 0.22 and i < 8 else "off" for i in range(10)], 1260)
    head(img, 1360, "8 EM CADA 10", 150, v, 2.4, mark_at=3.0)
    head(img, 1540, "empresas que vendem online", 58, v, 3.4)
    head(img, 1610, "vendem pelo WhatsApp", 58, v, 3.6)
    source(img, "Fonte: Cetic.br — TIC Empresas 2025 (indicador E2C)", t, 3.5)


def scene3(img, t, D):
    v = t - 0.5
    plate(img, 3, t, D)
    head(img, 1360, "SÓ 3 EM CADA 10", 140, v, 1.4, mark_at=2.4)
    head(img, 1540, "pequenas empresas", 58, v, 2.2)
    head(img, 1610, "usam um CRM", 58, v, 2.4)
    source(img, "Fonte: Cetic.br — TIC Empresas 2025 (indicador G2-3: pequenas empresas, 29%)", t, 2.0)


def scene4(img, t, D):
    v = t - 0.5
    plate(img, 4, t, D)
    head(img, 1260, "MEMÓRIA", 190, v, 1.3)
    head(img, 1470, "VAZA.", 190, v, 1.9, mark_at=2.2)


def scene5(img, t, D):
    v = t - 0.5
    plate(img, 5, t, D, box=(60, 150, 1020, 1000))
    n = int(2241 * ease(prog(v, 2.0, 1.6)))
    if v > 2.0 and v < 5.1:
        text(img, (540, 1300), f"{n:,}".replace(",", ".") + " empresas", font("head", 120), INK, "mt", alpha=ease(prog(v, 2.0, 0.3)))
    if v >= 5.1:
        head(img, 1150, "23%", 200, v, 5.1, mark_at=5.4)
        head(img, 1390, "nunca responderam", 66, v, 5.5)
    if v > 7.8:
        hrs = 2 + 40 * ease(prog(v, 7.9, 2.6))
        clock(img, 340, 1620, 100, hrs)
        text(img, (490, 1620), f"{int(hrs)} h", font("head", 140), RED, "lm", alpha=ease(prog(v, 7.9, 0.3)))
        text(img, (490, 1712), "tempo médio de resposta", font("med", 32), INK, "lt", alpha=ease(prog(v, 8.5, 0.4)))
    source(img, "Fonte: Oldroyd, McElheran e Elkington — “The Short Life of Online Sales Leads”, Harvard Business Review, 2011", t, 1.0)


def scene6(img, t, D):
    v = t - 0.5
    plate(img, 6, t, D, box=(60, 150, 1020, 950))
    d = ImageDraw.Draw(img)
    w5 = 760 * ease_out(prog(v, 1.9, 0.8))
    w30 = 760 / 21 * ease_out(prog(v, 2.6, 0.5))
    text(img, (100, 1120), "5 min", font("head", 50), INK, "lt")
    d.rectangle((100, 1185, 100 + max(w5, 1), 1245), fill=GREEN, outline=INK, width=4)
    text(img, (100, 1265), "30 min", font("head", 50), INK, "lt")
    d.rectangle((100, 1330, 100 + max(w30, 1), 1390), fill=GRAY, outline=INK, width=4)
    head(img, 1430, "ATÉ 21×", 150, v, 3.0, color=RED)
    r.hand_circle(img, 540, 1505, 300, 115, prog(v, 4.0, 0.7))
    head(img, 1650, "mais chance de qualificar o cliente", 52, v, 4.6)
    source(img, "Fonte: Lead Response Management Study (Oldroyd / InsideSales), 2007 — mais de 15 mil leads", t, 2.2)


def scene7(img, t, D):
    v = t - 0.5
    plate(img, 7, t, D)
    for k, (wd, st) in enumerate([("celular", 1.6), ("e-mail", 2.6), ("post-it", 6.3)]):
        p = back(prog(v, st, 0.4))
        if p > 0:
            chip = rounded(300, 110, 20, [INK, (60, 90, 200), YELLOW][k])
            ImageDraw.Draw(chip).text((150, 55), wd, font=font("head", 64), fill=(255, 255, 255) if k < 2 else INK, anchor="mm")
            paste(img, shadowed(chip, (6, 8), 8, 70), [220, 540, 860][k], 1300, scale=p, rot=[-6, 4, -8][k])
    head(img, 1480, "Cadê o cliente?", 110, v, 4.4, mark_at=4.9)


def wordmark(img, cx, y, size, alpha=1.0, color=(255, 255, 255)):
    """antares**crm** como na interface."""
    f1, f2 = font("med", size), font("bold", size)
    d = ImageDraw.Draw(img)
    w1, w2 = d.textlength("antares", font=f1), d.textlength("crm", font=f2)
    x = cx - (w1 + w2) / 2
    text(img, (x, y), "antares", f1, color, "ls", alpha=alpha)
    text(img, (x + w1, y), "crm", f2, color, "ls", alpha=alpha)


def brand_card(img, t, start, tagline=False, url=False):
    p = ease(prog(t, start, 0.6))
    ImageDraw.Draw(img).rectangle((0, H * (1 - p), W, H), fill=BRAND)
    sp = back(prog(t, start + 0.4, 0.6))
    if sp > 0:
        m = mark(420)
        border = Image.new("RGBA", (440, 440), (0, 0, 0, 0))
        ImageDraw.Draw(border).rounded_rectangle((0, 0, 439, 439), 72, fill=(255, 255, 255))
        border.alpha_composite(m, (10, 10))
        paste(img, border, W / 2, 700, scale=sp, rot=lerp(-12, 0, ease_out(prog(t, start + 0.4, 0.8))))
    wordmark(img, W / 2, 1100, 130, alpha=ease(prog(t, start + 0.9, 0.5)))
    if tagline:
        text(img, (W / 2, 1220), "Nenhum cliente esquecido.", font("bold", 64), YELLOW, "mt", alpha=ease(prog(t, start + 1.3, 0.5)))
    if url:
        text(img, (W / 2, 1360), "antares.douglasgermano.com", font("med", 44), (255, 230, 230), "mt", alpha=ease(prog(t, start + 1.7, 0.5)))


def scene8(img, t, D):
    plate(img, 8, t, D)
    brand_card(img, t, 0.9)


CHIPS = {}


def chip(label, color):
    if label not in CHIPS:
        f = font("head", 54)
        w = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(label, font=f)) + 80
        s = rounded(w, 100, 50, color)
        ImageDraw.Draw(s).text((w / 2, 50), label, font=f, fill="white", anchor="mm")
        CHIPS[label] = shadowed(s, (5, 7), 8, 70)
    return CHIPS[label]


def scene9(img, t, D):
    v = t - 0.5
    d = ImageDraw.Draw(img)
    if v < 7.3:
        plate(img, 9, t, D, box=(60, 150, 1020, 1000))
        if v < 4.7:
            for i, (lab, col) in enumerate([("WhatsApp", GREEN), ("Instagram", (225, 48, 108)), ("E-mail", (60, 90, 200)), ("SMS", (120, 120, 130))]):
                p = back(prog(v, 0.3 + i * 0.5, 0.4))
                paste(img, chip(lab, col), [300, 780, 300, 780][i], [1210, 1210, 1330, 1330][i], scale=0.85 * p)
            head(img, 1450, "Tudo numa caixa", 96, v, 1.0)
            head(img, 1560, "de entrada só", 96, v, 1.2, mark_at=1.8)
        else:
            lv = v - 4.7
            for i, c in enumerate(["NOVO", "CONVERSA", "PROPOSTA"]):
                x = 70 + i * 320
                d.rounded_rectangle((x, 1120, x + 300, 1400), 20, fill=(232, 224, 210), outline=INK, width=4)
                text(img, (x + 150, 1140), c, font("head", 44), INK, "mt")
                d.rounded_rectangle((x + 20, 1200, x + 280, 1285), 14, fill="white", outline=INK, width=3)
            mp = ease(prog(lv, 0.4, 1.2))
            mx = lerp(90, 90 + 640, mp)
            d.rounded_rectangle((mx, 1300, mx + 260, 1385), 14, fill=(255, 246, 200), outline=INK, width=5)
            text(img, (mx + 22, 1322), "Maria · Orçamento", font("bold", 26), INK)
            head(img, 1470, "Cada conversa vira", 90, lv, 0.1)
            head(img, 1580, "um negócio no funil", 90, lv, 0.3, mark_at=0.7)
    elif v < 13.6:
        lv = v - 7.3
        head(img, 220, "PRECISA DE", 110, lv, 0.0)
        head(img, 340, "ATENÇÃO HOJE", 110, lv, 0.2, mark_at=0.6)
        alerts = [("Aguardando resposta", "há 2 h · Maria Souza · WhatsApp", 1.4),
                  ("Sem próxima ação", "Clínica Bem Estar · R$ 4.800", 3.0),
                  ("Retorno atrasado", "João Lima · ligar ontem 16h", 4.8)]
        for i, (title, sub, st) in enumerate(alerts):
            p = back(prog(lv, st, 0.4))
            if p <= 0:
                continue
            y = 700 + i * 330
            card = torn_card(940, 260, seed=20 + i)
            dd = ImageDraw.Draw(card)
            dd.ellipse((40, 70, 140, 170), fill=[RED, (240, 150, 0), RED][i])
            dd.text((90, 120), "!", font=font("head", 80), fill="white", anchor="mm")
            dd.text((180, 60), title, font=font("head", 70), fill=INK)
            dd.text((180, 160), sub, font=font("med", 32), fill=(90, 84, 76))
            paste(img, shadowed(card), W / 2, y, scale=p)
            marker(img, (W / 2 - 290, y + 4, W / 2 + 420, y + 14), prog(lv, st + 0.4, 0.5))
    elif v < 17.1:
        lv = v - 13.6
        fx = ease_out(prog(lv, 0, 0.5))
        card = torn_card(640, 720, seed=31)
        dd = ImageDraw.Draw(card)
        dd.text((50, 50), "Fale com a gente", font=font("head", 64), fill=INK)
        for k, lab in enumerate(["Nome", "WhatsApp", "E-mail"]):
            dd.text((50, 170 + k * 140), lab, font=font("med", 32), fill=(90, 84, 76))
            dd.rounded_rectangle((50, 215 + k * 140, 590, 275 + k * 140), 12, outline=INK, width=3)
        dd.rounded_rectangle((50, 610, 590, 680), 16, fill=GREEN)
        dd.text((320, 645), "ENVIAR", font=font("head", 44), fill="white", anchor="mm")
        paste(img, shadowed(card), W / 2, lerp(-400, 620, fx), rot=-2)
        for i, lab in enumerate(["+ Contato criado", "+ Negócio no funil", "+ Automação disparada"]):
            p = back(prog(lv, 1.0 + i * 0.5, 0.4))
            if p > 0:
                paste(img, chip(lab, [INK, GREEN, (60, 90, 200)][i]), W / 2, 1180 + i * 150, scale=p)
    else:
        lv = v - 17.1
        d.rounded_rectangle((90, 360, 990, 1360), 32, fill=(252, 248, 240), outline=INK, width=6)
        d.rectangle((90, 360, 990, 500), fill=RED)
        text(img, (540, 430), "AGENDE SEU HORÁRIO", font("head", 66), (255, 255, 255), "mm")
        for k in range(12):
            x = 140 + (k % 4) * 210
            y = 560 + (k // 4) * 250
            fill = YELLOW if k == 6 and lv > 0.6 else "white"
            d.rounded_rectangle((x, y, x + 180, y + 200), 18, fill=fill, outline=INK, width=4)
            text(img, (x + 90, y + 100), f"{9 + k % 4 + (k // 4) * 4}h", font("head", 60), INK, "mm")
        head(img, 1460, "O cliente marca sozinho", 84, lv, 0.2)
        if lv > 0.9:
            stamp(img, 760, 1220, "MARCADO", lv, 0.9, GREEN, rot=-10)


def scene10(img, t, D):
    v = t - 0.5
    if v < 6.6:
        plate(img, 10, t, D, box=(60, 150, 1020, 1050))
        head(img, 1320, "Seu próximo cliente", 80, v, 0.3)
        head(img, 1420, "já mandou mensagem.", 80, v, 1.2, mark_at=1.8)
        head(img, 1580, "Alguém vai", 80, v, 4.6)
        head(img, 1680, "lembrar dele?", 80, v, 5.0, color=RED)
    else:
        brand_card(img, v, 6.6, tagline=True, url=True)


SCENES = [scene1, scene2, scene3, scene4, scene5, scene6, scene7, scene8, scene9, scene10]


def frame(tl, gt, n):
    idx = max(i for i, s in enumerate(tl) if s["start"] <= gt + 1e-6)
    sc = tl[idx]
    t = gt - sc["start"]
    img = r.PAPER.copy().convert("RGBA")
    SCENES[idx](img, t, sc["dur"])
    if idx not in (0, 7) and t < 0.35:
        ImageDraw.Draw(img).rectangle((0, H * ease(t / 0.35), W, H), fill=CREAM)
    if idx not in (7,) and not (idx == 9 and t > 7.1):
        m = mark(64)
        img.alpha_composite(m, (W - 64 - 40, 50))
    rgb = img.convert("RGB")
    g = r.GRAINS[(n // 2) % len(r.GRAINS)]
    rgb = Image.blend(rgb, Image.merge("RGB", (g, g, g)), 0.05)
    total = tl[-1]["start"] + tl[-1]["dur"]
    fade = min(clamp(gt / 0.5), clamp((total - gt) / 0.8))
    if fade < 1:
        rgb = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), rgb, fade)
    return rgb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    r.PAPER = r.make_paper()
    r.GRAINS = [r.make_grain(s) for s in range(4)]
    tl = r.build_timeline()
    total = tl[-1]["start"] + tl[-1]["dur"]
    if args.stills:
        for s in tl:
            for frac in (0.5, 0.9):
                frame(tl, s["start"] + s["dur"] * frac, 0).save(OUT / f"v_still_{s['scene']:02d}_{int(frac * 100)}.jpg", quality=80)
        return
    audio = OUT / "mix.wav"
    if not audio.exists():
        r.mix_audio(tl, total, audio)
    video = OUT / "antares-vox-vertical.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", str(audio), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
                           "-movflags", "+faststart", str(video)], stdin=subprocess.PIPE)
    n = int(total * FPS)
    for f in range(n):
        ff.stdin.write(frame(tl, f / FPS, f).tobytes())
        if f % 300 == 0:
            print(f"{f}/{n}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("ok", video, round(total, 1), "s")


if __name__ == "__main__":
    main()

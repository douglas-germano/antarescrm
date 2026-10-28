"""Vídeo vertical de demonstração do Antares CRM (1080×1920).

Telas reais capturadas por capture.mjs (shots/*.png, 390×844 @3x) dentro de um celular, com toques,
zoom e destaques animados; narração, trilha e efeitos do Epidemic Sound (audio/).
Uso: python3 render_demo.py [--stills]
"""
import argparse
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "video-vox"))
import render as r  # noqa: E402
from render import INK, YELLOW, back, clamp, ease, ease_out, font, lerp, marker, prog  # noqa: E402

W, H, FPS = 1080, 1920, 30
BRAND = (230, 0, 0)
BG = (244, 241, 236)
SHOTS = ROOT / "shots"
AUDIO = ROOT / "audio"
OUT = ROOT / "out"
TARGETS = json.loads((SHOTS / "targets.json").read_text())

SCREEN_W = 760  # largura da tela do celular no vídeo
K = SCREEN_W / 390  # px CSS → px do vídeo
SCREEN_H = int(844 * K)
BEZEL = 22
PHONE_CX, PHONE_TOP = W / 2, 390
SCREEN_CY = PHONE_TOP + BEZEL + SCREEN_H / 2

# Narração: (arquivo, início em s, legenda)
VO = [
    ("l01", 0.4, "Quantos clientes ficaram sem resposta essa semana?"),
    ("l02", 4.0, "WhatsApp, Instagram e e-mail numa caixa de entrada só."),
    ("l03", 10.2, "Você vê quem está esperando e responde dali mesmo."),
    ("l04", 15.2, "Cada conversa vira um negócio no funil."),
    ("l05", 21.0, "A tela inicial mostra o que precisa de atenção hoje."),
    ("l06", 27.6, "Um toque, e o próximo passo fica agendado."),
    ("l07", 32.0, None),
]
TOTAL = 36.5


@lru_cache(None)
def shot(name):
    im = Image.open(SHOTS / f"{name}.png").convert("RGB")
    return im.resize((SCREEN_W, SCREEN_H), Image.LANCZOS)


@lru_cache(None)
def phone_shell():
    w, h = SCREEN_W + 2 * BEZEL, SCREEN_H + 2 * BEZEL
    s = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(s).rounded_rectangle((0, 0, w - 1, h - 1), 74, fill=(18, 18, 20))
    return s


@lru_cache(None)
def screen_mask():
    m = Image.new("L", (SCREEN_W, SCREEN_H), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, SCREEN_W - 1, SCREEN_H - 1), 54, fill=255)
    return m


@lru_cache(None)
def phone_shadow():
    w, h = SCREEN_W + 2 * BEZEL, SCREEN_H + 2 * BEZEL
    pad = 80
    s = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(s).rounded_rectangle((pad + 10, pad + 30, pad + w - 10, pad + h + 10), 74, fill=(60, 40, 30, 90))
    return s.filter(ImageFilter.GaussianBlur(34))


def phone_image(screen):
    p = phone_shell().copy()
    sc = screen.convert("RGBA")
    sc.putalpha(screen_mask())
    p.alpha_composite(sc, (BEZEL, BEZEL))
    return p


def blend_screens(a, b, x):
    return a if x <= 0 else b if x >= 1 else Image.blend(a, b, ease(x))


def slide_screens(a, b, x):
    """Transição de navegação: a nova tela entra pela direita."""
    if x <= 0:
        return a
    if x >= 1:
        return b
    e = ease(x)
    out = Image.new("RGB", (SCREEN_W, SCREEN_H))
    out.paste(a, (int(-SCREEN_W * 0.3 * e), 0))
    out.paste(b, (int(SCREEN_W * (1 - e)), 0))
    return out


def tgt(name, dy=0):
    """Centro de um alvo em px de tela do vídeo (relativo ao canto da tela)."""
    b = TARGETS[name]
    return (b["x"] + b["width"] / 2) * K, (b["y"] + b["height"] / 2 + dy) * K


# Câmera: (tempo, zoom, foco_x, foco_y em px da tela) — interpolada com easing.
CAM = [
    (0.0, 1.0, SCREEN_W / 2, SCREEN_H / 2),
    (6.6, 1.0, SCREEN_W / 2, SCREEN_H / 2),
    (7.4, 1.45, SCREEN_W / 2, 450 * K),
    (10.0, 1.45, SCREEN_W / 2, 450 * K),
    (10.8, 1.0, SCREEN_W / 2, SCREEN_H / 2),
    (11.6, 1.0, SCREEN_W / 2, SCREEN_H / 2),
    (12.3, 1.5, SCREEN_W / 2, 650 * K),
    (14.8, 1.5, SCREEN_W / 2, 650 * K),
    (15.6, 1.0, SCREEN_W / 2, SCREEN_H / 2),
    (16.4, 1.0, SCREEN_W / 2, SCREEN_H / 2),
    (17.2, 1.55, 160 * K, 690 * K),
    (20.4, 1.55, 160 * K, 690 * K),
    (21.2, 1.0, SCREEN_W / 2, SCREEN_H / 2),
    (22.6, 1.0, SCREEN_W / 2, SCREEN_H / 2),
    (23.4, 1.5, SCREEN_W / 2, 690 * K),
    (27.2, 1.5, SCREEN_W / 2, 690 * K),
    (28.0, 1.0, SCREEN_W / 2, SCREEN_H / 2),
    (30.7, 1.0, SCREEN_W / 2, SCREEN_H / 2),
    (31.3, 1.0, SCREEN_W / 2, SCREEN_H / 2 + 330),
]


def camera(t):
    for (t0, z0, x0, y0), (t1, z1, x1, y1) in zip(CAM, CAM[1:]):
        if t0 <= t <= t1:
            e = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1
            return lerp(z0, z1, e), lerp(x0, x1, e), lerp(y0, y1, e)
    return CAM[-1][1:]


def current_screen(t):
    s = shot
    if t < 10.5:
        return s("01_inbox")
    if t < 11.2:
        return slide_screens(s("01_inbox"), s("02_conversa"), (t - 10.5) / 0.5)
    if t < 12.6:
        return s("02_conversa")
    if t < 13.6:
        return blend_screens(s("02_conversa"), s("03_resposta"), (t - 12.6) / 0.3)
    if t < 15.6:
        return blend_screens(s("03_resposta"), s("03b_enviada"), (t - 13.9) / 0.3)
    if t < 16.0:
        return slide_screens(s("03b_enviada"), s("04_funil"), (t - 15.6) / 0.4)
    if t < 18.6:
        return s("04_funil")
    if t < 19.6:
        return slide_screens(s("04_funil"), s("05_funil_b"), (t - 18.6) / 0.5)
    if t < 21.0:
        return s("05_funil_b")
    if t < 21.5:
        return slide_screens(s("05_funil_b"), s("07_atencao"), (t - 21.0) / 0.5)
    if t < 28.3:
        return s("07_atencao")
    if t < 30.6:
        return blend_screens(s("07_atencao"), s("08_agendar"), (t - 28.3) / 0.3)
    return blend_screens(s("08_agendar"), s("09_agendado"), (t - 30.6) / 0.3)


# Toques: (tempo, alvo, deslocamento y em px CSS)
TAPS = [(10.2, "inbox_maria", 10), (13.6, "composer", 0), (28.0, "agendar", 0), (30.3, "salvar", 0)]
# Destaques: (início, fim, alvo, margem em px CSS)
HIGHLIGHTS = [(7.6, 10.0, "inbox_maria", (-60, -8, 70, 26)), (17.4, 18.5, "crm_card_maria", (-12, -16, 12, 100)),
              (23.6, 27.0, "atencao", (-10, -12, 230, 270))]


def draw_tap(layer, t):
    d = ImageDraw.Draw(layer)
    for t0, name, dy in TAPS:
        lt = t - t0
        if -0.35 < lt < 0.6:
            x, y = tgt(name, dy)
            if lt < 0:  # dedo se aproximando
                a = 1 + lt / 0.35
                d.ellipse((x - 38, y - 38, x + 38, y + 38), fill=(255, 255, 255, int(110 * a)), outline=(0, 0, 0, int(80 * a)), width=3)
            else:
                rr = 38 + 70 * ease_out(lt / 0.6)
                a = 1 - lt / 0.6
                d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=BRAND + (int(230 * a),), width=8)
                d.ellipse((x - 34, y - 34, x + 34, y + 34), fill=(255, 255, 255, int(160 * a)))


def draw_highlights(layer, t):
    d = ImageDraw.Draw(layer)
    for t0, t1, name, (ml, mt, mr, mb) in HIGHLIGHTS:
        if t0 <= t <= t1:
            b = TARGETS[name]
            p = ease_out(prog(t, t0, 0.35)) * (1 - ease(prog(t, t1 - 0.3, 0.3)))
            x0, y0 = (b["x"] + ml) * K, (b["y"] + mt) * K
            x1, y1 = (b["x"] + b["width"] + mr) * K, (b["y"] + b["height"] + mb) * K
            g = 14 * (1 - p)
            d.rounded_rectangle((x0 - g, y0 - g, x1 + g, y1 + g), 18, outline=BRAND + (int(255 * p),), width=7)


def phone_frame(t):
    sc = current_screen(t).convert("RGBA")
    over = Image.new("RGBA", sc.size, (0, 0, 0, 0))
    draw_highlights(over, t)
    draw_tap(over, t)
    sc.alpha_composite(over)
    return phone_image(sc.convert("RGB"))


def caption(img, t):
    """Legenda da narração no topo, com marca-texto na linha ativa."""
    cur = None
    for name, start, text in VO:
        if text and start - 0.15 <= t:
            cur = (start, text)
    if not cur or t > 31.8:
        return
    start, s = cur
    f = font("head", 74)
    d = ImageDraw.Draw(img)
    words, lines, line = s.split(), [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if d.textlength(trial, font=f) > W - 140 and line:
            lines.append(line)
            line = w
        else:
            line = trial
    lines.append(line)
    a = ease(prog(t, start - 0.15, 0.35))
    y0 = 110 if len(lines) < 3 else 80
    for i, ln in enumerate(lines):
        y = y0 + i * 92 + (1 - a) * 24
        if i == len(lines) - 1:
            bb = d.textbbox((W / 2, y), ln, font=f, anchor="mt")
            marker(img, (bb[0] - 8, bb[1] - 2, bb[2] + 8, bb[3] + 10), prog(t, start + 0.3, 0.5))
        r.text(img, (W / 2, y), ln, f, INK, "mt", alpha=a)


def wordmark(img, cx, y, size, alpha=1.0, color=(255, 255, 255)):
    f1, f2 = font("med", size), font("bold", size)
    d = ImageDraw.Draw(img)
    w1, w2 = d.textlength("antares", font=f1), d.textlength("crm", font=f2)
    x = cx - (w1 + w2) / 2
    r.text(img, (x, y), "antares", f1, color, "ls", alpha=alpha)
    r.text(img, (x + w1, y), "crm", f2, color, "ls", alpha=alpha)


@lru_cache(None)
def mark(size):
    return Image.open(ROOT.parent / "video-vox" / "brand" / "antares-mark.png").convert("RGBA").resize((size, size), Image.LANCZOS)


@lru_cache(None)
def hook_plate():
    im = Image.open(ROOT.parent / "video-vox" / "images" / "vertical" / "cena01.png").convert("RGB")
    s = max(W / im.width, H / im.height)
    return im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)


def frame(t, n):
    img = Image.new("RGBA", (W, H), BG + (255,))
    if t < 3.7:  # gancho com a ilustração do vídeo Vox
        pl = hook_plate()
        z = 1 + 0.05 * t / 3.7
        rs = pl.resize((int(pl.width * z), int(pl.height * z)), Image.BICUBIC)
        ox, oy = (rs.width - W) // 2, (rs.height - H) // 3
        img.paste(rs.crop((ox, oy, ox + W, oy + H)).convert("RGBA"), (0, 0))
        veil = Image.new("RGBA", (W, 560), BG + (225,))
        img.alpha_composite(veil, (0, 0))
    if t >= 3.2 and t < 32.6:
        z, fx, fy = camera(t)
        enter = ease_out(prog(t, 3.2, 0.8))
        exit_ = ease(prog(t, 31.6, 0.8))
        ph = phone_frame(t)
        pw, phh = ph.size
        if abs(z - 1) > 0.01:
            ph = ph.resize((int(pw * z), int(phh * z)), Image.BICUBIC)
        # o ponto de foco (fx, fy) da tela fica no centro da área do celular
        cx = PHONE_CX + (SCREEN_W / 2 - fx) * z
        cy = SCREEN_CY + (SCREEN_H / 2 - fy) * z
        cy += (1 - enter) * 1200 + exit_ * 1300
        sh = phone_shadow()
        if z < 1.05:
            img.alpha_composite(sh, (int(cx - sh.width / 2), int(cy - sh.height / 2 + 20)))
        img.alpha_composite(ph, (int(cx - ph.width / 2), int(cy - ph.height / 2)))
    # faixa superior para a legenda
    if 3.2 <= t < 32.0:
        band = Image.new("RGBA", (W, 400), BG + (255,))
        a = band.split()[3].point(lambda v: v)
        grad = Image.linear_gradient("L").rotate(180).resize((W, 400))
        band.putalpha(Image.eval(grad, lambda v: min(255, int(v * 1.6))))
        img.alpha_composite(band, (0, 0))
        del a
    caption(img, t)
    if t >= 31.6:  # encerramento com a marca
        lt = t - 31.6
        p = ease(prog(lt, 0, 0.6))
        ImageDraw.Draw(img).rectangle((0, H * (1 - p), W, H), fill=BRAND)
        sp = back(prog(lt, 0.4, 0.6))
        if sp > 0:
            m = mark(400)
            border = Image.new("RGBA", (420, 420), (0, 0, 0, 0))
            ImageDraw.Draw(border).rounded_rectangle((0, 0, 419, 419), 70, fill=(255, 255, 255))
            border.alpha_composite(m, (10, 10))
            r.paste(img, border, W / 2, 680, scale=sp)
        wordmark(img, W / 2, 1060, 128, alpha=ease(prog(lt, 0.9, 0.5)))
        r.text(img, (W / 2, 1170), "Nenhum cliente esquecido.", font("bold", 62), YELLOW, "mt", alpha=ease(prog(lt, 1.3, 0.5)))
        r.text(img, (W / 2, 1300), "antares.douglasgermano.com", font("med", 44), (255, 230, 230), "mt", alpha=ease(prog(lt, 1.7, 0.5)))
    elif t >= 3.2:
        img.alpha_composite(mark(64), (W - 104, 40))
    rgb = img.convert("RGB")
    fade = min(clamp(t / 0.4), clamp((TOTAL - t) / 0.6))
    if fade < 1:
        rgb = Image.blend(Image.new("RGB", (W, H)), rgb, fade)
    return rgb


SFX = [(0.6, "notificacao", 0.7), (3.2, "swoosh", 0.5), (4.3, "notificacao", 0.5), (7.4, "swish", 0.35),
       (10.2, "toque", 0.9), (10.5, "swish", 0.35), (13.6, "toque", 0.9), (13.9, "swoosh", 0.55),
       (15.6, "swish", 0.35), (17.2, "pop_ui", 0.5), (18.6, "swish", 0.35), (21.0, "swish", 0.35), (23.4, "pop_ui", 0.5),
       (28.0, "toque", 0.9), (30.3, "toque", 0.9), (30.5, "confirma", 0.8), (31.6, "swoosh", 0.6)]


def mix(dst):
    inputs, filt, labels = ["-i", str(AUDIO / "music" / "a_step_ahead.wav")], [], ["[m]"]
    filt.append(f"[0:a]atrim=0:{TOTAL},afade=t=in:d=0.8,afade=t=out:st={TOTAL - 2.5}:d=2.5,volume=0.2[m]")
    n = 1
    for name, start, _ in VO:
        inputs += ["-i", str(AUDIO / "vo" / f"{name}.mp3")]
        ms = int(start * 1000)
        filt.append(f"[{n}:a]aresample=48000,volume=1.7,adelay={ms}|{ms}[v{n}]")
        labels.append(f"[v{n}]")
        n += 1
    for start, name, vol in SFX:
        inputs += ["-i", str(AUDIO / "sfx" / f"{name}.wav")]
        ms = int(start * 1000)
        filt.append(f"[{n}:a]aresample=48000,volume={vol * 0.7},adelay={ms}|{ms}[s{n}]")
        labels.append(f"[s{n}]")
        n += 1
    filt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,atrim=0:{TOTAL},loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt),
                    "-map", "[out]", "-ar", "48000", str(dst)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    if args.stills:
        for t in (1.5, 5.0, 8.5, 12.0, 14.5, 18.0, 19.8, 22.0, 25.0, 29.0, 31.4, 34.5):
            frame(t, 0).save(OUT / f"still_{t:05.1f}.jpg", quality=80)
        return
    audio = OUT / "mix.wav"
    mix(audio)
    video = OUT / "antares-demo-vertical.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", str(audio), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(video)],
                          stdin=subprocess.PIPE)
    n = int(TOTAL * FPS)
    for f in range(n):
        ff.stdin.write(frame(f / FPS, f).tobytes())
    ff.stdin.close()
    ff.wait()
    print("ok", video)


if __name__ == "__main__":
    main()

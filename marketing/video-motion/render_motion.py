"""Motion graphics vertical (1080×1920) do Antares CRM — estilo limpo, tipografia cinética e cores da marca.

Desenha em 2× (2160×3840) e reduz, para bordas suaves. Narração, trilha e efeitos: Epidemic Sound (audio/).
Uso: python3 render_motion.py [--stills]
"""
import argparse
import math
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "video-vox"))
from render import back, clamp, ease, ease_out, lerp, prog  # noqa: E402

W, H, FPS, SS = 1080, 1920, 30, 2
BG = (247, 247, 245)
INK = (17, 17, 17)
RED = (230, 0, 0)
GRAY = (226, 226, 222)
MID = (150, 150, 146)
WHITE = (255, 255, 255)
CH = [("WhatsApp", (37, 211, 102)), ("Instagram", (225, 48, 108)), ("E-mail", (52, 104, 214)), ("SMS", (120, 120, 128))]
AVENIR = "/System/Library/Fonts/Avenir Next.ttc"
AUDIO = ROOT / "audio"
OUT = ROOT / "out"

VO = [("m01", 0.5), ("m02", 3.8), ("m03", 8.7), ("m04", 11.8), ("m05", 17.0), ("m06", 20.3), ("m07", 25.9)]
TOTAL = 30.5


@lru_cache(None)
def F(size, weight="bold"):
    idx = {"bold": 0, "demi": 2, "medium": 5, "regular": 7, "heavy": 8}[weight]
    return ImageFont.truetype(AVENIR, int(size * SS), index=idx)


def s(v):
    return v * SS


class Canvas:
    """Desenho em coordenadas 1080×1920, renderizado em 2×."""

    def __init__(self, bg=BG):
        self.img = Image.new("RGBA", (W * SS, H * SS), bg + (255,))

    def layer(self):
        return Image.new("RGBA", self.img.size, (0, 0, 0, 0))

    def comp(self, layer, alpha=1.0):
        if alpha < 0.999:
            layer.putalpha(layer.split()[3].point(lambda v: int(v * alpha)))
        self.img.alpha_composite(layer)

    def rrect(self, box, r, fill=None, outline=None, width=0, alpha=1.0):
        if alpha <= 0:
            return
        L = self.layer()
        x0, y0, x1, y1 = box
        ImageDraw.Draw(L).rounded_rectangle((s(x0), s(y0), s(x1), s(y1)), s(r), fill=fill, outline=outline, width=int(s(width)))
        self.comp(L, alpha)

    def circle(self, cx, cy, r, fill=None, outline=None, width=0, alpha=1.0):
        if alpha <= 0 or r <= 0:
            return
        L = self.layer()
        ImageDraw.Draw(L).ellipse((s(cx - r), s(cy - r), s(cx + r), s(cy + r)), fill=fill, outline=outline, width=int(s(width)))
        self.comp(L, alpha)

    def line(self, pts, fill, width, alpha=1.0):
        if alpha <= 0 or len(pts) < 2:
            return
        L = self.layer()
        ImageDraw.Draw(L).line([(s(x), s(y)) for x, y in pts], fill=fill, width=int(s(width)), joint="curve")
        self.comp(L, alpha)

    def text(self, xy, t, size, fill=INK, weight="bold", anchor="mm", alpha=1.0):
        if alpha <= 0:
            return
        L = self.layer()
        ImageDraw.Draw(L).text((s(xy[0]), s(xy[1])), t, font=F(size, weight), fill=fill, anchor=anchor)
        self.comp(L, alpha)

    def width(self, t, size, weight="bold"):
        return ImageDraw.Draw(self.img).textlength(t, font=F(size, weight)) / SS

    def final(self):
        return self.img.convert("RGB").resize((W, H), Image.LANCZOS)


def kinetic(c, lines, t, start, y, size=96, color=INK, weight="heavy", red_words=(), gap=1.12, stagger=0.09, out_at=None):
    """Palavras sobem e aparecem uma a uma; some (sobe) a partir de out_at."""
    k = 0
    out = ease(prog(t, out_at, 0.35)) if out_at else 0
    for li, line in enumerate(lines):
        words = line.split()
        total = sum(c.width(w + " ", size, weight) for w in words) - c.width(" ", size, weight)
        x = W / 2 - total / 2
        for w in words:
            p = ease_out(prog(t, start + k * stagger, 0.45))
            if p > 0:
                col = RED if w.strip(".,:") in red_words else color
                c.text((x, y + li * size * gap + (1 - p) * 40 - out * 60), w, size, col, weight, "lm", alpha=p * (1 - out))
            x += c.width(w + " ", size, weight)
            k += 1


def bubble(c, cx, cy, w, h, dark=False, alpha=1.0, scale=1.0, lines=2):
    if scale <= 0.01:
        return
    w, h = w * scale, h * scale
    x0, y0 = cx - w / 2, cy - h / 2
    c.rrect((x0, y0, x0 + w, y0 + h), 30 * scale, fill=INK if dark else WHITE, alpha=alpha)
    bar = (90, 90, 90) if dark else GRAY
    for i in range(lines):
        bw = (w - 60 * scale) * (0.9 if i == 0 else 0.55)
        yy = y0 + 30 * scale + i * 30 * scale
        c.rrect((x0 + 30 * scale, yy, x0 + 30 * scale + bw, yy + 14 * scale), 7 * scale, fill=bar, alpha=alpha)


def scene_a(c, t):
    """0–3,6 s: Toda venda começa com uma mensagem."""
    kinetic(c, ["Toda venda", "começa com uma", "mensagem."], t, 0.5, 330, 104, red_words=("mensagem",), out_at=3.3)
    out = ease(prog(t, 3.25, 0.4))
    for i, (dx, dy, dark) in enumerate([(-90, 0, False), (110, 210, True), (-60, 420, False)]):
        p = back(prog(t, 0.9 + i * 0.35, 0.45))
        bubble(c, W / 2 + dx, 1000 + dy, 660, 150, dark, alpha=min(1, p) * (1 - out), scale=p)


def scene_b(c, t):
    """3,6–8 s: quase 1 em cada 4 nunca responde."""
    lt = t - 3.6
    kinetic(c, ["Quase 1 em cada 4"], lt, 0.2, 320, 92, red_words=("1", "4"), out_at=4.05)
    kinetic(c, ["empresas nunca responde."], lt, 0.7, 450, 64, color=INK, weight="demi", out_at=4.05)
    out = ease(prog(lt, 4.0, 0.4))
    cols, rows = 4, 5
    for i in range(cols * rows):
        r_, c_ = divmod(i, cols)
        cx, cy = 225 + c_ * 210, 760 + r_ * 190
        p = back(prog(lt, 0.15 + i * 0.03, 0.4))
        lost = i in (1, 6, 11, 16, 18)  # 5 de 20 = 25%
        fall = ease(prog(lt, 1.6 + (i % 5) * 0.08, 0.7)) if lost else 0
        col = RED if lost and lt > 1.4 else INK
        a = min(1, p) * (1 - out) * (1 - 0.75 * fall)
        cy += fall * 90
        if p > 0.01:
            c.rrect((cx - 70 * p, cy - 44 * p, cx + 70 * p, cy + 44 * p), 22 * p, fill=None if lost and lt > 1.4 else col,
                    outline=col, width=6, alpha=a)
            if lost and lt > 1.4:
                c.text((cx, cy), "?", 54, RED, "heavy", alpha=a)
    c.text((W / 2, 1800), "Harvard Business Review, 2011: 23% de 2.241 empresas não responderam", 26, MID, "medium",
           alpha=ease(prog(lt, 1.0, 0.5)) * (1 - out))


@lru_cache(None)
def mark(size):
    return Image.open(ROOT.parent / "video-vox" / "brand" / "antares-mark.png").convert("RGBA").resize((int(s(size)),) * 2, Image.LANCZOS)


def logo(c, cx, cy, size, p, on_red=False):
    if p <= 0.01:
        return
    sz = size * p
    if on_red:
        c.rrect((cx - sz / 2 - 10 * p, cy - sz / 2 - 10 * p, cx + sz / 2 + 10 * p, cy + sz / 2 + 10 * p), 0.17 * sz + 8, fill=WHITE)
    m = mark(size).resize((max(1, int(s(sz))),) * 2, Image.LANCZOS)
    c.img.alpha_composite(m, (int(s(cx) - m.width / 2), int(s(cy) - m.height / 2)))


def wordmark(c, cx, y, size, alpha, color=WHITE):
    w1, w2 = c.width("antares", size, "medium"), c.width("crm", size, "bold")
    x = cx - (w1 + w2) / 2
    c.text((x, y), "antares", size, color, "medium", "lm", alpha)
    c.text((x + w1, y), "crm", size, color, "bold", "lm", alpha)


def scene_c(c, t):
    """8–11,4 s: círculo vermelho, logo, 'resolve isso'."""
    lt = t - 8.0
    grow = ease(prog(lt, 0, 0.6))
    shrink = ease(prog(lt, 3.0, 0.4))
    rad = 2300 * grow * (1 - shrink)
    c.circle(W / 2, H / 2, rad, fill=RED)
    if shrink < 0.6:
        a = 1 - ease(prog(lt, 2.8, 0.25))
        logo(c, W / 2, 790, 300, back(prog(lt, 0.55, 0.55)) * a, on_red=True)
        wordmark(c, W / 2, 1060, 120, ease(prog(lt, 0.9, 0.4)) * a)
        kinetic(c, ["resolve isso."], lt, 1.4, 1230, 84, color=WHITE, weight="heavy")
        if a < 1:
            c.circle(W / 2, H / 2, rad, fill=RED, alpha=1 - a)


def scene_d(c, t):
    """11,4–16,8 s: canais convergem para uma caixa de entrada."""
    lt = t - 11.4
    out = ease(prog(lt, 5.05, 0.35))
    box = (240, 1120, 840, 1500)
    bx, by = (box[0] + box[2]) / 2, box[1]
    pts = [(200, 720), (420, 640), (660, 640), (880, 720)]
    hits = [0.5, 1.2, 1.9, 2.4]
    for i, ((name, col), (px, py), h) in enumerate(zip(CH, pts, hits)):
        p = back(prog(lt, h, 0.4))
        lp = ease(prog(lt, h + 0.2, 0.6))
        tx, ty = lerp(px, bx - 150 + i * 100, 1), by
        if lp > 0:
            c.line([(px, py + 60), (lerp(px, tx, lp), lerp(py + 60, ty, lp))], col, 6, alpha=0.5 * (1 - out))
        # partículas indo para a caixa
        for k in range(3):
            q = (lt - h - 0.8 - k * 0.45) % 1.35
            if lt > h + 0.8 and q < 1:
                e = ease(q)
                c.circle(lerp(px, tx, e), lerp(py + 60, ty, e), 12, fill=col, alpha=(1 - out) * (1 - q * 0.3))
        c.circle(px, py, 58 * min(p, 1.2), fill=col, alpha=min(1, p) * (1 - out))
        c.text((px, py + 100), name, 40, INK, "demi", alpha=ease(prog(lt, h + 0.1, 0.3)) * (1 - out))
    bp = back(prog(lt, 0.2, 0.5))
    if bp > 0.01:
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        w2, h2 = (box[2] - box[0]) / 2 * bp, (box[3] - box[1]) / 2 * bp
        c.rrect((cx - w2, cy - h2, cx + w2, cy + h2), 44, fill=INK, alpha=1 - out)
        c.text((cx, cy - 50), "Caixa de entrada", 56, WHITE, "bold", alpha=min(1, bp) * (1 - out))
        n = int(clamp((lt - 1.3) / 3.2) * 24)
        c.text((cx, cy + 55), f"{n} conversas", 46, (200, 200, 200), "medium", alpha=min(1, bp) * (1 - out))
    kinetic(c, ["Tudo num", "lugar só."], lt, 2.9, 300, 112, red_words=("só",), out_at=5.05)


STAGES = ["Novo", "Conversa", "Proposta", "Ganho"]


def scene_e(c, t):
    """16,8–20 s: negócio atravessa o funil."""
    lt = t - 16.8
    out = ease(prog(lt, 2.85, 0.35))
    x0, cw, gap = 70, 220, 20
    for i, st in enumerate(STAGES):
        p = ease_out(prog(lt, 0.05 + i * 0.07, 0.4))
        x = x0 + i * (cw + gap)
        c.rrect((x, 760 + (1 - p) * 60, x + cw, 1500 + (1 - p) * 60), 28, fill=(238, 238, 234), alpha=p * (1 - out))
        c.text((x + cw / 2, 810 + (1 - p) * 60), st, 34, INK if i < 3 else (37, 160, 80), "bold", alpha=p * (1 - out))
        for k in range(2):
            y = 880 + k * 150 + (1 - p) * 60
            c.rrect((x + 18, y, x + cw - 18, y + 120), 18, fill=WHITE, alpha=p * (1 - out) * 0.9)
    # cartão principal pulando de coluna em coluna
    step = clamp((lt - 0.7) / 1.8) * 3
    k = min(3, int(step))
    frac = ease(step - k) if k < 3 else 0
    xa = x0 + k * (cw + gap)
    xb = x0 + min(3, k + 1) * (cw + gap)
    cx = lerp(xa, xb, frac) + cw / 2
    lift = math.sin(frac * math.pi) * 40
    ap = back(prog(lt, 0.4, 0.4))
    if ap > 0.01:
        won = step >= 3
        c.rrect((cx - cw / 2 + 8, 1180 - lift + 10, cx + cw / 2 - 8, 1340 - lift + 10), 22, fill=(0, 0, 0), alpha=0.12 * (1 - out))
        c.rrect((cx - cw / 2 + 8, 1180 - lift, cx + cw / 2 - 8, 1340 - lift), 22, fill=WHITE, outline=(37, 160, 80) if won else RED,
                width=6, alpha=min(1, ap) * (1 - out))
        c.text((cx, 1235 - lift), "Maria Souza", 30, INK, "bold", alpha=min(1, ap) * (1 - out))
        c.text((cx, 1285 - lift), "R$ 2.400", 30, RED if not won else (37, 160, 80), "heavy", alpha=min(1, ap) * (1 - out))
    kinetic(c, ["Cada conversa vira", "um negócio."], lt, 0.15, 330, 92, red_words=("negócio.",), out_at=2.85)


def scene_f(c, t):
    """20–25,2 s: alertas aparecem e são resolvidos."""
    lt = t - 20.0
    out = ease(prog(lt, 4.85, 0.35))
    rows = [("Aguardando resposta", "Maria Souza · há 2 h", RED), ("Sem próxima ação", "Clínica Bem Estar · R$ 4.800", (240, 150, 0)),
            ("Retorno atrasado", "João Lima · ontem 16h", RED)]
    for i, (title, sub, col) in enumerate(rows):
        p = ease_out(prog(lt, 0.4 + i * 0.35, 0.5))
        done = ease_out(prog(lt, 3.0 + i * 0.35, 0.35))
        y = 760 + i * 230
        x = 80 + (1 - p) * 900
        c.rrect((x, y, x + 920, y + 190), 34, fill=WHITE, alpha=p * (1 - out))
        dcol = tuple(int(lerp(a, b, done)) for a, b in zip(col, (37, 160, 80)))
        c.circle(x + 95, y + 95, 38, fill=dcol, alpha=p * (1 - out))
        if done > 0.05:
            cx, cy = x + 95, y + 95
            c.line([(cx - 16, cy + 1), (cx - 4, cy + 14), (cx + 18, cy - 14)], WHITE, 8, alpha=done * (1 - out))
        else:
            c.text((x + 95, y + 93), "!", 48, WHITE, "heavy", alpha=p * (1 - out))
        c.text((x + 170, y + 75), title, 46, INK, "bold", "lm", alpha=p * (1 - out))
        c.text((x + 170, y + 130), sub, 32, MID, "medium", "lm", alpha=p * (1 - out))
        if done > 0:
            tw = c.width(title, 46, "bold")
            c.line([(x + 170, y + 77), (x + 170 + tw * done, y + 77)], INK, 5, alpha=0.6 * done * (1 - out))
    kinetic(c, ["Antes que o", "cliente esfrie."], lt, 0.2, 330, 104, red_words=("esfrie.",), out_at=4.85)


def scene_g(c, t):
    """25,2–30,5 s: encerramento com a marca."""
    lt = t - 25.2
    p = ease(prog(lt, 0, 0.6))
    c.rrect((-50, H * (1 - p) - 50, W + 50, H + 100), 60 * (1 - p), fill=RED)
    logo(c, W / 2, 760, 340, back(prog(lt, 0.45, 0.6)), on_red=True)
    wordmark(c, W / 2, 1070, 130, ease(prog(lt, 0.9, 0.5)))
    c.text((W / 2, 1200), "Nenhum cliente esquecido.", 60, WHITE, "bold", alpha=ease(prog(lt, 1.4, 0.5)))
    c.text((W / 2, 1320), "antares.douglasgermano.com", 42, (255, 215, 215), "medium", alpha=ease(prog(lt, 1.9, 0.5)))


SCENES = [(0, 3.6, scene_a), (3.6, 8.0, scene_b), (8.0, 11.4, scene_c), (11.4, 16.8, scene_d), (16.8, 20.0, scene_e),
          (20.0, 25.2, scene_f), (25.2, TOTAL + 1, scene_g)]


def frame(t):
    c = Canvas()
    for a, b, fn in SCENES:
        if a <= t < b + 0.01:
            fn(c, t)
    im = c.final()
    fade = min(clamp(t / 0.3), clamp((TOTAL - t) / 0.6))
    if fade < 1:
        im = Image.blend(Image.new("RGB", (W, H)), im, fade)
    return im


SFX = [(0.9, "bolha", 0.8), (1.25, "bolha", 0.8), (1.6, "bolha", 0.8), (3.6, "whoosh", 0.5), (3.8, "pop", 0.4),
       (5.0, "dados", 0.5), (8.0, "whoosh", 0.7), (8.6, "pop", 0.6), (11.4, "whoosh", 0.5), (11.9, "bolha", 0.8),
       (12.6, "bolha", 0.8), (13.3, "bolha", 0.8), (13.8, "bolha", 0.8), (14.5, "dados", 0.4), (16.8, "whoosh", 0.4),
       (17.7, "pop", 0.5), (18.3, "pop", 0.5), (18.9, "pop", 0.5), (19.2, "confirma", 0.6), (20.4, "whoosh", 0.4),
       (23.0, "confirma", 0.6), (23.35, "confirma", 0.6), (23.7, "confirma", 0.6), (25.2, "whoosh", 0.6), (25.7, "pop", 0.6)]


def mix(dst):
    inputs, filt, labels = ["-i", str(AUDIO / "music" / "miles.wav")], [], ["[m]"]
    filt.append(f"[0:a]atrim=0:{TOTAL},afade=t=in:d=0.6,afade=t=out:st={TOTAL - 2.2}:d=2.2,volume=0.22[m]")
    n = 1
    for name, start in VO:
        inputs += ["-i", str(AUDIO / "vo" / f"{name}.mp3")]
        ms = int(start * 1000)
        filt.append(f"[{n}:a]aresample=48000,volume=1.7,adelay={ms}|{ms}[v{n}]")
        labels.append(f"[v{n}]")
        n += 1
    for start, name, vol in SFX:
        inputs += ["-i", str(AUDIO / "sfx" / f"{name}.wav")]
        ms = int(start * 1000)
        filt.append(f"[{n}:a]aresample=48000,volume={vol * 0.6},adelay={ms}|{ms}[s{n}]")
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
        for t in (2.6, 6.4, 7.6, 9.9, 13.2, 15.6, 18.0, 19.6, 22.0, 24.3, 28.5):
            frame(t).save(OUT / f"still_{t:05.1f}.jpg", quality=80)
        return
    audio = OUT / "mix.wav"
    mix(audio)
    video = OUT / "antares-motion-vertical.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", str(audio), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(video)],
                          stdin=subprocess.PIPE)
    for f in range(int(TOTAL * FPS)):
        ff.stdin.write(frame(f / FPS).tobytes())
    ff.stdin.close()
    ff.wait()
    print("ok", video)


if __name__ == "__main__":
    main()

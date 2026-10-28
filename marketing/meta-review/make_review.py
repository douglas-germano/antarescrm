"""Monta os screencasts da análise da Meta (um por permissão) a partir das gravações em raw/.

Recorta a página do Chrome, desfoca dados de terceiros, acelera esperas, adiciona narração (audio/*.mp3)
e legenda em inglês. Uso: python3 make_review.py [basic|messages|comments ...]
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
RAW, AUDIO, OUT, TMP = ROOT / "raw", ROOT / "audio", ROOT / "out", ROOT / "out" / "tmp"
TEXT = json.loads((ROOT / "narration.json").read_text())
W, H, PAGE_H = 1920, 1080, 940
PAGE_W = round(2916 * PAGE_H / 1476)
CROP = "crop=2916:1476:12:424"  # página do Chrome, sem barras do sistema/navegador
FONT = "/System/Library/Fonts/Avenir Next.ttc"

LIST_ALL = [(536, 380, 756, 1070)]           # lista da Caixa de entrada (x, y, w, h no recorte)
LIST_BELOW_FIRST = [(536, 516, 756, 934)]
IG_INBOX = [(132, 395, 798, 245), (132, 790, 798, 686)]
RUNS_CONTACTS = [(1400, 852, 420, 248)]

VIDEOS = {
    "basic": {
        "title": "instagram_business_basic",
        "subtitle": "Connect an Instagram professional account and show its profile in Antares CRM",
        "clips": [("basic", 0.5, 10, "b1", 1.0, []), ("basic", 10, 14, "b2", 1.0, []),
                  ("basic", 14, 38, "b3", 1.6, []), ("basic", 38, 58, "b4", 1.0, [])],
    },
    "messages": {
        "title": "instagram_business_manage_messages",
        "subtitle": "Receive Instagram direct messages in the Antares CRM inbox and reply to them",
        "clips": [("messages", 1.5, 11, "m1", 1.0, LIST_ALL), ("messages", 11, 24, "m2", 1.0, LIST_BELOW_FIRST),
                  ("messages", 24, 40, "m3", 1.0, LIST_BELOW_FIRST), ("messages", 55, 76, "m4", 1.5, IG_INBOX)],
    },
    "comments": {
        "title": "instagram_business_manage_comments",
        "subtitle": "Automatically reply to comments on the account's Instagram posts",
        "clips": [("comments", 2, 13, "c1", 1.0, []), ("comments", 13, 62, "c2", 2.4, []),
                  ("comments", 62, 74, "c3", 1.0, []), ("comments_b", 6, 22, "c4", 1.5, RUNS_CONTACTS),
                  ("comments_c", 3, 30, "c5", 1.0, [])],
    },
}


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out)


def wrap(draw, text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=font) > width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line]


def caption_png(text, path):
    im = Image.new("RGB", (W, H - PAGE_H), (14, 14, 16))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 32, index=5)
    lines = wrap(d, text, f, W - 160)
    y0 = (im.height - len(lines) * 42) / 2
    for i, ln in enumerate(lines):
        d.text((W / 2, y0 + i * 42 + 21), ln, font=f, fill=(255, 255, 255), anchor="mm")
    im.save(path)


def title_png(title, subtitle, path):
    im = Image.new("RGB", (W, H), (247, 247, 245))
    d = ImageDraw.Draw(im)
    mark = Image.open(ROOT.parent / "video-vox" / "brand" / "antares-mark.png").convert("RGBA").resize((150, 150))
    im.paste(mark, (W // 2 - 75, 300), mark)
    d.text((W / 2, 540), "Antares CRM — Instagram App Review", font=ImageFont.truetype(FONT, 44, index=2), fill=(17, 17, 17), anchor="mm")
    d.text((W / 2, 625), title, font=ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 52), fill=(230, 0, 0), anchor="mm")
    d.text((W / 2, 705), subtitle, font=ImageFont.truetype(FONT, 34, index=5), fill=(90, 90, 90), anchor="mm")
    d.text((W / 2, 1010), "Recorded on the production app: antares.douglasgermano.com", font=ImageFont.truetype(FONT, 26, index=5),
           fill=(130, 130, 130), anchor="mm")
    im.save(path)


def blur_chain(boxes):
    """Desfoque em regiões do recorte: split → crop → boxblur → overlay."""
    if not boxes:
        return "[c]copy[b]"
    parts = [f"[c]split={len(boxes) + 1}[base]" + "".join(f"[s{i}]" for i in range(len(boxes)))]
    cur = "base"
    for i, (x, y, w, h) in enumerate(boxes):
        parts.append(f"[s{i}]crop={w}:{h}:{x}:{y},boxblur=28:3[k{i}]")
        nxt = "b" if i == len(boxes) - 1 else f"o{i}"
        parts.append(f"[{cur}][k{i}]overlay={x}:{y}[{nxt}]")
        cur = nxt
    return ";".join(parts)


def make_clip(idx, src, start, end, key, speed, boxes, name):
    vo = AUDIO / f"{key}.mp3"
    vlen = (end - start) / speed
    total = max(vlen, duration(vo) + 0.9)
    cap = TMP / f"{name}_{idx}_cap.png"
    caption_png(TEXT[key], cap)
    out = TMP / f"{name}_{idx}.mp4"
    fc = (f"[0:v]trim={start}:{end},setpts=(PTS-STARTPTS)/{speed},fps=30,{CROP}[c];{blur_chain(boxes)};"
          f"[b]scale={PAGE_W}:{PAGE_H}:flags=lanczos,pad={W}:{H}:{(W - PAGE_W) // 2}:0:black[p];"
          f"[p][1:v]overlay=0:{PAGE_H},tpad=stop_mode=clone:stop_duration={total - vlen + 0.1:.2f},trim=0:{total:.2f},format=yuv420p[v];"
          f"[2:a]aresample=48000,adelay=300|300,apad,atrim=0:{total:.2f}[a]")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(RAW / f"{src}.mov"), "-i", str(cap), "-i", str(vo),
         "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(out)])
    return out


def make_title(name, spec):
    png = TMP / f"{name}_title.png"
    title_png(spec["title"], spec["subtitle"], png)
    out = TMP / f"{name}_0.mp4"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-t", "3", "-i", str(png), "-f", "lavfi", "-t", "3",
         "-i", "anullsrc=r=48000:cl=stereo", "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)])
    return out


def build(name):
    spec = VIDEOS[name]
    TMP.mkdir(parents=True, exist_ok=True)
    parts = [make_title(name, spec)]
    for i, clip in enumerate(spec["clips"], 1):
        parts.append(make_clip(i, *clip, name))
    listing = TMP / f"{name}_list.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    out = OUT / f"antares-{spec['title']}.mp4"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    print("ok", out, round(duration(out), 1), "s")


if __name__ == "__main__":
    for n in sys.argv[1:] or list(VIDEOS):
        build(n)

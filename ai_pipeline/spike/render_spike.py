"""Phase 0.5 spike B — رندر حقيقي من عقود مكتوبة بالإيد.

بيجاوب على:
  R2  هل الفهرسة بالإطار بتعطي تزامنًا تامًّا؟   (عدّ إطارات + موقع النقرات)
  R6  هل النص بيختفي على لقطة فاتحة؟             (تباين مقيس + scrim)
  R11 هل الانتقال بيسرق مدة؟                     (قطع حادّ مقابل xfade)
  R5  هل exit-code 0 كافٍ؟                        (فحص المخرَج نفسه)
هالكود بينتشال بعد ما نطلّع النتائج. مش تصميمًا، تحقيقًا.
"""
import json, subprocess, sys, math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np, imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = Path("spike/out"); SRC = ROOT/"src"; TYPO = ROOT/"typo"
W, H, FPS, SR = 1080, 1920, 30, 48000
SPF = SR // FPS                      # 1600 عيّنة/إطار — عدد صحيح
assert SR % FPS == 0, "sr/fps لازم يكون صحيحًا"

FONT_P = "assets/fonts/AmiriQuran-Regular.ttf"
FSIZE  = 64
TEXT_RGB = (243, 229, 171)
BOX_X, BOX_Y, BOX_W = 80, 1180, 920

# ── العقود (مكتوبة بالإيد — هاد المقصود بالـspike) ────────────────────
SEGMENTS = [
    {"id": 1, "start": 0.82, "end": 3.41, "text": "الٓمٓ ۚ ذَٰلِكَ ٱلْكِتَٰبُ لَا رَيْبَ"},
    {"id": 2, "start": 3.41, "end": 5.90, "text": "فِيهِ هُدًى لِّلْمُتَّقِينَ"},
    {"id": 3, "start": 5.90, "end": 8.20, "text": "ٱلَّذِينَ يُؤْمِنُونَ بِٱلْغَيْبِ"},
]
ASSETS = {1: ("a1.mp4", 0.0), 2: ("a2.mp4", 1.0), 3: ("a3.mp4", 2.0)}
AUDIO_DUR = 9.0

# ── quantize ──────────────────────────────────────────────────────────
total_frames = round(AUDIO_DUR * FPS)
text_spans, cuts = [], [0]
for s in SEGMENTS:
    text_spans.append((s["id"], round(s["start"]*FPS), round(s["end"]*FPS)))
for i, s in enumerate(SEGMENTS[1:], 1):
    cuts.append(round(s["start"]*FPS))
cuts.append(total_frames)
vis_spans = [(SEGMENTS[i]["id"], cuts[i], cuts[i+1]) for i in range(len(SEGMENTS))]
print("total_frames :", total_frames)
print("visual spans :", vis_spans, " Σ =", sum(b-a for _,a,b in vis_spans))
print("text   spans :", text_spans)
assert sum(b-a for _,a,b in vis_spans) == total_frames

# ── تخطيط النص ────────────────────────────────────────────────────────
font = ImageFont.truetype(FONT_P, FSIZE)
def wrap(text, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur+" "+w).strip()
        if font.getlength(t) <= maxw or not cur: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def ink_box(lines):
    """صندوق الحبر الفعلي — مش من font metrics (شوف spike A)."""
    probe = Image.new("L", (maxw_px:=BOX_W+400, 900), 0)
    d = ImageDraw.Draw(probe); y = 300
    for ln in lines:
        d.text((maxw_px-40, y), ln, font=font, fill=255,
               direction="rtl", language="ar", anchor="rs")
        y += int(FSIZE*1.9)
    bb = probe.getbbox()
    return bb[3]-bb[1]

layouts = {s["id"]: wrap(s["text"], BOX_W-40) for s in SEGMENTS}
BOX_H = max(ink_box(l) for l in layouts.values()) + 48
print("box          :", BOX_W, "x", BOX_H, "(من الحبر الفعلي، مش من metrics)")

# ── R6: قياس تباين على الإطار اللي ffmpeg رح يسلّمه فعلًا ─────────────
def lum(rgb):
    def c(v):
        v = v/255
        return v/12.92 if v <= 0.03928 else ((v+0.055)/1.055)**2.4
    r,g,b = rgb
    return 0.2126*c(r)+0.7152*c(g)+0.0722*c(b)
def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la,lb), min(la,lb)
    return (hi+0.05)/(lo+0.05)

TYPO.mkdir(parents=True, exist_ok=True)
bg_mean, contrast = {}, {}
for sid,(f_,inp) in ASSETS.items():
    p = ROOT/f"probe_{sid}.png"
    subprocess.run([FF,"-y","-v","error","-ss",str(inp),"-i",str(SRC/f_),
        "-vf",f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
        "-frames:v","1",str(p)], check=True)
    im = np.asarray(Image.open(p).convert("RGB"))
    patch = im[BOX_Y:BOX_Y+BOX_H, BOX_X:BOX_X+BOX_W].reshape(-1,3).mean(0)
    bg_mean[sid] = tuple(int(v) for v in patch)
    contrast[sid] = ratio(TEXT_RGB, bg_mean[sid])
print("\nR6 — تباين النص على كل لقطة (WCAG):")
for sid in ASSETS:
    ok = contrast[sid] >= 4.5
    print(f"  segment {sid}: bg={bg_mean[sid]}  ratio={contrast[sid]:.2f}  {'✅' if ok else '❌ يلزمه scrim'}")

SCRIM_A = 165
def make_png(sid, scrim):
    im = Image.new("RGBA", (BOX_W, BOX_H), (0,0,0,0))
    d = ImageDraw.Draw(im)
    if scrim:
        d.rounded_rectangle([0,0,BOX_W-1,BOX_H-1], radius=22, fill=(8,8,10,SCRIM_A))
    y = 34 + FSIZE
    for ln in layouts[sid]:
        d.text((BOX_W-24, y), ln, font=font, fill=TEXT_RGB+(255,),
               direction="rtl", language="ar", anchor="rs")
        y += int(FSIZE*1.9)
    return im

# التباين بعد الـscrim (على المزيج الفعلي، مش على افتراض)
def blend(bg, a):
    return tuple(int(bg[i]*(1-a/255) + (8,8,10)[i]*(a/255)) for i in range(3))
print("\nR6 — بعد الـscrim:")
scrim_for = {}
for sid in ASSETS:
    need = contrast[sid] < 4.5
    scrim_for[sid] = need
    if need:
        after = ratio(TEXT_RGB, blend(bg_mean[sid], SCRIM_A))
        print(f"  segment {sid}: {contrast[sid]:.2f} -> {after:.2f}  {'✅' if after>=4.5 else '❌ لسا'}")

# ── تسلسل الصور: كل ملف بنفس المقاس بالضبط ────────────────────────────
blank = Image.new("RGBA", (BOX_W, BOX_H), (0,0,0,0))
cache = {sid: make_png(sid, scrim_for[sid]) for sid in ASSETS}
sizes = set()
for n in range(total_frames):
    img = blank
    for sid,a,b in text_spans:
        if a <= n < b: img = cache[sid]; break
    img.save(TYPO/f"{n:06d}.png")
    sizes.add(img.size)
assert len(sizes) == 1, f"مقاسات مختلفة بالتسلسل: {sizes}"
print(f"\nتسلسل الكابشن: {total_frames} ملف، مقاس واحد {sizes.pop()}")

# ── بناء الرسم — دالة نقية، ولا نداء ffmpeg ───────────────────────────
def build_graph(vis_spans, assets):
    parts, labels = [], []
    for i,(sid,a,b) in enumerate(vis_spans):
        n = b-a; inf = round(assets[sid][1]*FPS)
        parts.append(f"[{i}:v]fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H},trim=start_frame={inf}:end_frame={inf+n},"
                     f"setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
    parts.append("".join(labels)+f"concat=n={len(vis_spans)}:v=1:a=0[bg]")
    ti = len(vis_spans)
    parts.append(f"[bg][{ti}:v]overlay=x={BOX_X}:y={BOX_Y}:eof_action=pass[vout]")
    return ";".join(parts)

graph = build_graph(vis_spans, ASSETS)
inputs = []
for sid,_,_ in vis_spans: inputs += ["-i", str(SRC/ASSETS[sid][0])]
inputs += ["-framerate", str(FPS), "-i", str(TYPO/"%06d.png")]
inputs += ["-i", str(SRC/"voice.wav")]
ai = len(vis_spans)+1
out = ROOT/"final.mp4"
cmd = [FF,"-y","-v","error",*inputs,"-filter_complex",graph,
       "-map","[vout]","-map",f"{ai}:a",
       "-c:v","libx264","-pix_fmt","yuv420p","-crf","19","-preset","medium",
       "-r",str(FPS),"-c:a","aac","-b:a","192k","-ar",str(SR),
       "-frames:v",str(total_frames),str(out)]
(ROOT/"cmd.txt").write_text(" ".join(cmd))
print("\n[08] ffmpeg — تشغيلة واحدة ...")
r = subprocess.run(cmd, capture_output=True, text=True)
print("    exit", r.returncode, ("| stderr: "+r.stderr.strip()[:300]) if r.stderr.strip() else "")
if r.returncode: sys.exit("❌ ffmpeg فشل")
print("    حجم:", out.stat().st_size, "بايت")

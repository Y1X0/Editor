"""
التكامل النهائي للمرحلة ٠: الزوم لكل مقطع **مع** الكابشن والصوت
بنفس التشغيلة، وفحص الخمس ثوابت سوا.

  ١. عدد الإطارات = Σ frame_plan
  ٢. كل إطار مخرَج من إطار المصدر الصح (بلا إسقاط/تكرار)
  ٣. الزوم مطابق zoom_cycle بكل إطار، وبيتبدّل عند الحدّ بالضبط
  ٤. كل كابشن بيبلّش على إطاره المقصود
  ٥. الصوت بلا انزياح متراكم

usage: z7.py [K] [NCAP]
"""
import subprocess, os, re, sys, time, shutil, resource
sys.path.insert(0, "/tmp/realrun")
from z0 import PITCH, profile, fit_pitch, real_zoom
from z2 import read_barcode, SW, SH, BAND_X, BAND_Y, NBITS, CELL_W, CELL_H, _D
from det import peaks as click_peaks
from PIL import Image, ImageDraw

FPS, SR = 30, 48000
W, H = 540, 960
BIAS, PAN = 0.5, 26
CYCLE = [1.0, 1.1, 1.04, 1.14]
K = int(sys.argv[1]) if len(sys.argv) > 1 else 10
NCAP = int(sys.argv[2]) if len(sys.argv) > 2 else 60
WORK = f"/tmp/z7_{K}_{NCAP}"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)
SRC = "/tmp/realrun/grid3.mp4"      # باركود + نقرات
ENC = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '10', '-pix_fmt', 'yuv420p']


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def frames(p):
    f = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', p, '-f', 'null', '-'], text=True).stderr)
    return int(f[-1]) if f else None


if not os.path.exists(SRC):
    sh(['ffmpeg', '-y', '-v', 'error', '-framerate', str(FPS), '-start_number', '0',
        '-i', f'{_D}/%05d.png',
        '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', '/tmp/realrun/click.raw',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '10', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-ar', str(SR), '-shortest', SRC], check=False)

# ---- خطة قص: كل مقطع بيمسك نقرة (نقرة كل ٠.٥s بالمصدر)
SEGS = [(round(0.5 * (i + 1) - 0.12, 3), round(0.5 * (i + 1) + 0.28, 3)) for i in range(K)]
PLAN = [max(3, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)
OFF = [sum(PLAN[:i]) for i in range(K)]
ZOOM = [CYCLE[i % len(CYCLE)] for i in range(K)]
DXr = [max(0, int(W * ZOOM[i] / 2) * 2 - W) for i in range(K)]
DX = [max(-DXr[i] // 2, min(DXr[i] // 2, (1 if i % 2 == 0 else -1) * PAN)) for i in range(K)]
for i in range(K - 1):
    assert ST[i] + PLAN[i] <= ST[i + 1], "مدايات select متداخلة — التجربة غلط"

want_clicks, t = [], 0.0
for i in range(K):
    want_clicks.append(t + (0.5 * (i + 1) - ST[i] / FPS))
    t += PLAN[i] / FPS


def seg_of(n):
    for i in range(K):
        if OFF[i] <= n < OFF[i] + PLAN[i]:
            return i


# ---- كابشنات: ألوان فريدة، حدود بفهارس إطارات، تسلسل موصول بالإطار
bounds = sorted(set([round(i * TOTAL_F / NCAP) for i in range(NCAP)] + [TOTAL_F]))
NC = len(bounds) - 1
COLORS = [(40 + (i % 14) * 15, 40 + ((i // 14) % 14) * 15, 40 + ((i // 196) % 14) * 15)
          for i in range(NC)]
assert len(set(COLORS)) == NC
CW, CH = 180, 60
CX, CY = (W - CW) // 2, int(H * 0.80)
os.makedirs(f"{WORK}/png")
os.makedirs(f"{WORK}/seq")
for i in range(NC):
    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([0, 0, CW - 1, CH - 1], fill=COLORS[i] + (255,))
    img.save(f"{WORK}/png/{i:04d}.png")
    for n in range(bounds[i], bounds[i + 1]):
        os.symlink(f"{WORK}/png/{i:04d}.png", f"{WORK}/seq/{n:06d}.png")

# ---- الرسم
sws, shs, xs, ys = [], [], [], []
for i in range(K):
    z = ZOOM[i]
    sw, sh_ = int(W * z / 2) * 2, int(H * z / 2) * 2
    s = max(sw / SW, sh_ / SH)
    iw, ih = round(SW * s), round(SH * s)
    sws.append(sw); shs.append(sh_)
    xs.append(round((iw - W) / 2 + DX[i]))
    ys.append(round((ih - H) * BIAS))


def flat(c):
    return "+".join(
        f"{c[i]}*between(n\\,{OFF[i]}\\,"
        f"{(OFF[i]+PLAN[i]-1) if i < K-1 else 9999999})" for i in range(K))


SEL = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
parts = [f"[0:v]fps={FPS},select='{SEL}',settb=1/{FPS},setpts=N,fps={FPS}[base]",
         f"[base]scale=w='{flat(sws)}':h='{flat(shs)}':"
         f"force_original_aspect_ratio=increase:eval=frame,"
         f"crop={W}:{H}:x='{flat(xs)}':y='{flat(ys)}',setsar=1[zoomed]",
         f"[2:v]fps={FPS}[cap]",
         f"[zoomed][cap]overlay={CX}:{CY}:eof_action=pass[m0]",
         f"[0:a]aresample={SR},asplit={K}" + "".join(f"[d{i}]" for i in range(K))]
for i in range(K):
    parts.append(f"[d{i}]atrim=start={ST[i]/FPS:.9f}:end={(ST[i]+PLAN[i])/FPS:.9f},"
                 f"asetpts=PTS-STARTPTS[a{i}]")
parts.append("".join(f"[a{i}]" for i in range(K)) + f"concat=n={K}:v=0:a=1[ao]")
g = "; ".join(parts)
open(f"{WORK}/graph.txt", "w").write(g)

OUT = f"{WORK}/out.mp4"
t0 = time.time()
r = sh(['ffmpeg', '-y', '-v', 'error', '-i', SRC,
        '-f', 'lavfi', '-i', 'nullsrc=s=2x2:d=1',
        '-framerate', str(FPS), '-start_number', '0', '-i', f'{WORK}/seq/%06d.png',
        '-filter_complex_script', f"{WORK}/graph.txt",
        '-map', '[m0]', '-map', '[ao]', *ENC, '-c:a', 'aac', OUT], text=True)
dt = time.time() - t0
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
if r.returncode:
    print("❌ فشل:", r.stderr[-800:])
    raise SystemExit(1)

nf = frames(OUT)
print(f"K={K} كابشن={NC} · {dt:.1f}s · ذروة {pk:.0f} MiB · رسم={len(g)} محرف")
print(f"  ١) إطارات: {nf}/{TOTAL_F} " + ("✅" if nf == TOTAL_F else "❌"))

fd = f"{WORK}/fr"
os.makedirs(fd)
sh(['ffmpeg', '-y', '-v', 'error', '-i', OUT, '-fps_mode', 'passthrough', f'{fd}/%05d.png'])
files = sorted(os.listdir(fd))
assert len(files) == TOTAL_F, f"الاستخراج {len(files)} والمخطط {TOTAL_F}"

bad_src, bad_zoom, zs, srcs, capobs = [], [], [], [], []
for n, f in enumerate(files):
    img = Image.open(f"{fd}/{f}").convert("RGB")
    i = seg_of(n)
    zr = real_zoom(ZOOM[i], W, H, SW, SH)
    b = read_barcode(img, zr, pan_out=DX[i], bias=BIAS)
    srcs.append(b)
    if b != ST[i] + (n - OFF[i]):
        bad_src.append((n, ST[i] + (n - OFF[i]), b))
    z = fit_pitch(profile(img), PITCH * 0.85, PITCH * 1.45) / PITCH
    zs.append(z)
    if abs(z - zr) > 0.006:
        bad_zoom.append((n, zr, round(z, 4)))
    c = img.getpixel((CX + CW // 2, CY + CH // 2))
    capobs.append(min(range(NC), key=lambda j: sum((a - b2) ** 2
                                                   for a, b2 in zip(c, COLORS[j]))))

print(f"  ٢) إطار المصدر الصح: {TOTAL_F-len(bad_src)}/{TOTAL_F} "
      + ("✅" if not bad_src else f"❌ {bad_src[:4]}")
      + f" · مكرر={len(srcs)-len(set(x for x in srcs if x is not None))}")
print(f"  ٣) الزوم مطابق: {TOTAL_F-len(bad_zoom)}/{TOTAL_F} "
      + ("✅" if not bad_zoom else f"❌ {bad_zoom[:4]}"))
edge = [i for i in range(K - 1)
        if abs(zs[OFF[i] + PLAN[i] - 1] - real_zoom(ZOOM[i], W, H, SW, SH)) > 0.006
        or abs(zs[OFF[i + 1]] - real_zoom(ZOOM[i + 1], W, H, SW, SH)) > 0.006]
print(f"     الحدود: {K-1-len(edge)}/{K-1} " + ("✅" if not edge else f"❌ {edge[:3]}"))
first = {}
for n, c in enumerate(capobs):
    first.setdefault(c, n)
badcap = [i for i in range(NC) if first.get(i) != bounds[i]]
print(f"  ٤) الكابشن على إطاره: {NC-len(badcap)}/{NC} "
      + ("✅" if not badcap else f"❌ {badcap[:5]}"))
got = click_peaks(OUT)
m = min(len(got), len(want_clicks))
e = [(got[i] - want_clicks[i]) * 1000 for i in range(m)]
print(f"  ٥) الصوت: {len(got)}/{len(want_clicks)} نقرة · أقصى={max(abs(x) for x in e):.2f}ms"
      f" · تراكم={e[-1]-e[0]:+.2f}ms "
      + ("✅" if len(got) == len(want_clicks) and max(abs(x) for x in e) <= 5 else "❌"))

"""
التكامل: المسار المقترح كامل بتشغيلة ffmpeg وحدة، وقياس الثلاث ثوابت سوا:

  ١. عدد الإطارات = خطة الإطارات بالضبط (لكل مقاس)
  ٢. الصوت بلا انزياح متراكم
  ٣. كل كابشن بيبلّش على إطاره المقصود بالضبط

المصدر بيحمل الاتنين: نقرات صوتية بأزمنة معروفة، وصورة رمادية عشان
لون الكابشن يكون الشي الوحيد بالإطار.

usage: e16.py [K] [NCAP]
"""
import subprocess, os, re, sys, time, shutil, resource
sys.path.insert(0, "/tmp/realrun")
from det import peaks as click_peaks
from PIL import Image, ImageDraw

FPS, SR = 30, 48000
SIZES = [("reel", 1080, 1920), ("square", 1080, 1080),
         ("wide", 1920, 1080), ("story", 720, 1280)]
K = int(sys.argv[1]) if len(sys.argv) > 1 else 30
NCAP = int(sys.argv[2]) if len(sys.argv) > 2 else 120
WORK = f"/tmp/e16_{K}_{NCAP}"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def frames(p):
    f = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', p, '-f', 'null', '-'], text=True).stderr)
    return int(f[-1]) if f else None


# ---------- مصدر: رمادي + نقرات كل ٠.٥s
SRC = f"{WORK}/src.mp4"
sh(['ffmpeg', '-y', '-v', 'error',
    '-f', 'lavfi', '-i', 'color=c=gray:s=640x1138:r=30:d=40',
    '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', '/tmp/realrun/click.raw',
    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-ar', str(SR), '-shortest', SRC], check=False)

SEGS = [(round(0.5 * i - 0.12, 3), round(0.5 * i + 0.28, 3)) for i in range(1, K + 1)]
PLAN = [max(1, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)

want, t = [], 0.0
for idx, i in enumerate(range(1, K + 1)):
    want.append(t + (0.5 * i - ST[idx] / FPS))
    t += PLAN[idx] / FPS

# ---------- الكابشنات: حدود بفهارس إطارات، ألوان فريدة
bounds, step = [0], TOTAL_F / NCAP
for i in range(1, NCAP):
    bounds.append(min(TOTAL_F - 1, round(i * step) + (1 if i % 3 == 0 else 0)))
bounds.append(TOTAL_F)
bounds = sorted(set(bounds))
NC = len(bounds) - 1
COLORS = [(40 + (i % 14) * 15, 40 + ((i // 14) % 14) * 15, 40 + ((i // 196) % 14) * 15)
          for i in range(NC)]
assert len(set(COLORS)) == NC

POS = {}
for name, W, H in SIZES:
    os.makedirs(f"{WORK}/png_{name}")
    os.makedirs(f"{WORK}/seq_{name}")
    cw, ch = int(W * 0.5), int(W * 0.10)
    POS[name] = ((W - cw) // 2, int(H * 0.72) - ch // 2, cw, ch)
    for i in range(NC):
        img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle([0, 0, cw - 1, ch - 1], fill=COLORS[i] + (255,))
        img.save(f"{WORK}/png_{name}/{i:04d}.png")
    for i in range(NC):
        s = f"{WORK}/png_{name}/{i:04d}.png"
        for n in range(bounds[i], bounds[i + 1]):
            os.symlink(s, f"{WORK}/seq_{name}/{n:06d}.png")

# ---------- الرسم
vsel = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
parts = [f"[0:v]fps={FPS},select='{vsel}',setpts=N/{FPS}/TB,fps={FPS},"
         f"split={len(SIZES)}" + "".join(f"[z{n}]" for n in range(len(SIZES)))]
parts.append(f"[0:a]aresample={SR},asplit={K}" + "".join(f"[d{i}]" for i in range(K)))
for i in range(K):
    parts.append(f"[d{i}]atrim=start={ST[i]/FPS:.9f}:end={(ST[i]+PLAN[i])/FPS:.9f},"
                 f"asetpts=PTS-STARTPTS[a{i}]")
parts.append("".join(f"[a{i}]" for i in range(K)) + f"concat=n={K}:v=0:a=1[acat]")
parts.append(f"[acat]asplit={len(SIZES)}" + "".join(f"[ao{n}]" for n in range(len(SIZES))))

inputs = ['-i', SRC]
for n, (name, W, H) in enumerate(SIZES):
    inputs += ['-framerate', str(FPS), '-start_number', '0',
               '-i', f'{WORK}/seq_{name}/%06d.png']
    x, y, cw, ch = POS[name]
    parts.append(f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,"
                 f"crop={W}:{H}[g{n}]")
    parts.append(f"[g{n}][{n+1}:v]overlay={x}:{y}:eof_action=pass[m{n}]")

g = "; ".join(parts)
out = f"{WORK}/out"
os.makedirs(out)
args = ['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', g]
for n, (name, W, H) in enumerate(SIZES):
    args += ['-map', f'[m{n}]', '-map', f'[ao{n}]', '-c:v', 'libx264',
             '-preset', 'ultrafast', '-qp', '0', '-pix_fmt', 'yuv444p',
             '-c:a', 'aac', f'{out}/{name}.mp4']

t0 = time.time()
r = sh(args, text=True)
dt = time.time() - t0
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
print(f"مقاطع={K} كابشن={NC} إطارات={TOTAL_F} · {dt:.1f}s · ذروة {pk:.0f} MiB · "
      f"مدخلات={len([x for x in args if x=='-i'])} · رسم={len(g)} محرف · rc={r.returncode}")
if r.returncode:
    print("خطأ:", r.stderr[-600:])
    raise SystemExit(1)

# ---- ثابت ١: عدد الإطارات
fr = {name: frames(f"{out}/{name}.mp4") for name, _, _ in SIZES}
print(f"١) إطارات: {fr}  " + ("✅" if all(v == TOTAL_F for v in fr.values()) else "❌"))

# ---- ثابت ٢: الصوت
got = click_peaks(f"{out}/reel.mp4")
m = min(len(got), len(want))
e = [(got[i] - want[i]) * 1000 for i in range(m)]
print(f"٢) الصوت: {len(got)}/{len(want)} نقرة · أقصى={max(abs(x) for x in e):.2f}ms · "
      f"تراكم={e[-1]-e[0]:+.2f}ms  " +
      ("✅" if max(abs(x) for x in e) <= 5 and len(got) == len(want) else "❌"))

# ---- ثابت ٣: الكابشن على إطاره
os.makedirs(f"{WORK}/fr")
sh(['ffmpeg', '-y', '-v', 'error', '-i', f"{out}/reel.mp4", f'{WORK}/fr/%06d.png'])
x, y, cw, ch = POS["reel"]


def near(c):
    return min(range(NC), key=lambda i: sum((a - b) ** 2 for a, b in zip(c, COLORS[i])))


fs = sorted(os.listdir(f"{WORK}/fr"))
obs = [near(Image.open(f"{WORK}/fr/{f}").convert("RGB").getpixel((x + cw // 2, y + ch // 2)))
       for f in fs]
first = {}
for n, c in enumerate(obs):
    first.setdefault(c, n)
bad = [i for i in range(NC) if first.get(i) != bounds[i]]
print(f"٣) الكابشن: {NC - len(bad)}/{NC} على إطاره  " +
      ("✅" if not bad else f"❌ {bad[:6]}"))

"""
٢ GB لسا كتير لتيرمكس. الشكّ على `split=K`: كل فرع بيستهلك من مكان
مختلف بالخط الزمني، فالفلتر مجبور يخزّن كل المدى بين أول مستهلك وآخره
— يعني عمليًا **الفيديو كله** بالذاكرة.

البديل: بلا split وبلا trim. فلتر `select` بتعبير بيغطي كل المدايات
المحفوظة، وsetpts=N/FPS/TB بيعيد الترقيم على شبكة الإطارات.
ذاكرته O(1): إطار واحد بالمرة.

  ٤) select + setpts=N/FPS/TB   ·   aselect + asetpts=N/SR/TB
  ٥) نفسها مع مسار كابشن concat demuxer وoverlay واحد لكل مقاس
"""
import subprocess, os, re, sys, time, shutil, resource
sys.path.insert(0, "/tmp/realrun")
from det import peaks as click_peaks
from PIL import Image, ImageDraw

FPS, SR = 30, 48000
SRC = "/tmp/realrun/click.mp4"
SIZES = {"reel": (1080, 1920), "square": (1080, 1080),
         "wide": (1920, 1080), "story": (720, 1280)}
NCAP = 40
VARIANT = sys.argv[1]
WORK = f"/tmp/e10_{VARIANT}"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def frames(p):
    f = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', p, '-f', 'null', '-'], text=True).stderr)
    return int(f[-1]) if f else None


K = 30
SEGS = [(round(0.5 * i - 0.12, 3), round(0.5 * i + 0.28, 3)) for i in range(1, K + 1)]
PLAN = [max(1, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)
DUR = TOTAL_F / FPS

want, t = [], 0.0
for idx, i in enumerate(range(1, K + 1)):
    want.append(t + (0.5 * i - ST[idx] / FPS))
    t += PLAN[idx] / FPS

bounds = [round(i * TOTAL_F / NCAP) for i in range(NCAP + 1)]
CAPS = {}
for name, (W, H) in SIZES.items():
    d = f"{WORK}/cap_{name}"
    os.makedirs(d)
    it = []
    for i in range(NCAP):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle(
            [W // 8, int(H * 0.70), W - W // 8, int(H * 0.78)], fill=(255, 255, 255, 200))
        p = f"{d}/{i:04d}.png"
        img.save(p)
        it.append((p, bounds[i], bounds[i + 1]))
    CAPS[name] = it

# ---- الجذع: select على شبكة الإطارات
vsel = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
asel = "+".join(f"between(t,{ST[i]/FPS:.9f},{(ST[i]+PLAN[i])/FPS:.9f})" for i in range(K))
stem = [f"[0:v]fps={FPS},select='{vsel}',setpts=N/{FPS}/TB,split={len(SIZES)}"
        + "".join(f"[z{n}]" for n in range(len(SIZES))),
        f"[0:a]aselect='{asel}',asetpts=N/SR/TB,asplit={len(SIZES)}"
        + "".join(f"[ao{n}]" for n in range(len(SIZES)))]

out = f"{WORK}/out"
os.makedirs(out)
t0 = time.time()

if VARIANT == "4":       # بلا كابشن — نقيس الجذع لحاله
    parts = list(stem)
    args = ['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-filter_complex', "; ".join(parts)]
    for n, (name, (W, H)) in enumerate(SIZES.items()):
        parts_extra = f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[g{n}]"
        parts.append(parts_extra)
    args[-1] = "; ".join(parts)
    for n, name in enumerate(SIZES):
        args += ['-map', f'[g{n}]', '-map', f'[ao{n}]', '-c:v', 'libx264',
                 '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                 f'{out}/{name}.mp4']
    r = sh(args, text=True)

elif VARIANT == "5":     # + مسار كابشن concat demuxer، overlay واحد لكل مقاس
    inputs = ['-i', SRC]
    for name in SIZES:
        lst = f"{WORK}/cap_{name}.txt"
        with open(lst, "w") as fh:
            for p, a, b in CAPS[name]:
                fh.write(f"file '{p}'\nduration {(b - a) / FPS:.9f}\n")
            fh.write(f"file '{CAPS[name][-1][0]}'\n")
        inputs += ['-f', 'concat', '-safe', '0', '-i', lst]
    parts = list(stem)
    for n, (name, (W, H)) in enumerate(SIZES.items()):
        parts.append(f"[{n+1}:v]fps={FPS}[cap{n}]")
        parts.append(f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H}[g{n}]")
        parts.append(f"[g{n}][cap{n}]overlay=0:0:eof_action=pass[m{n}]")
    args = ['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', "; ".join(parts)]
    for n, name in enumerate(SIZES):
        args += ['-map', f'[m{n}]', '-map', f'[ao{n}]', '-c:v', 'libx264',
                 '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                 f'{out}/{name}.mp4']
    r = sh(args, text=True)

dt = time.time() - t0
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
print(f"صياغة {VARIANT}: {dt:6.1f}s · ذروة ذاكرة {pk:8.1f} MiB · rc={r.returncode}")
if r.returncode:
    print("   خطأ:", (r.stderr or "")[-600:])
for name in SIZES:
    p = f"{out}/{name}.mp4"
    print(f"   {name:7s} -> {frames(p) if os.path.exists(p) else 'مفقود'} إطار "
          f"(المخطط {TOTAL_F})")
p = f"{out}/reel.mp4"
if os.path.exists(p):
    got = click_peaks(p)
    n = min(len(got), len(want))
    if n:
        e = [(got[i] - want[i]) * 1000 for i in range(n)]
        print(f"   الصوت: {len(got)}/{len(want)} نقرة · أول={e[0]:+.2f}ms "
              f"آخر={e[-1]:+.2f}ms أقصى={max(abs(x) for x in e):.2f}ms")

"""
الصياغة النهائية المرشّحة + تصحيحين من e10:

  ١. `setpts` بيمسح معدّل الإطارات (مبرهن بـe4) -> لازم `fps` **بعده**،
     مش قبله بس. بدونها cfr بيعيد التشكيل لـ25 و٣٦٠ بتصير ٣٠١.
  ٢. الكابشن بالإنتاج PNG **بحجم الكابشن** مش بحجم الإطار. تجربتي
     السابقة استعملت PNG بحجم الإطار فنفخت الذاكرة.

usage: e11.py <ncap> <variant>
   variant=demux : مسار كابشن واحد لكل مقاس (concat demuxer) + overlay واحد
   variant=chain : N overlay متسلسلة، PNG بمدخل مستقل بلا loop
"""
import subprocess, os, re, sys, time, shutil, resource
sys.path.insert(0, "/tmp/realrun")
from det import peaks as click_peaks
from PIL import Image, ImageDraw

FPS, SR = 30, 48000
SRC = "/tmp/realrun/click.mp4"
SIZES = {"reel": (1080, 1920), "square": (1080, 1080),
         "wide": (1920, 1080), "story": (720, 1280)}
NCAP = int(sys.argv[1])
VARIANT = sys.argv[2]
WORK = f"/tmp/e11_{VARIANT}_{NCAP}"
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

want, t = [], 0.0
for idx, i in enumerate(range(1, K + 1)):
    want.append(t + (0.5 * i - ST[idx] / FPS))
    t += PLAN[idx] / FPS

# كابشن بحجم الكابشن (زي الإنتاج): ~٨٠٪ عرض × ١٦٠px لكل ١٠٨٠ عرض
bounds = [round(i * TOTAL_F / NCAP) for i in range(NCAP + 1)]
CAPS, POS = {}, {}
for name, (W, H) in SIZES.items():
    d = f"{WORK}/cap_{name}"
    os.makedirs(d)
    cw, ch = int(W * 0.82), int(W * 0.15)
    POS[name] = ((W - cw) // 2, int(H * 0.72) - ch // 2)
    it = []
    for i in range(NCAP):
        img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=ch // 3,
                                              fill=(0, 0, 0, 160))
        ImageDraw.Draw(img).rectangle([20, ch // 3, cw - 20, 2 * ch // 3],
                                      fill=(255, 255, 255, 230))
        p = f"{d}/{i:04d}.png"
        img.save(p)
        it.append((p, bounds[i], bounds[i + 1]))
    CAPS[name] = it

vsel = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
asel = "+".join(f"between(t,{ST[i]/FPS:.9f},{(ST[i]+PLAN[i])/FPS:.9f})" for i in range(K))
# التصحيح: fps **بعد** setpts
stem = [f"[0:v]fps={FPS},select='{vsel}',setpts=N/{FPS}/TB,fps={FPS},split={len(SIZES)}"
        + "".join(f"[z{n}]" for n in range(len(SIZES))),
        f"[0:a]aselect='{asel}',asetpts=N/SR/TB,asplit={len(SIZES)}"
        + "".join(f"[ao{n}]" for n in range(len(SIZES)))]

out = f"{WORK}/out"
os.makedirs(out)
parts = list(stem)
inputs = ['-i', SRC]

if VARIANT == "demux":
    for name in SIZES:
        lst = f"{WORK}/cap_{name}.txt"
        with open(lst, "w") as fh:
            for p, a, b in CAPS[name]:
                fh.write(f"file '{p}'\nduration {(b - a) / FPS:.9f}\n")
            fh.write(f"file '{CAPS[name][-1][0]}'\n")
        inputs += ['-f', 'concat', '-safe', '0', '-i', lst]
    for n, (name, (W, H)) in enumerate(SIZES.items()):
        x, y = POS[name]
        parts.append(f"[{n+1}:v]fps={FPS}[cap{n}]")
        parts.append(f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H}[g{n}]")
        parts.append(f"[g{n}][cap{n}]overlay={x}:{y}:eof_action=pass[m{n}]")
else:                                   # chain
    ix, k = {}, 1
    for name in SIZES:
        for p, a, b in CAPS[name]:
            inputs += ['-i', p]
            ix[p] = k
            k += 1
    for n, (name, (W, H)) in enumerate(SIZES.items()):
        x, y = POS[name]
        parts.append(f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H}[g{n}]")
        last = f"[g{n}]"
        for j, (p, a, b) in enumerate(CAPS[name]):
            nxt = f"[q{n}_{j}]"
            parts.append(f"{last}[{ix[p]}:v]overlay={x}:{y}:eof_action=pass:"
                         f"enable='between(n,{a},{b-1})'{nxt}")
            last = nxt
        parts.append(f"{last}null[m{n}]")

g = "; ".join(parts)
open(f"{WORK}/graph.txt", "w").write(g)
args = ['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', g]
for n, name in enumerate(SIZES):
    args += ['-map', f'[m{n}]', '-map', f'[ao{n}]', '-c:v', 'libx264',
             '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
             f'{out}/{name}.mp4']

t0 = time.time()
r = sh(args, text=True)
dt = time.time() - t0
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
nin = len([x for x in args if x == '-i'])
print(f"{VARIANT:6s} ncap={NCAP:4d}: {dt:6.1f}s · ذروة {pk:8.1f} MiB · "
      f"مدخلات={nin} · رسم={len(g)} محرف · rc={r.returncode}")
if r.returncode:
    print("   خطأ:", (r.stderr or "")[-500:])
bad = [name for name in SIZES
       if not os.path.exists(f"{out}/{name}.mp4") or frames(f"{out}/{name}.mp4") != TOTAL_F]
print(f"   إطارات: " + " ".join(
    f"{name}={frames(f'{out}/{name}.mp4') if os.path.exists(f'{out}/{name}.mp4') else '-'}"
    for name in SIZES) + f"  (المخطط {TOTAL_F})" + ("  ❌" if bad else "  ✅"))
p = f"{out}/reel.mp4"
if os.path.exists(p):
    got = click_peaks(p)
    n = min(len(got), len(want))
    if n:
        e = [(got[i] - want[i]) * 1000 for i in range(n)]
        print(f"   الصوت: {len(got)}/{len(want)} نقرة · أول={e[0]:+.2f}ms "
              f"آخر={e[-1]:+.2f}ms أقصى={max(abs(x) for x in e):.2f}ms")

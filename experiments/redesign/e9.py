"""
الرسم الواحد الساذج انقتل (OOM، ذروة 13.5 GiB): كل `-loop 1 -t DUR`
بيولّد تيار كامل بطول المخرَج لكل PNG، و١٦٠ منها = عشرات آلاف الإطارات
بالذاكرة.

٣ صياغات أرخص:
  ١) بلا loop: كل PNG إطار واحد، وoverlay بيكرّر آخر إطار (repeatlast)
  ٢) مسار كابشن واحد لكل مقاس: concat للصور بمدّة كل وحدة -> overlay واحد
  ٣) نفس ٢ بس الصور بتتحمّل كتيار concat demuxer بدل ١٦٠ مدخل

كل صياغة بتنشغّل بعملية لحالها عشان قياس الذاكرة ما يتلوّث.
"""
import subprocess, os, re, sys, time, shutil, resource
from PIL import Image, ImageDraw

FPS = 30
SRC = "/tmp/realrun/click.mp4"
SIZES = {"reel": (1080, 1920), "square": (1080, 1080),
         "wide": (1920, 1080), "story": (720, 1280)}
NCAP = 40
VARIANT = sys.argv[1]
WORK = f"/tmp/e9_{VARIANT}"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def peak():
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024


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

# الكابشنات: كل واحد بياخد شريحة متساوية، وحدودها على شبكة الإطارات
bounds = [round(i * TOTAL_F / NCAP) for i in range(NCAP + 1)]
CAPS = {}
for name, (W, H) in SIZES.items():
    d = f"{WORK}/cap_{name}"
    os.makedirs(d)
    items = []
    for i in range(NCAP):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle(
            [W // 8, int(H * 0.70), W - W // 8, int(H * 0.78)], fill=(255, 255, 255, 200))
        p = f"{d}/{i:04d}.png"
        img.save(p)
        items.append((p, bounds[i], bounds[i + 1]))   # حدود بالإطارات
    CAPS[name] = items

# ---- الجذع المشترك: fps -> split -> trim -> concat  (مبرهن بـe3)
def stem():
    vp = [f"[0:v]fps={FPS}[src]",
          f"[src]split={K}" + "".join(f"[c{i}]" for i in range(K))]
    ap = [f"[0:a]asplit={K}" + "".join(f"[d{i}]" for i in range(K))]
    for i in range(K):
        s = ST[i]
        vp.append(f"[c{i}]trim=start_frame={s}:end_frame={s+PLAN[i]},setpts=PTS-STARTPTS[v{i}]")
        ap.append(f"[d{i}]atrim=start={s/FPS:.9f}:end={(s+PLAN[i])/FPS:.9f},"
                  f"asetpts=PTS-STARTPTS[a{i}]")
    parts = vp + ap
    parts.append("".join(f"[v{i}][a{i}]" for i in range(K)) +
                 f"concat=n={K}:v=1:a=1[vcat][ao]")
    parts.append(f"[vcat]fps={FPS},split={len(SIZES)}" +
                 "".join(f"[z{n}]" for n in range(len(SIZES))))
    parts.append(f"[ao]asplit={len(SIZES)}" + "".join(f"[ao{n}]" for n in range(len(SIZES))))
    return parts


out = f"{WORK}/out"
os.makedirs(out)
t0 = time.time()

if VARIANT == "1":
    # PNG بلا loop: إطار واحد لكل مدخل، overlay بيكرّره
    inputs, ix, k = ['-i', SRC], {}, 1
    for name in SIZES:
        for p, a, b in CAPS[name]:
            inputs += ['-i', p]
            ix[p] = k
            k += 1
    parts = stem()
    maps = []
    for n, (name, (W, H)) in enumerate(SIZES.items()):
        parts.append(f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[g{n}]")
        last = f"[g{n}]"
        for j, (p, a, b) in enumerate(CAPS[name]):
            nxt = f"[q{n}_{j}]"
            parts.append(f"{last}[{ix[p]}:v]overlay=0:0:eof_action=pass:"
                         f"enable='between(n,{a},{b-1})'{nxt}")
            last = nxt
        maps.append(last)
    args = ['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', "; ".join(parts)]
    for n, (name, lab) in enumerate(zip(SIZES, maps)):
        args += ['-map', lab, '-map', f'[ao{n}]', '-c:v', 'libx264', '-preset', 'ultrafast',
                 '-pix_fmt', 'yuv420p', '-c:a', 'aac', f'{out}/{name}.mp4']
    r = sh(args, text=True)

elif VARIANT == "2":
    # مسار كابشن واحد لكل مقاس: كل PNG بيمتد مدّته هو بس، ثم concat، ثم overlay واحد
    inputs, ix, k = ['-i', SRC], {}, 1
    for name in SIZES:
        for p, a, b in CAPS[name]:
            inputs += ['-loop', '1', '-framerate', str(FPS), '-t',
                       f'{(b - a) / FPS:.9f}', '-i', p]
            ix[p] = k
            k += 1
    parts = stem()
    maps = []
    for n, (name, (W, H)) in enumerate(SIZES.items()):
        chain = "".join(f"[{ix[p]}:v]" for p, a, b in CAPS[name])
        parts.append(f"{chain}concat=n={NCAP}:v=1:a=0,fps={FPS}[cap{n}]")
        parts.append(f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[g{n}]")
        parts.append(f"[g{n}][cap{n}]overlay=0:0:eof_action=pass[m{n}]")
        maps.append(f"[m{n}]")
    args = ['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', "; ".join(parts)]
    for n, (name, lab) in enumerate(zip(SIZES, maps)):
        args += ['-map', lab, '-map', f'[ao{n}]', '-c:v', 'libx264', '-preset', 'ultrafast',
                 '-pix_fmt', 'yuv420p', '-c:a', 'aac', f'{out}/{name}.mp4']
    r = sh(args, text=True)

elif VARIANT == "3":
    # مسار كابشن جاهز مسبقًا: concat demuxer على الصور (مدخل واحد لكل مقاس)
    inputs = ['-i', SRC]
    for n, name in enumerate(SIZES):
        lst = f"{WORK}/cap_{name}.txt"
        with open(lst, "w") as fh:
            for p, a, b in CAPS[name]:
                fh.write(f"file '{p}'\nduration {(b - a) / FPS:.9f}\n")
            fh.write(f"file '{CAPS[name][-1][0]}'\n")   # concat demuxer بده تكرار الأخير
        inputs += ['-f', 'concat', '-safe', '0', '-i', lst]
    parts = stem()
    maps = []
    for n, (name, (W, H)) in enumerate(SIZES.items()):
        parts.append(f"[{n+1}:v]fps={FPS}[cap{n}]")
        parts.append(f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[g{n}]")
        parts.append(f"[g{n}][cap{n}]overlay=0:0:eof_action=pass[m{n}]")
        maps.append(f"[m{n}]")
    args = ['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', "; ".join(parts)]
    for n, (name, lab) in enumerate(zip(SIZES, maps)):
        args += ['-map', lab, '-map', f'[ao{n}]', '-c:v', 'libx264', '-preset', 'ultrafast',
                 '-pix_fmt', 'yuv420p', '-c:a', 'aac', f'{out}/{name}.mp4']
    r = sh(args, text=True)

dt = time.time() - t0
pk = peak()
print(f"صياغة {VARIANT}: {dt:6.1f}s · ذروة ذاكرة {pk:8.1f} MiB · "
      f"مدخلات={len([x for x in args if x == '-i'])} · rc={r.returncode}")
if r.returncode:
    print("   خطأ:", (r.stderr or "")[-500:])
for name in SIZES:
    p = f"{out}/{name}.mp4"
    print(f"   {name:7s} -> {frames(p) if os.path.exists(p) else 'مفقود'} إطار "
          f"(المخطط {TOTAL_F})")

"""
٥+٦+٧: الكابشن داخل الرسم الواحد، و٤ مخرجات من فك ترميز واحد،
والذاكرة/الملفات الوسيطة.

المقارنة:
  أ) الحالية: لكل مقاس -> base.mp4 (ترميز) ثم حرق الكابشن على دفعات ٦٠
              (ترميز إضافي لكل دفعة) = 4 * (1 + ceil(n/60)) ترميز
  ب) المقترحة: تشغيلة ffmpeg وحدة: fps->split->trim->concat مرة وحدة،
              ثم split لأربع مقاسات، overlay الكابشن لكل مقاس،
              و٤ مخرجات = ٤ ترميزات نهائية بس.
"""
import subprocess, os, re, sys, time, shutil
from PIL import Image, ImageDraw

FPS = 30
SRC = "/tmp/realrun/click.mp4"          # 640x360 · 40s · 30fps · صوت
SIZES = {"reel": (1080, 1920), "square": (1080, 1080),
         "wide": (1920, 1080), "story": (720, 1280)}
NCAP = int(sys.argv[1]) if len(sys.argv) > 1 else 40
ARCH = sys.argv[2] if len(sys.argv) > 2 else "AB"
WORK = "/tmp/e8"
WORK = WORK + ARCH
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


import resource


def timed(args, label):
    """
    يرجّع (ثواني, ذروة ذاكرة أثقل ابن لهلأ MiB).

    `ru_maxrss` لـRUSAGE_CHILDREN تراكمية-عظمى: بتضل أعلى قيمة شافها
    أي ابن انتهى. فهي مش قيمة هالنداء لحاله، هي **ذروة التشغيلة كلها**
    — وهاي بالضبط الرقم اللي بيقرر هل بينقتل العملية على تيرمكس.
    """
    t0 = time.time()
    r = sh(args, text=True)
    dt = time.time() - t0
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
    if r.returncode:
        print(f"   ⚠ {label} رجّع {r.returncode}: {r.stderr[-400:]}")
    return dt, peak


def frames(p):
    f = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', p, '-f', 'null', '-'], text=True).stderr)
    return int(f[-1]) if f else None


def disk(d):
    return sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(d) for f in fs) / 1e6


# ---------- خطة القص
K = 30
SEGS = [(round(0.5 * i - 0.12, 3), round(0.5 * i + 0.28, 3)) for i in range(1, K + 1)]
PLAN = [max(1, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)
DUR = TOTAL_F / FPS
print(f"{K} مقطع · {TOTAL_F} إطار = {DUR:.3f}s · {NCAP} كابشن · {len(SIZES)} مقاسات\n")

# ---------- كابشنات مزيّفة (الشكل مغطّى بالصور المرجعية؛ هون بنختبر الرسم)
CAPS = {}
for name, (W, H) in SIZES.items():
    d = f"{WORK}/cap_{name}"
    os.makedirs(d)
    items = []
    for i in range(NCAP):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        dr.rectangle([W // 8, int(H * 0.70), W - W // 8, int(H * 0.78)],
                     fill=(255, 255, 255, 200))
        p = f"{d}/{i:04d}.png"
        img.save(p)
        s = i * DUR / NCAP
        items.append((p, s, s + DUR / NCAP))
    CAPS[name] = items

# =============== أ) الحالية
if "A" in ARCH:
    tA, mA = 0.0, 0.0
    dirA = f"{WORK}/A"
    os.makedirs(dirA)
    encodes_A = 0
    for name, (W, H) in SIZES.items():
        # base: مقطع لكل قطعة ثم concat demuxer
        lst = f"{dirA}/{name}.txt"
        with open(lst, "w") as fh:
            for i, (a, b) in enumerate(SEGS):
                p = f"{dirA}/{name}_s{i}.mp4"
                dt, mm = timed(['ffmpeg', '-y', '-v', 'error', '-ss', f'{a:.6f}', '-i', SRC,
                                '-frames:v', str(PLAN[i]),
                                '-vf', f'scale={W}:{H}:force_original_aspect_ratio=increase,'
                                       f'crop={W}:{H}',
                                '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                                '-c:a', 'aac', p], f"A/{name}/seg{i}")
                tA += dt
                mA = max(mA, mm)
                encodes_A += 1
                fh.write(f"file '{p}'\n")
        base = f"{dirA}/{name}_base.mp4"
        dt, mm = timed(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0',
                        '-i', lst, '-c', 'copy', base], f"A/{name}/concat")
        tA += dt
        mA = max(mA, mm)
        # حرق الكابشن على دفعات ٦٠
        cur = base
        items = CAPS[name]
        for bi in range(0, len(items), 60):
            chunk = items[bi:bi + 60]
            ins, parts, last = [], [], "[0:v]"
            for j, (p, s, e) in enumerate(chunk):
                ins += ['-i', p]
                nxt = f"[o{j}]"
                parts.append(f"{last}[{j+1}:v]overlay=0:0:enable='between(t,{s:.3f},{e:.3f})'{nxt}")
                last = nxt
            g = ";".join(parts)
            out = f"{dirA}/{name}_b{bi}.mp4"
            dt, mm = timed(['ffmpeg', '-y', '-v', 'error', '-i', cur, *ins,
                            '-filter_complex', g, '-map', last, '-map', '0:a?',
                            '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                            '-c:a', 'copy', out], f"A/{name}/burn{bi}")
            tA += dt
            mA = max(mA, mm)
            encodes_A += 1
            cur = out
        os.replace(cur, f"{dirA}/{name}.mp4")

    print(f"أ) الحالية:  {tA:6.1f}s · ذروة ذاكرة {mA:7.1f} MiB · "
          f"{encodes_A} ترميز فيديو · قرص وسيط {disk(dirA):.1f} MB")
    for name in SIZES:
        print(f"     {name:7s} -> {frames(f'{dirA}/{name}.mp4')} إطار (المخطط {TOTAL_F})")

# =============== ب) المقترحة — تشغيلة وحدة
if "B" in ARCH:
    dirB = f"{WORK}/B"
    os.makedirs(dirB)
    inputs = ['-i', SRC]
    png_index = {}
    idx = 1
    for name in SIZES:
        for p, s, e in CAPS[name]:
            inputs += ['-loop', '1', '-t', f'{DUR:.6f}', '-i', p]
            png_index[(name, p)] = idx
            idx += 1

    vp = [f"[0:v]fps={FPS}[src]",
          f"[src]split={K}" + "".join(f"[c{i}]" for i in range(K))]
    ap = [f"[0:a]asplit={K}" + "".join(f"[d{i}]" for i in range(K))]
    for i in range(K):
        s = ST[i]
        vp.append(f"[c{i}]trim=start_frame={s}:end_frame={s+PLAN[i]},setpts=PTS-STARTPTS[v{i}]")
        ap.append(f"[d{i}]atrim=start={s/FPS:.9f}:end={(s+PLAN[i])/FPS:.9f},asetpts=PTS-STARTPTS[a{i}]")
    parts = vp + ap
    parts.append("".join(f"[v{i}][a{i}]" for i in range(K)) +
                 f"concat=n={K}:v=1:a=1[vcat][ao]")
    parts.append(f"[vcat]fps={FPS},split={len(SIZES)}" +
                 "".join(f"[z{n}]" for n in range(len(SIZES))))
    # قيد حقيقي: كل تسمية مخرَج بالفلتر بتتربط مرة وحدة بس.
    # ٤ مخرجات لازمها ٤ نسخ صوت -> asplit.
    parts.append(f"[ao]asplit={len(SIZES)}" +
                 "".join(f"[ao{n}]" for n in range(len(SIZES))))
    maps = []
    for n, (name, (W, H)) in enumerate(SIZES.items()):
        parts.append(f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H}[g{name}]")
        last = f"[g{name}]"
        for j, (p, s, e) in enumerate(CAPS[name]):
            k = png_index[(name, p)]
            nxt = f"[{name}o{j}]"
            parts.append(f"{last}[{k}:v]overlay=0:0:enable='between(t,{s:.3f},{e:.3f})'{nxt}")
            last = nxt
        maps.append((name, last))

    g = "; ".join(parts)
    open(f"{WORK}/graph.txt", "w").write(g)
    args = ['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', g]
    for n, (name, lab) in enumerate(maps):
        args += ['-map', lab, '-map', f'[ao{n}]', '-c:v', 'libx264', '-preset', 'ultrafast',
                 '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', f'{dirB}/{name}.mp4']
    tB, mB = timed(args, "B/single")
    print(f"\nب) المقترحة: {tB:6.1f}s · ذروة ذاكرة {mB:7.1f} MiB · "
          f"{len(SIZES)} ترميز فيديو · قرص وسيط {disk(dirB):.1f} MB "
          f"· طول الرسم {len(g)} محرف · {len(inputs)//2} مدخل")
    for name in SIZES:
        p = f'{dirB}/{name}.mp4'
        print(f"     {name:7s} -> {frames(p) if os.path.exists(p) else 'مفقود'} إطار "
              f"(المخطط {TOTAL_F})")

"""
المرحلة ٠ — إثبات الزوم لكل مقطع بدون split=K.

الفكرة (خيار أ): الزوم بينحدّد بتعبير على **فهرس إطار المخرَج** `n`.
بما إن `select` بتعطي تيار موحّد وترقيمه بيصير 0..Σn_i−1 بعد
`setpts=N/FPS/TB`، فـ`n` بالضبط هو "أي إطار من الريل" — يعني عنده كل
المعلومات اللازمة ليعرف بأي مقطع احنا.

صياغتان:
  أ١) scale(eval=frame) ثم crop ثابت W×H
      = نفس فلتر الإنتاج حرفيًا، بس أبعاد scale صارت تعبير.
      إعادة تشكيل **وحدة** زي اليوم.
  أ٢) لوحة بأقصى زوم مرة وحدة، ثم crop(eval=frame) ثم scale لـW×H
      إعادة تشكيل **مرتين** -> جودة أقل، بس أبعاد scale ثابتة.

التعبير مجموع مسطّح مش if متداخلة:  Σ_i  const_i · between(n, a_i, b_i)
بالضبط حدّ واحد بيشتغل، فالمجموع = القيمة. مسطّح يعني بلا عمق تداخل
عند ٣٠٠ مقطع.

usage: z1.py <baseline|a1|a2> [K] [NOUT]
"""
import subprocess, os, re, sys, time, shutil, resource
sys.path.insert(0, "/tmp/realrun")
from z0 import SRC, SW, SH, PITCH, measure_zoom, real_zoom, frames, sh

FPS = 30
W, H = 540, 960
BIAS = 0.5
PAN = 26
CYCLE = [1.0, 1.1, 1.04, 1.14]
MODE = sys.argv[1]
K = int(sys.argv[2]) if len(sys.argv) > 2 else 12
NOUT = int(sys.argv[3]) if len(sys.argv) > 3 else 1
WORK = f"/tmp/z1_{MODE}_{K}_{NOUT}"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)
ENC = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '12', '-pix_fmt', 'yuv420p']

# ---------- خطة القص
span = 18.0 / (K + 1)
SEGS = [(round(span * (i + 1) - span * 0.35, 3), round(span * (i + 1) + span * 0.35, 3))
        for i in range(K)]
PLAN = [max(2, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)
OFF = [sum(PLAN[:i]) for i in range(K)]          # بداية كل مقطع بالمخرَج
ZOOM = [CYCLE[i % len(CYCLE)] for i in range(K)]


def geom(z):
    """نفس حساب `render.segment_filter` بالضبط لنمط crop."""
    sw, sh_ = int(W * z / 2) * 2, int(H * z / 2) * 2
    s = max(sw / SW, sh_ / SH)                   # معامل التكبير الفعلي
    iw, ih = round(SW * s), round(SH * s)        # أبعاد الصورة بعد scale
    room_x = max(0, sw - W)
    dx = max(-room_x // 2, min(room_x // 2, (1 if len(geom.hist) % 2 == 0 else -1) * PAN))
    geom.hist.append(1)
    return sw, sh_, s, iw, ih, dx


geom.hist = []


def flat(consts):
    """Σ const_i · between(n, a_i, b_i) — آخر مقطع بيمتد للأبد كأمان."""
    parts = []
    for i, c in enumerate(consts):
        a = OFF[i]
        b = (OFF[i] + PLAN[i] - 1) if i < K - 1 else 9999999
        parts.append(f"{c}*between(n\\,{a}\\,{b})")
    return "+".join(parts)


SEL = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
# settb+setpts=N: تفادي حساب العائمة بـsetpts=N/FPS/TB (شوف z5.py)
STEM = f"[0:v]fps={FPS},select='{SEL}',settb=1/{FPS},setpts=N,fps={FPS}"

t0 = time.time()
out = f"{WORK}/out"
os.makedirs(out)

if MODE == "baseline":
    lst = f"{WORK}/l.txt"
    with open(lst, "w") as fh:
        for i, (a, b) in enumerate(SEGS):
            z = ZOOM[i]
            sw, sh_ = int(W * z / 2) * 2, int(H * z / 2) * 2
            room_x = max(0, sw - W)
            dx = max(-room_x // 2, min(room_x // 2, (1 if i % 2 == 0 else -1) * PAN))
            vf = (f"scale={sw}:{sh_}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H}:(iw-{W})/2{dx:+d}:(ih-{H})*{BIAS:.4f},"
                  f"fps={FPS},setsar=1")
            p = f"{WORK}/s{i}.mp4"
            sh(['ffmpeg', '-y', '-v', 'error', '-ss', f'{a:.6f}', '-i', SRC,
                '-frames:v', str(PLAN[i]), '-vf', vf, *ENC, '-c:a', 'aac', p])
            fh.write(f"file '{p}'\n")
    sh(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', lst,
        '-c', 'copy', f'{out}/reel.mp4'])
    graph_len = 0

elif MODE == "a1":
    sws, shs, xs, ys = [], [], [], []
    for i in range(K):
        z = ZOOM[i]
        sw, sh_ = int(W * z / 2) * 2, int(H * z / 2) * 2
        s = max(sw / SW, sh_ / SH)
        iw, ih = round(SW * s), round(SH * s)
        room_x = max(0, sw - W)
        dx = max(-room_x // 2, min(room_x // 2, (1 if i % 2 == 0 else -1) * PAN))
        sws.append(sw)
        shs.append(sh_)
        xs.append(round((iw - W) / 2 + dx))
        ys.append(round((ih - H) * BIAS))
    chain = (f"scale=w='{flat(sws)}':h='{flat(shs)}':"
             f"force_original_aspect_ratio=increase:eval=frame,"
             f"crop={W}:{H}:x='{flat(xs)}':y='{flat(ys)}',setsar=1")
    parts = [STEM + (f",split={NOUT}" + "".join(f"[z{n}]" for n in range(NOUT))
                     if NOUT > 1 else "[z0]")]
    for n in range(NOUT):
        parts.append(f"[z{n}]{chain}[m{n}]")
    g = "; ".join(parts)
    graph_len = len(g)
    open(f"{WORK}/graph.txt", "w").write(g)
    args = ['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-filter_complex_script',
            f"{WORK}/graph.txt"]
    for n in range(NOUT):
        args += ['-map', f'[m{n}]', *ENC, f'{out}/o{n}.mp4']
    r = sh(args, text=True)
    if r.returncode:
        print("❌ فشل:", r.stderr[-700:])
    if os.path.exists(f"{out}/o0.mp4"):
        os.rename(f"{out}/o0.mp4", f"{out}/reel.mp4")

elif MODE == "a2":
    ZMAX = max(CYCLE)
    swm, shm = int(W * ZMAX / 2) * 2, int(H * ZMAX / 2) * 2
    smax = max(swm / SW, shm / SH)
    Cw, Ch = round(SW * smax), round(SH * smax)
    cws, chs, xs, ys = [], [], [], []
    for i in range(K):
        z = ZOOM[i]
        sw, sh_ = int(W * z / 2) * 2, int(H * z / 2) * 2
        s = max(sw / SW, sh_ / SH)
        iw, ih = round(SW * s), round(SH * s)
        room_x = max(0, sw - W)
        dx = max(-room_x // 2, min(room_x // 2, (1 if i % 2 == 0 else -1) * PAN))
        k = smax / s                              # لوحة/صورة-الزوم
        cws.append(int(W * k / 2) * 2)
        chs.append(int(H * k / 2) * 2)
        xs.append(round(((iw - W) / 2 + dx) * k))
        ys.append(round(((ih - H) * BIAS) * k))
    chain = (f"scale={swm}:{shm}:force_original_aspect_ratio=increase,"
             f"crop=w='{flat(cws)}':h='{flat(chs)}':x='{flat(xs)}':y='{flat(ys)}':"
             f"eval=frame,scale={W}:{H},setsar=1")
    parts = [STEM + (f",split={NOUT}" + "".join(f"[z{n}]" for n in range(NOUT))
                     if NOUT > 1 else "[z0]")]
    for n in range(NOUT):
        parts.append(f"[z{n}]{chain}[m{n}]")
    g = "; ".join(parts)
    graph_len = len(g)
    open(f"{WORK}/graph.txt", "w").write(g)
    args = ['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-filter_complex_script',
            f"{WORK}/graph.txt"]
    for n in range(NOUT):
        args += ['-map', f'[m{n}]', *ENC, f'{out}/o{n}.mp4']
    r = sh(args, text=True)
    if r.returncode:
        print("❌ فشل:", r.stderr[-700:])
    if os.path.exists(f"{out}/o0.mp4"):
        os.rename(f"{out}/o0.mp4", f"{out}/reel.mp4")

dt = time.time() - t0
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
P = f"{out}/reel.mp4"
got_f = frames(P) if os.path.exists(P) else None
print(f"[{MODE}] K={K} NOUT={NOUT} · {dt:6.1f}s · ذروة {pk:7.1f} MiB · "
      f"رسم={graph_len} محرف · إطارات {got_f}/{TOTAL_F} "
      + ("✅" if got_f == TOTAL_F else "❌"))

if got_f and K <= 24 and os.environ.get('ZFULL','1')=='1':
    print("   المقطع | مطلوب | فعلي(الإنتاج) | مقيس | إطار | خطأ")
    worst = 0.0
    for i in range(K):
        mid = OFF[i] + PLAN[i] // 2
        m = measure_zoom(P, mid)
        rz = real_zoom(ZOOM[i])
        e = abs(m - rz) if m else 99
        worst = max(worst, e)
        print(f"   {i:6d} | {ZOOM[i]:5.2f} | {rz:13.4f} | {m:5.4f} | "
              f"{mid:4d} | {e:.4f} {'✅' if e < 0.006 else '❌'}")
    print(f"   -> أسوأ خطأ زوم = {worst:.4f} "
          + ("✅" if worst < 0.006 else "❌"))

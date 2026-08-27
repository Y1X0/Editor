"""
المرحلة ٠ — الفحص الكامل لخيار أ١ مقابل الخط الأساسي.

بيفحص **كل إطار مخرَج**، مش عيّنة:
  ١. من أي إطار مصدر إجا (باركود)  -> إسقاط/تكرار/ترتيب
  ٢. معامل الزوم عنده              -> مطابقة zoom_cycle
  ٣. الزوم بيتغيّر عند حدّ المقطع بالضبط (مش إطار بدري ولا متأخر)
  ٤. عدد الإطارات = Σ frame_plan

usage: z3.py <baseline|a1|a2> [K]
"""
import subprocess, os, re, sys, time, shutil, resource, math
sys.path.insert(0, "/tmp/realrun")
from z0 import PITCH, profile, fit_pitch, real_zoom
from z2 import SRC, SW, SH, read_barcode
from PIL import Image

FPS = 30
W, H = 540, 960
BIAS, PAN = 0.5, 26
CYCLE = [1.0, 1.1, 1.04, 1.14]
MODE = sys.argv[1]
K = int(sys.argv[2]) if len(sys.argv) > 2 else 8
WORK = f"/tmp/z3_{MODE}_{K}"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)
ENC = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '10', '-pix_fmt', 'yuv420p']


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def frames(p):
    f = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', p, '-f', 'null', '-'], text=True).stderr)
    return int(f[-1]) if f else None


span = 18.0 / (K + 1)
SEGS = [(round(span * (i + 1) - span * 0.35, 3), round(span * (i + 1) + span * 0.35, 3))
        for i in range(K)]
PLAN = [max(3, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)
OFF = [sum(PLAN[:i]) for i in range(K)]
ZOOM = ([1.0] * K) if MODE == 'stem' else [CYCLE[i % len(CYCLE)] for i in range(K)]
DX = [max(0, int(W * ZOOM[i] / 2) * 2 - W) for i in range(K)]
DX = [max(-DX[i] // 2, min(DX[i] // 2, (1 if i % 2 == 0 else -1) * PAN)) for i in range(K)]


def seg_of(n):
    for i in range(K):
        if OFF[i] <= n < OFF[i] + PLAN[i]:
            return i
    return None


def flat(consts):
    out = []
    for i, c in enumerate(consts):
        a = OFF[i]
        b = (OFF[i] + PLAN[i] - 1) if i < K - 1 else 9999999
        out.append(f"{c}*between(n\\,{a}\\,{b})")
    return "+".join(out)


SEL = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
# `settb=1/FPS,setpts=N` بدل `setpts=N/FPS/TB`: التانية بتحسب بعائمة،
# وعند tbn=15360 بتطلع N·512 أحيانًا 100863.99999999999 فبتنقصّ لصحيح
# أقل، والـ`fps` اللي بعدها بتحطّ الإطار بالخانة السابقة -> إسقاط
# وتكرار مع بقاء العدد صحيح. قِسناها: ٢ من ٣٣٦ إطار.
STEM = f"[0:v]fps={FPS},select='{SEL}',settb=1/{FPS},setpts=N,fps={FPS}"

t0 = time.time()
OUT = f"{WORK}/out.mp4"

if MODE == "baseline":
    lst = f"{WORK}/l.txt"
    with open(lst, "w") as fh:
        for i, (a, b) in enumerate(SEGS):
            z = ZOOM[i]
            sw, sh_ = int(W * z / 2) * 2, int(H * z / 2) * 2
            vf = (f"scale={sw}:{sh_}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H}:(iw-{W})/2{DX[i]:+d}:(ih-{H})*{BIAS:.4f},"
                  f"fps={FPS},setsar=1")
            p = f"{WORK}/s{i}.mp4"
            sh(['ffmpeg', '-y', '-v', 'error', '-ss', f'{a:.6f}', '-i', SRC,
                '-frames:v', str(PLAN[i]), '-vf', vf, *ENC, '-c:a', 'aac', p])
            fh.write(f"file '{p}'\n")
    sh(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', lst,
        '-c', 'copy', OUT])
    glen = 0
else:
    sws, shs, xs, ys, cws, chs = [], [], [], [], [], []
    ZMAX = max(CYCLE)
    swm, shm = int(W * ZMAX / 2) * 2, int(H * ZMAX / 2) * 2
    smax = max(swm / SW, shm / SH)
    for i in range(K):
        z = ZOOM[i]
        sw, sh_ = int(W * z / 2) * 2, int(H * z / 2) * 2
        s = max(sw / SW, sh_ / SH)
        iw, ih = round(SW * s), round(SH * s)
        sws.append(sw); shs.append(sh_)
        if MODE == "a1":
            xs.append(round((iw - W) / 2 + DX[i]))
            ys.append(round((ih - H) * BIAS))
        else:
            k = smax / s
            cws.append(int(W * k / 2) * 2)
            chs.append(int(H * k / 2) * 2)
            xs.append(round(((iw - W) / 2 + DX[i]) * k))
            ys.append(round(((ih - H) * BIAS) * k))
    if MODE == "stem":
        chain = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                 f"crop={W}:{H},setsar=1")
    elif MODE == "a1":
        chain = (f"scale=w='{flat(sws)}':h='{flat(shs)}':"
                 f"force_original_aspect_ratio=increase:eval=frame,"
                 f"crop={W}:{H}:x='{flat(xs)}':y='{flat(ys)}',setsar=1")
    else:
        chain = (f"scale={swm}:{shm}:force_original_aspect_ratio=increase,"
                 f"crop=w='{flat(cws)}':h='{flat(chs)}':x='{flat(xs)}':y='{flat(ys)}':"
                 f"eval=frame,scale={W}:{H},setsar=1")
    g = f"{STEM}[z0]; [z0]{chain}[m0]"
    glen = len(g)
    open(f"{WORK}/graph.txt", "w").write(g)
    r = sh(['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-filter_complex_script',
            f"{WORK}/graph.txt", '-map', '[m0]', *ENC, OUT], text=True)
    if r.returncode:
        print("❌ فشل:", r.stderr[-700:])
        raise SystemExit(1)

dt = time.time() - t0
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
nf = frames(OUT)
print(f"[{MODE}] K={K} · {dt:.1f}s · ذروة {pk:.0f} MiB · رسم={glen} محرف")
print(f"  ١) إطارات: {nf}/{TOTAL_F} " + ("✅" if nf == TOTAL_F else "❌"))

fd = f"{WORK}/fr"
os.makedirs(fd)
# `-fps_mode passthrough`: بدونها مخرِج الصور بيشتغل cfr وبيطلّع إطار
# زيادة (٣٣٧ بدل ٣٣٦) — خلل بالاستخراج مش بالمسار.
# `-fps_mode passthrough` **بعد** `-i`: خيار مخرَج مش مدخَل. وبدونها
# مخرِج الصور بيشتغل cfr وبيطلّع إطار زيادة (٣٣٧ بدل ٣٣٦) — خلل
# بالاستخراج مش بالمسار.
sh(['ffmpeg', '-y', '-v', 'error', '-i', OUT, '-fps_mode', 'passthrough',
    f'{fd}/%05d.png'])
files = sorted(os.listdir(fd))
# حارس: "٠/٠ ✅" نجاح فاضي. لو الاستخراج فشل بدنا نعرف، مش نمرق.
assert len(files) == TOTAL_F, f"الاستخراج طلّع {len(files)} صورة والمخطط {TOTAL_F}"

bad_src, bad_zoom, zs, srcs = [], [], [], []
for n, f in enumerate(files):
    img = Image.open(f"{fd}/{f}").convert("RGB")
    i = seg_of(n)
    z_real = real_zoom(ZOOM[i], W, H, SW, SH)
    b = read_barcode(img, z_real, pan_out=DX[i], bias=BIAS)
    want_src = ST[i] + (n - OFF[i])
    srcs.append(b)
    if b != want_src:
        bad_src.append((n, want_src, b))
    v = profile(img)
    z = fit_pitch(v, PITCH * 0.85, PITCH * 1.45) / PITCH
    zs.append(z)
    if abs(z - z_real) > 0.006:
        bad_zoom.append((n, z_real, round(z, 4)))

print(f"  ٢) إطار المصدر الصح بكل إطار مخرَج: {len(files)-len(bad_src)}/{len(files)} "
      + ("✅" if not bad_src else f"❌ {bad_src[:5]}"))
print(f"     تكرار={len(srcs)-len(set(x for x in srcs if x is not None))} "
      f"· ترتيب تصاعدي جوا كل مقطع="
      + ("✅" if all(srcs[n+1] == srcs[n] + 1
                     for n in range(len(srcs)-1) if seg_of(n) == seg_of(n+1)
                     and srcs[n] is not None and srcs[n+1] is not None) else "❌"))
print(f"  ٣) الزوم مطابق بكل إطار: {len(files)-len(bad_zoom)}/{len(files)} "
      + ("✅" if not bad_zoom else f"❌ {bad_zoom[:5]}"))

# ٤) الحدود: آخر إطار بالمقطع i لازم يكون زوم i، وأول إطار بـi+1 زوم i+1
edge = []
for i in range(K - 1):
    last, first = OFF[i] + PLAN[i] - 1, OFF[i + 1]
    zl, zf = real_zoom(ZOOM[i], W, H, SW, SH), real_zoom(ZOOM[i + 1], W, H, SW, SH)
    if abs(zs[last] - zl) > 0.006 or abs(zs[first] - zf) > 0.006:
        edge.append((i, last, round(zs[last], 4), zl, first, round(zs[first], 4), zf))
print(f"  ٤) الزوم بيتبدّل عند الحدّ بالضبط: {K-1-len(edge)}/{K-1} "
      + ("✅" if not edge else f"❌ {edge[:3]}"))

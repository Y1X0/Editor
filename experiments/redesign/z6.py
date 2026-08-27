"""
مصفوفة التوسّع لخيار أ١: K ∈ {30,120,300} × مخرجات ∈ {1,2,4}.

المحاولة الأولى أعطت ٥٣٩/٦٠٠ عند K=300 — وطلع **خلل بالتجربة**:
٣٠٠ مقطع على مصدر ١٨s بتتداخل، و`select` بتمرّر إطار المصدر مرة وحدة
مهما تداخلت المدايات. حارس `assert` تحت بيمنع تكرار الخلل.

(هاد قيد حقيقي على الإنتاج كمان: مدايات `select` لازم تكون **منفصلة**.
`segments_from_words` بتدمج المتداخلة أصلًا، بس الرسم بيعتمد عليها.)
"""
import subprocess, os, re, sys, time, shutil, resource

FPS = 30
W, H = 540, 960
BIAS, PAN = 0.5, 26
CYCLE = [1.0, 1.1, 1.04, 1.14]
SRC = "/tmp/realrun/big.mp4"          # ٦٠٠s · 1280x720 · 30fps
SRC_W, SRC_H = 1280, 720
K = int(sys.argv[1])
NOUT = int(sys.argv[2])
WORK = f"/tmp/z6_{K}_{NOUT}"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)
ENC = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-pix_fmt', 'yuv420p']


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def frames(p):
    f = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', p, '-f', 'null', '-'], text=True).stderr)
    return int(f[-1]) if f else None


step = 600.0 / (K + 1)
SEGS = [(round(step * (i + 1) - 0.6, 3), round(step * (i + 1) + 0.6, 3)) for i in range(K)]
PLAN = [max(2, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)
OFF = [sum(PLAN[:i]) for i in range(K)]
ZOOM = [CYCLE[i % len(CYCLE)] for i in range(K)]

for i in range(K - 1):
    assert ST[i] + PLAN[i] <= ST[i + 1], (
        f"مدايات select متداخلة عند {i}: "
        f"[{ST[i]},{ST[i]+PLAN[i]}) و[{ST[i+1]},…) — التجربة غلط مش المسار")

sws, shs, xs, ys = [], [], [], []
for i in range(K):
    z = ZOOM[i]
    sw, sh_ = int(W * z / 2) * 2, int(H * z / 2) * 2
    s = max(sw / SRC_W, sh_ / SRC_H)
    iw, ih = round(SRC_W * s), round(SRC_H * s)
    room_x = max(0, sw - W)
    dx = max(-room_x // 2, min(room_x // 2, (1 if i % 2 == 0 else -1) * PAN))
    sws.append(sw); shs.append(sh_)
    xs.append(round((iw - W) / 2 + dx))
    ys.append(round((ih - H) * BIAS))


def flat(c):
    return "+".join(
        f"{c[i]}*between(n\\,{OFF[i]}\\,"
        f"{(OFF[i]+PLAN[i]-1) if i < K-1 else 9999999})" for i in range(K))


SEL = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
STEM = f"[0:v]fps={FPS},select='{SEL}',settb=1/{FPS},setpts=N,fps={FPS}"
chain = (f"scale=w='{flat(sws)}':h='{flat(shs)}':"
         f"force_original_aspect_ratio=increase:eval=frame,"
         f"crop={W}:{H}:x='{flat(xs)}':y='{flat(ys)}',setsar=1")
parts = [STEM + (f",split={NOUT}" + "".join(f"[z{n}]" for n in range(NOUT))
                 if NOUT > 1 else "[z0]")]
for n in range(NOUT):
    parts.append(f"[z{n}]{chain}[m{n}]")
g = "; ".join(parts)
open(f"{WORK}/graph.txt", "w").write(g)
args = ['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-filter_complex_script',
        f"{WORK}/graph.txt"]
for n in range(NOUT):
    args += ['-map', f'[m{n}]', *ENC, f'{WORK}/o{n}.mp4']

t0 = time.time()
r = sh(args, text=True)
dt = time.time() - t0
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
fr = [frames(f"{WORK}/o{n}.mp4") if os.path.exists(f"{WORK}/o{n}.mp4") else None
      for n in range(NOUT)]
ok = all(x == TOTAL_F for x in fr)
print(f"K={K:3d} مخرجات={NOUT} · {dt:6.1f}s · ذروة {pk:7.1f} MiB · "
      f"رسم={len(g):6d} محرف · إطارات {fr} من {TOTAL_F} " + ("✅" if ok else "❌"))
if r.returncode:
    print("   ❌", r.stderr[-400:])
shutil.rmtree(WORK, ignore_errors=True)

"""
الجذع `fps -> select -> setpts -> fps` بيعطي **عدد** الإطارات الصح بس
بيسقّط إطارًا وبيكرّر تاني (٢ من ٣٣٦). أي فلتر منهن السبب؟

بنقرا تسلسل إطارات المصدر من المخرَج بالباركود لكل صياغة.
"""
import subprocess, os, sys, shutil
sys.path.insert(0, "/tmp/realrun")
from z2 import read_barcode, SRC
from PIL import Image

FPS = 30
W, H = 540, 960
K = 8


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


span = 18.0 / (K + 1)
SEGS = [(round(span * (i + 1) - span * 0.35, 3), round(span * (i + 1) + span * 0.35, 3))
        for i in range(K)]
PLAN = [max(3, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL = sum(PLAN)
OFF = [sum(PLAN[:i]) for i in range(K)]
WANT = [ST[i] + j for i in range(K) for j in range(PLAN[i])]
SEL = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))

VARIANTS = {
    "fps→select→setpts→fps":
        (f"[0:v]fps={FPS},select='{SEL}',setpts=N/{FPS}/TB,fps={FPS}[m0]", []),
    "select→setpts→fps (بلا fps أولى)":
        (f"[0:v]select='{SEL}',setpts=N/{FPS}/TB,fps={FPS}[m0]", []),
    "fps→select→setpts + passthrough":
        (f"[0:v]fps={FPS},select='{SEL}',setpts=N/{FPS}/TB[m0]",
         ['-fps_mode', 'passthrough']),
    "select→setpts + passthrough":
        (f"[0:v]select='{SEL}',setpts=N/{FPS}/TB[m0]", ['-fps_mode', 'passthrough']),
    "fps→select + passthrough (بلا setpts)":
        (f"[0:v]fps={FPS},select='{SEL}'[m0]", ['-fps_mode', 'passthrough']),
    "fps→select→setpts=PTS-STARTPTS→fps":
        (f"[0:v]fps={FPS},select='{SEL}',setpts=PTS-STARTPTS,fps={FPS}[m0]", []),
}

print(f"المخطط: {TOTAL} إطار · {K} مقاطع\n")
for name, (g, extra) in VARIANTS.items():
    W_ = f"/tmp/z4/{abs(hash(name))}"
    shutil.rmtree(W_, ignore_errors=True)
    os.makedirs(W_)
    out = f"{W_}/o.mp4"
    r = sh(['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-filter_complex', g,
            '-map', '[m0]', *extra, '-c:v', 'libx264', '-preset', 'ultrafast',
            '-crf', '10', '-pix_fmt', 'yuv420p', out], text=True)
    if r.returncode:
        print(f"❌ {name}: {r.stderr[-200:]}")
        continue
    fd = f"{W_}/fr"
    os.makedirs(fd)
    sh(['ffmpeg', '-y', '-v', 'error', '-i', out, '-fps_mode', 'passthrough',
        f'{fd}/%05d.png'])
    fs = sorted(os.listdir(fd))
    got = [read_barcode(Image.open(f"{fd}/{f}").convert("RGB"), 1.0) for f in fs]
    n = min(len(got), len(WANT))
    bad = [(i, WANT[i], got[i]) for i in range(n) if got[i] != WANT[i]]
    dup = len(got) - len(set(x for x in got if x is not None))
    missing = len(set(WANT) - set(x for x in got if x is not None))
    print(f"{'✅' if not bad and len(fs) == TOTAL else '❌'} {name:38s} "
          f"إطارات={len(fs):4d}/{TOTAL} · غلط={len(bad):3d} · مكرر={dup} · ناقص={missing}"
          + (f"  أول ٣: {bad[:3]}" if bad else ""))
    shutil.rmtree(W_, ignore_errors=True)

"""
`setpts=N/FPS/TB` بتحسب بعائمة. لو قاعدة الزمن ١/١٥٣٦٠ (الشائعة بـmp4)
فالقيمة N·512 بتطلع أحيانًا 100863.99999999999 بدل 100864، وffmpeg
بيقصّها لصحيح -> الإطار بيقع قبل خانته بجزء تكّة، والـ`fps` اللي بعدها
بتحطّه بالخانة السابقة: تكرار + إسقاط، والعدد بيضل صح.

البديل: **صفّر العائمة**. `settb=1/FPS` بتخلّي التكّة = إطار، وبعدها
`setpts=N` عدد صحيح بالضبط بلا أي قسمة.

بنفحص كمان معدّل الإطارات بالمخرَج (لغم ١) لكل صياغة ناجحة.
"""
import subprocess, os, sys, shutil, re
sys.path.insert(0, "/tmp/realrun")
from z2 import read_barcode, SRC
from PIL import Image

FPS = 30
K = 8


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


span = 18.0 / (K + 1)
SEGS = [(round(span * (i + 1) - span * 0.35, 3), round(span * (i + 1) + span * 0.35, 3))
        for i in range(K)]
PLAN = [max(3, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL = sum(PLAN)
WANT = [ST[i] + j for i in range(K) for j in range(PLAN[i])]
SEL = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))

V = {
    "fps,select,setpts=N/FPS/TB,fps":
        (f"[0:v]fps={FPS},select='{SEL}',setpts=N/{FPS}/TB,fps={FPS}[m0]", []),
    "fps,select,settb=1/FPS,setpts=N,fps":
        (f"[0:v]fps={FPS},select='{SEL}',settb=1/{FPS},setpts=N,fps={FPS}[m0]", []),
    "fps,select,settb=1/FPS,setpts=N":
        (f"[0:v]fps={FPS},select='{SEL}',settb=1/{FPS},setpts=N[m0]", []),
    "fps,select,setpts=N/FPS/TB + passthrough":
        (f"[0:v]fps={FPS},select='{SEL}',setpts=N/{FPS}/TB[m0]",
         ['-fps_mode', 'passthrough']),
    "fps,select,settb,setpts=N + passthrough":
        (f"[0:v]fps={FPS},select='{SEL}',settb=1/{FPS},setpts=N[m0]",
         ['-fps_mode', 'passthrough']),
}

print(f"المخطط {TOTAL} إطار · المصدر {FPS}fps\n")
for name, (g, extra) in V.items():
    W_ = "/tmp/z5run"
    shutil.rmtree(W_, ignore_errors=True)
    os.makedirs(W_ + "/fr")
    out = f"{W_}/o.mp4"
    r = sh(['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-filter_complex', g,
            '-map', '[m0]', *extra, '-c:v', 'libx264', '-preset', 'ultrafast',
            '-crf', '10', '-pix_fmt', 'yuv420p', out], text=True)
    if r.returncode:
        print(f"❌ {name}: {r.stderr[-200:]}")
        continue
    info = sh(['ffmpeg', '-i', out], text=True).stderr
    ofps = re.findall(r'(\d+(?:\.\d+)?) fps', info)
    otbn = re.findall(r'(\d+k?) tbn', info)
    sh(['ffmpeg', '-y', '-v', 'error', '-i', out, '-fps_mode', 'passthrough',
        f'{W_}/fr/%05d.png'])
    fs = sorted(os.listdir(f"{W_}/fr"))
    got = [read_barcode(Image.open(f"{W_}/fr/{f}").convert("RGB"), 1.0) for f in fs]
    n = min(len(got), len(WANT))
    bad = [(i, WANT[i], got[i]) for i in range(n) if got[i] != WANT[i]]
    ok = (not bad) and len(fs) == TOTAL and ofps and float(ofps[0]) == FPS
    print(f"{'✅' if ok else '❌'} {name:42s} إطارات={len(fs):4d}/{TOTAL} · "
          f"غلط={len(bad):3d} · fps المخرَج={ofps[0] if ofps else '?'} · "
          f"tbn={otbn[0] if otbn else '?'}"
          + (f"  {bad[:2]}" if bad else ""))

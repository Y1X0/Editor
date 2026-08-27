"""
CR-2 مقاس: انزياح الصوت بالمعمارية الحالية مقابل المقترحة.

المصدر: click.mp4 — نقرة كل ٠.٥s، ٤٠s، ٣٠fps، صوت 48kHz.
أرضية القياس ٢ms (تحقّقنا منها بـdet.py).
"""
import subprocess, re, os, sys
sys.path.insert(0, "/tmp/realrun")
from det import peaks

FPS, SR = 30, 48000
SRC = "/tmp/realrun/click.mp4"
WORK = "/tmp/e6"
os.makedirs(WORK, exist_ok=True)
CLICKS = [float(x) for x in open("/tmp/realrun/click_times.txt").read().split()]


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def frames(p):
    f = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', p, '-f', 'null', '-'], text=True).stderr)
    return int(f[-1]) if f else None


# ---- خطة قص: ٣٠ مقطع، كل واحد بيمسك نقرة وحدة على بُعد ٠.١٢s من بدايته
K = 30
SEGS = [(round(0.5 * i - 0.12, 3), round(0.5 * i + 0.28, 3))
        for i in range(1, K + 1)]
PLAN = [max(1, round((b - a) * FPS)) for a, b in SEGS]
STARTS = [round(a * FPS) for a, _ in SEGS]

# النقرة i بتقع بالمصدر عند 0.5*i، وبداية المقطع frame STARTS[i]/FPS
want, t = [], 0.0
for idx, i in enumerate(range(1, K + 1)):
    want.append(t + (0.5 * i - STARTS[idx] / FPS))
    t += PLAN[idx] / FPS
print(f"{K} مقطع · المخطط Σ={sum(PLAN)} إطار = {sum(PLAN)/FPS:.4f}s")
print(f"المتوقع: أول نقرة {want[0]:.4f}s · آخر نقرة {want[-1]:.4f}s\n")

# ================= أ) الحالية: AAC لكل مقطع + concat demuxer -c copy
lst = f"{WORK}/list.txt"
with open(lst, "w") as fh:
    for i, (a, b) in enumerate(SEGS):
        p = f"{WORK}/a{i}.mp4"
        sh(['ffmpeg', '-y', '-v', 'error', '-ss', f'{a:.6f}', '-i', SRC,
            '-frames:v', str(PLAN[i]), '-c:v', 'libx264', '-preset', 'ultrafast',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', str(SR), p])
        fh.write(f"file '{p}'\n")
sh(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', lst,
    '-c', 'copy', f'{WORK}/A.mp4'])

# ================= ب) المقترحة: PCM بالفلتر + concat + ترميز AAC واحد
vp = [f"[0:v]fps={FPS}[src]",
      f"[src]split={K}" + "".join(f"[c{i}]" for i in range(K))]
ap = [f"[0:a]aresample={SR},asplit={K}" + "".join(f"[d{i}]" for i in range(K))]
for i in range(K):
    s = STARTS[i]
    vp.append(f"[c{i}]trim=start_frame={s}:end_frame={s+PLAN[i]},setpts=PTS-STARTPTS[v{i}]")
    ap.append(f"[d{i}]atrim=start={s/FPS:.9f}:end={(s+PLAN[i])/FPS:.9f},"
              f"asetpts=PTS-STARTPTS[a{i}]")
inter = "".join(f"[v{i}][a{i}]" for i in range(K))
g = "; ".join(vp + ap) + "; " + inter + \
    f"concat=n={K}:v=1:a=1[vo][ao]; [vo]fps={FPS}[out]"
r = sh(['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-filter_complex', g,
        '-map', '[out]', '-map', '[ao]', '-c:v', 'libx264', '-preset', 'ultrafast',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', str(SR), f'{WORK}/B.mp4'],
       text=True)
if r.returncode:
    print("ب فشلت:", r.stderr[-500:])

# ================= القياس
for tag, path in (("أ) الحالية  (AAC لكل مقطع + concat -c copy)", f"{WORK}/A.mp4"),
                  ("ب) المقترحة (atrim + concat فلتر + AAC واحد)", f"{WORK}/B.mp4")):
    if not os.path.exists(path):
        continue
    got = peaks(path)
    n = min(len(got), len(want))
    errs = [(got[i] - want[i]) * 1000 for i in range(n)]
    print(f"\n{tag}")
    print(f"   إطارات: {frames(path)} / المخطط {sum(PLAN)}")
    print(f"   نقرات: {len(got)} / {len(want)}")
    if errs:
        print(f"   انزياح أول نقرة = {errs[0]:+8.2f} ms")
        print(f"   انزياح آخر نقرة = {errs[-1]:+8.2f} ms")
        print(f"   أقصى |انزياح|   = {max(abs(e) for e in errs):8.2f} ms")
        print(f"   الاتجاه (آخر-أول) = {errs[-1]-errs[0]:+8.2f} ms  <- التراكم")
        print("   عيّنة: " + "  ".join(f"{errs[i]:+.0f}" for i in
                                       range(0, n, max(1, n // 8))))

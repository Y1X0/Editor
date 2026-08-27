"""
هل بنقدر نجبر concat يطلّع عدد إطارات المخطط بالضبط؟

من e2: دلالة trim الزمني = ceil(b*fps) - ceil(a*fps)  (مش round((b-a)*fps))
       و-fps_mode cfr الافتراضي بيعيد التشكيل لـ25fps لأن السلسلة بتفقد
       معدّل الإطارات -> هون كان الفرق ٢٢٢ -> ١٨٦.
"""
import subprocess, re

FPS = 30
SRC = "counter.mp4"
SEGS = [(1.237, 2.981), (4.512, 5.833), (8.104, 9.677), (11.05, 12.30), (14.9, 16.44)]
PLAN = [max(1, round((b - a) * FPS)) for a, b in SEGS]
N = len(SEGS)


def sh(a):
    return subprocess.run(a, capture_output=True, text=True)


def frames(p):
    f = re.findall(r'frame=\s*(\d+)', sh(['ffmpeg', '-i', p, '-f', 'null', '-']).stderr)
    return int(f[-1]) if f else None


def run(label, graph, extra=()):
    r = sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', SRC, '-filter_complex', graph,
            '-map', '[out]', *extra, '-c:v', 'libx264', '-preset', 'ultrafast',
            '-pix_fmt', 'yuv420p', '/tmp/e3.mp4'])
    n = frames('/tmp/e3.mp4')
    ok = "✅" if n == sum(PLAN) else "❌"
    print(f"{ok} {label:52s} -> {n} إطار" + (f"   خطأ: {r.stderr[-160:]}" if r.returncode else ""))
    return n


print(f"المخطط: {PLAN} · Σ={sum(PLAN)} إطار\n")

# أ) trim زمني + fps بعد concat
parts = [f"[0:v]trim=start={a:.6f}:end={b:.6f},setpts=PTS-STARTPTS[v{i}]"
         for i, (a, b) in enumerate(SEGS)]
tail = "".join(f"[v{i}]" for i in range(N)) + f"concat=n={N}:v=1:a=0,fps={FPS}[out]"
run("أ) trim زمني + concat + fps", "; ".join(parts) + "; " + tail)

# ب) fps -> split -> trim بالإطارات (start_frame = ceil(a*fps), العدد = المخطط)
starts = [-(-round(a * FPS * 1000) // 1000) for a, _ in SEGS]  # نبدأ من round مش ceil
starts = [round(a * FPS) for a, _ in SEGS]
parts = [f"[0:v]fps={FPS}[src]",
         f"[src]split={N}" + "".join(f"[c{i}]" for i in range(N))]
for i in range(N):
    s = starts[i]
    parts.append(f"[c{i}]trim=start_frame={s}:end_frame={s + PLAN[i]},setpts=PTS-STARTPTS[v{i}]")
tail = "".join(f"[v{i}]" for i in range(N)) + f"concat=n={N}:v=1:a=0[out]"
run("ب) fps->split->trim بالإطارات + concat", "; ".join(parts) + "; " + tail)

# ج) نفسها بس مع fps بعد concat كمان (حزام + حمّالة)
parts_c = list(parts)
tail_c = "".join(f"[v{i}]" for i in range(N)) + f"concat=n={N}:v=1:a=0,fps={FPS}[out]"
run("ج) ب + fps بعد concat", "; ".join(parts_c) + "; " + tail_c)

# د) ب مع -fps_mode passthrough بدل fps
run("د) ب + -fps_mode passthrough", "; ".join(parts) + "; " + tail,
    extra=('-fps_mode', 'passthrough'))

# هـ) trim زمني بحدود محسوبة على شبكة الإطارات: start=s/fps, end=(s+n)/fps
parts = []
for i, (a, b) in enumerate(SEGS):
    s = round(a * FPS)
    parts.append(f"[0:v]trim=start={s / FPS:.9f}:end={(s + PLAN[i]) / FPS:.9f},"
                 f"setpts=PTS-STARTPTS[v{i}]")
tail = "".join(f"[v{i}]" for i in range(N)) + f"concat=n={N}:v=1:a=0,fps={FPS}[out]"
run("هـ) trim زمني على شبكة الإطارات + fps", "; ".join(parts) + "; " + tail)

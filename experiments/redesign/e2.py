"""تفكيك: هل الخلل بالـtrim، ولا بالـconcat، ولا بالمرحّل (encoder)؟"""
import subprocess, re, math

FPS = 30
SRC = "counter.mp4"
SEGS = [(1.237, 2.981), (4.512, 5.833), (8.104, 9.677), (11.05, 12.30), (14.9, 16.44)]
PLAN = [max(1, round((b - a) * FPS)) for a, b in SEGS]


def sh(args):
    return subprocess.run(args, capture_output=True, text=True)


def frames(p):
    r = sh(['ffmpeg', '-i', p, '-f', 'null', '-']).stderr
    f = re.findall(r'frame=\s*(\d+)', r)
    return int(f[-1]) if f else None


print(f"المصدر: {frames(SRC)} إطار")
print(f"المخطط: {PLAN} · Σ={sum(PLAN)}\n")

# دلالة trim النظرية: بتمرّر الإطار لو a <= pts < b
theory = [math.ceil(b * FPS) - math.ceil(a * FPS) for a, b in SEGS]
print(f"دلالة trim النظرية (ceil(b*fps)-ceil(a*fps)): {theory} · Σ={sum(theory)}\n")

# ١) كل مقطع لحاله بـtrim — بدون concat
print("١) trim لحاله (بلا concat):")
solo = []
for i, (a, b) in enumerate(SEGS):
    g = f"[0:v]trim=start={a:.6f}:end={b:.6f},setpts=PTS-STARTPTS[out]"
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', SRC, '-filter_complex', g,
        '-map', '[out]', '-c:v', 'libx264', '-preset', 'ultrafast',
        '-pix_fmt', 'yuv420p', f'/tmp/s{i}.mp4'])
    n = frames(f'/tmp/s{i}.mp4')
    solo.append(n)
    print(f"   مقطع {i}: مخطط={PLAN[i]:3d}  نظري={theory[i]:3d}  فعلي={n:3d}")
print(f"   Σ فعلي = {sum(solo)}\n")

# ٢) -ss/-frames:v (طريقة الإنتاج الحالية) لكل مقطع
print("٢) -ss + -frames:v (اللي بالإنتاج):")
ss = []
for i, (a, b) in enumerate(SEGS):
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{a:.6f}', '-i', SRC,
        '-frames:v', str(PLAN[i]), '-c:v', 'libx264', '-preset', 'ultrafast',
        '-pix_fmt', 'yuv420p', f'/tmp/p{i}.mp4'])
    n = frames(f'/tmp/p{i}.mp4')
    ss.append(n)
    print(f"   مقطع {i}: مخطط={PLAN[i]:3d}  فعلي={n:3d}")
print(f"   Σ فعلي = {sum(ss)}\n")

# ٣) concat بالفلتر — بس مع -fps_mode passthrough (بلا إسقاط/تكرار)
for mode in ("cfr", "passthrough", "vfr"):
    parts = [f"[0:v]trim=start={a:.6f}:end={b:.6f},setpts=PTS-STARTPTS[v{i}]"
             for i, (a, b) in enumerate(SEGS)]
    g = "; ".join(parts) + "; " + "".join(f"[v{i}]" for i in range(len(SEGS))) \
        + f"concat=n={len(SEGS)}:v=1:a=0[out]"
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', SRC, '-filter_complex', g,
        '-map', '[out]', '-fps_mode', mode, '-c:v', 'libx264',
        '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', f'/tmp/cc_{mode}.mp4'])
    print(f"٣) concat + -fps_mode {mode:12s} -> {frames(f'/tmp/cc_{mode}.mp4')} إطار")

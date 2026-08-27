"""
concat demuxer مرفوض للكابشن: قاعدة زمنه ١/٢٥ ثابتة، فكل حدّ بينقرّب
لمضاعف ٤٠ms (قِسناها: ٦.٣٠٠ -> ٦.٢٨). خطأ لحد ٢٠ms = نص إطار عند ٣٠fps
-> كابشن بيبلّش إطار بدري.

البديل: تسلسل صور مفهرس بالإطار. لكل إطار مخرَج **وصلة رمزية** للـPNG
اللي المفروض يظهر فيه، ثم `-framerate 30 -i cap/%06d.png`. حتمي بالبناء:
ما في ولا عملية فاصلة، الفهرس هو الزمن.

usage: e15.py <nframes> <ncap>
"""
import subprocess, os, re, sys, time, shutil, resource
from PIL import Image, ImageDraw

FPS = 30
W, H = 480, 854
TOTAL_F = int(sys.argv[1]) if len(sys.argv) > 1 else 296
NCAP = int(sys.argv[2]) if len(sys.argv) > 2 else 25
WORK = f"/tmp/e15_{TOTAL_F}_{NCAP}"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(f"{WORK}/png")
os.makedirs(f"{WORK}/seq")


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


# حدود غير منتظمة عمدًا، كلها فهارس إطارات صحيحة
bounds, step = [0], TOTAL_F / NCAP
for i in range(1, NCAP):
    bounds.append(min(TOTAL_F - 1, round(i * step) + (1 if i % 3 == 0 else 0)))
bounds.append(TOTAL_F)
bounds = sorted(set(bounds))
NC = len(bounds) - 1
# ألوان **فريدة** لحد ٢٧٤٤ كابشن. المولّد السابق (%200) كان بيكرّر كل
# ٢٠٠ فيوهم إن في زحلقة — كان خلل بالمقياس مش بالمسار.
COLORS = [(40 + (i % 14) * 15, 40 + ((i // 14) % 14) * 15, 40 + ((i // 196) % 14) * 15)
          for i in range(NC)]
assert len(set(COLORS)) == NC, "ألوان متكررة — المقياس بينكسر"

CW, CH = 200, 60
X, Y = (W - CW) // 2, int(H * 0.72)

t0 = time.time()
for i in range(NC):
    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([0, 0, CW - 1, CH - 1], fill=COLORS[i] + (255,))
    img.save(f"{WORK}/png/{i:04d}.png")
# وصلات مفهرسة بالإطار
for i in range(NC):
    src = f"{WORK}/png/{i:04d}.png"
    for n in range(bounds[i], bounds[i + 1]):
        os.symlink(src, f"{WORK}/seq/{n:06d}.png")
t_links = time.time() - t0
links_bytes = sum(os.lstat(f"{WORK}/seq/{f}").st_size for f in os.listdir(f"{WORK}/seq"))

SRC = f"{WORK}/src.mp4"
sh(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi',
    '-i', f'color=c=gray:s={W}x{H}:r={FPS}:d={TOTAL_F/FPS + 1:.3f}',
    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', SRC])

g = (f"[0:v]trim=end_frame={TOTAL_F},setpts=PTS-STARTPTS,fps={FPS}[base]; "
     f"[base][1:v]overlay={X}:{Y}:eof_action=pass[out]")
OUT = f"{WORK}/out.mp4"
t1 = time.time()
r = sh(['ffmpeg', '-y', '-v', 'error', '-i', SRC,
        '-framerate', str(FPS), '-start_number', '0', '-i', f'{WORK}/seq/%06d.png',
        '-filter_complex', g, '-map', '[out]', '-c:v', 'libx264', '-preset', 'ultrafast',
        '-qp', '0', '-pix_fmt', 'yuv444p', OUT], text=True)
t_enc = time.time() - t1
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
if r.returncode:
    print("فشل:", r.stderr[-500:])
    raise SystemExit(1)

os.makedirs(f"{WORK}/fr")
sh(['ffmpeg', '-y', '-v', 'error', '-i', OUT, f'{WORK}/fr/%06d.png'])
fs = sorted(os.listdir(f"{WORK}/fr"))


def near(c):
    return min(range(NC), key=lambda i: sum((a - b) ** 2 for a, b in zip(c, COLORS[i])))


obs = [near(Image.open(f"{WORK}/fr/{f}").convert("RGB").getpixel((X + CW // 2, Y + CH // 2)))
       for f in fs]
first = {}
for n, c in enumerate(obs):
    first.setdefault(c, n)
bad = [i for i in range(NC) if first.get(i) != bounds[i]]

print(f"إطارات={TOTAL_F} كابشن={NC}: مخرَج={len(fs)} · "
      f"وصلات {len(os.listdir(f'{WORK}/seq'))} ({links_bytes/1024:.0f} KiB، "
      f"{t_links:.2f}s) · ترميز {t_enc:.1f}s · ذروة {pk:.0f} MiB")
print(f"   {'✅ كل كابشن على إطاره بالضبط' if not bad else f'❌ {len(bad)} مزحلق: {bad[:8]}'}"
      f"  ({NC - len(bad)}/{NC})")

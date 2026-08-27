"""
٥) الكابشن: هل مسار الـconcat demuxer بيوقّع كل كابشن على **الإطار**
   المقصود بالضبط؟

الطريقة: كل "كابشن" لون صريح مختلف. بنرمّز، بنفكّ كل إطار، وبنقرا لونه.
لو الكابشن i المفروض يبلّش بالإطار b[i]، لازم نلاقي لونه بالضبط من
b[i] لحد b[i+1]-1. أي إزاحة إطار واحد بتنمسك.
"""
import subprocess, os, re, shutil
from PIL import Image, ImageDraw

FPS = 30
W, H = 480, 854
NCAP = 25
WORK = "/tmp/e14"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(f"{WORK}/cap")
os.makedirs(f"{WORK}/fr")


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


# خطة قص بسيطة: ٨ مقاطع
K = 8
SEGS = [(round(1.0 + 2.0 * i, 3), round(1.0 + 2.0 * i + 1.23, 3)) for i in range(K)]
PLAN = [max(1, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)

# حدود الكابشنات بالإطارات (غير منتظمة عمدًا)
bounds = [0]
step = TOTAL_F / NCAP
for i in range(1, NCAP):
    bounds.append(round(i * step) + (1 if i % 3 == 0 else 0))
bounds.append(TOTAL_F)
bounds = sorted(set(bounds))
NCAP = len(bounds) - 1

COLORS = [((37 * i + 11) % 200 + 40, (91 * i + 7) % 200 + 40, (53 * i + 29) % 200 + 40)
          for i in range(NCAP)]
CW, CH = 200, 60
X, Y = (W - CW) // 2, int(H * 0.72)

lst = f"{WORK}/cap.txt"
with open(lst, "w") as fh:
    for i in range(NCAP):
        img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle([0, 0, CW - 1, CH - 1], fill=COLORS[i] + (255,))
        p = f"{WORK}/cap/{i:04d}.png"
        img.save(p)
        fh.write(f"file '{p}'\nduration {(bounds[i+1]-bounds[i])/FPS:.9f}\n")
    fh.write(f"file '{WORK}/cap/{NCAP-1:04d}.png'\n")

# مصدر رمادي ثابت عشان اللون الوحيد بالإطار يكون لون الكابشن
SRC = f"{WORK}/src.mp4"
sh(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi',
    '-i', f'color=c=gray:s={W}x{H}:r={FPS}:d=30', '-c:v', 'libx264',
    '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', SRC])

vsel = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
g = (f"[0:v]fps={FPS},select='{vsel}',setpts=N/{FPS}/TB,fps={FPS}[base]; "
     f"[1:v]fps={FPS}[cap]; [base][cap]overlay={X}:{Y}:eof_action=pass[out]")
OUT = f"{WORK}/out.mp4"
r = sh(['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-f', 'concat', '-safe', '0',
        '-i', lst, '-filter_complex', g, '-map', '[out]', '-c:v', 'libx264',
        '-preset', 'ultrafast', '-qp', '0', '-pix_fmt', 'yuv444p', OUT], text=True)
if r.returncode:
    print("فشل:", r.stderr[-500:])
    raise SystemExit(1)

sh(['ffmpeg', '-y', '-v', 'error', '-i', OUT, f'{WORK}/fr/%05d.png'])
got = sorted(os.listdir(f"{WORK}/fr"))
print(f"المخطط {TOTAL_F} إطار · استخرجنا {len(got)} · {NCAP} كابشن")


def nearest(c):
    return min(range(NCAP), key=lambda i: sum((a - b) ** 2 for a, b in zip(c, COLORS[i])))


obs = []
for f in got:
    px = Image.open(f"{WORK}/fr/{f}").convert("RGB").getpixel((X + CW // 2, Y + CH // 2))
    obs.append(nearest(px))

# أول إطار لكل كابشن حسب الملاحظة
first = {}
for n, cap in enumerate(obs):
    first.setdefault(cap, n)

bad = 0
for i in range(NCAP):
    want = bounds[i]
    have = first.get(i)
    if have != want:
        bad += 1
        if bad <= 8:
            print(f"   ❌ كابشن {i:3d}: متوقع يبلّش بالإطار {want:4d}، بلّش بـ{have}")
print(f"\n{'✅ كل كابشن على إطاره بالضبط' if bad == 0 else f'❌ {bad} كابشن مزحلق'}"
      f"  ({NCAP - bad}/{NCAP})")

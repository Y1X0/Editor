"""
المقارنة النهائية بإعدادات ترميز عادية (مش qp=0):
  أ) المعمارية الحالية   ب) المقترحة النهائية
usage: e18.py <A|B>
"""
import subprocess, os, re, sys, time, shutil, resource
from PIL import Image, ImageDraw

FPS, SR = 30, 48000
SRC = "/tmp/realrun/click.mp4"
SIZES = [("reel", 1080, 1920), ("square", 1080, 1080),
         ("wide", 1920, 1080), ("story", 720, 1280)]
ARCH = sys.argv[1]
NOUT = int(sys.argv[2]) if len(sys.argv) > 2 else 4
K, NCAP = 60, 240
SIZES = SIZES[:NOUT]
WORK = f"/tmp/e18{ARCH}{NOUT}"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)
ENC = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p']


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def frames(p):
    f = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', p, '-f', 'null', '-'], text=True).stderr)
    return int(f[-1]) if f else None


def disk(d):
    return sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(d) for f in fs
               if not os.path.islink(os.path.join(r, f))) / 1e6


SEGS = [(round(0.6 * i - 0.15, 3), round(0.6 * i + 0.25, 3)) for i in range(1, K + 1)]
PLAN = [max(1, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)
bounds = sorted(set([round(i * TOTAL_F / NCAP) for i in range(NCAP)] + [TOTAL_F]))
NC = len(bounds) - 1

POS = {}
for name, W, H in SIZES:
    os.makedirs(f"{WORK}/png_{name}")
    cw, ch = int(W * 0.82), int(W * 0.15)
    POS[name] = ((W - cw) // 2, int(H * 0.72) - ch // 2)
    for i in range(NC):
        img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d2 = ImageDraw.Draw(img)
        d2.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=ch // 3, fill=(0, 0, 0, 160))
        d2.rectangle([20, ch // 3, cw - 20, 2 * ch // 3], fill=(255, 255, 255, 230))
        img.save(f"{WORK}/png_{name}/{i:04d}.png")

out = f"{WORK}/out"
os.makedirs(out)
t0 = time.time()
encodes = 0

if ARCH == "A":
    tmp = f"{WORK}/tmp"
    os.makedirs(tmp)
    for name, W, H in SIZES:
        lst = f"{tmp}/{name}.txt"
        with open(lst, "w") as fh:
            for i, (a, b) in enumerate(SEGS):
                p = f"{tmp}/{name}_s{i}.mp4"
                sh(['ffmpeg', '-y', '-v', 'error', '-ss', f'{a:.6f}', '-i', SRC,
                    '-frames:v', str(PLAN[i]),
                    '-vf', f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}',
                    *ENC, '-c:a', 'aac', p])
                encodes += 1
                fh.write(f"file '{p}'\n")
        cur = f"{tmp}/{name}_base.mp4"
        sh(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', lst,
            '-c', 'copy', cur])
        x, y = POS[name]
        for bi in range(0, NC, 60):
            chunk = list(range(bi, min(bi + 60, NC)))
            ins, ps, last = [], [], "[0:v]"
            for j, i in enumerate(chunk):
                ins += ['-i', f"{WORK}/png_{name}/{i:04d}.png"]
                nxt = f"[o{j}]"
                ps.append(f"{last}[{j+1}:v]overlay={x}:{y}:"
                          f"enable='between(n,{bounds[i]},{bounds[i+1]-1})'{nxt}")
                last = nxt
            o = f"{tmp}/{name}_b{bi}.mp4"
            sh(['ffmpeg', '-y', '-v', 'error', '-i', cur, *ins, '-filter_complex', ";".join(ps),
                '-map', last, '-map', '0:a?', *ENC, '-c:a', 'copy', o])
            encodes += 1
            cur = o
        shutil.move(cur, f"{out}/{name}.mp4")
    d = disk(tmp)
else:
    for name, W, H in SIZES:
        os.makedirs(f"{WORK}/seq_{name}")
        for i in range(NC):
            s = f"{WORK}/png_{name}/{i:04d}.png"
            for n in range(bounds[i], bounds[i + 1]):
                os.symlink(s, f"{WORK}/seq_{name}/{n:06d}.png")
    vsel = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
    parts = [f"[0:v]fps={FPS},select='{vsel}',setpts=N/{FPS}/TB,fps={FPS},"
             f"split={len(SIZES)}" + "".join(f"[z{n}]" for n in range(len(SIZES)))]
    parts.append(f"[0:a]aresample={SR},asplit={K}" + "".join(f"[d{i}]" for i in range(K)))
    for i in range(K):
        parts.append(f"[d{i}]atrim=start={ST[i]/FPS:.9f}:end={(ST[i]+PLAN[i])/FPS:.9f},"
                     f"asetpts=PTS-STARTPTS[a{i}]")
    parts.append("".join(f"[a{i}]" for i in range(K)) + f"concat=n={K}:v=0:a=1[acat]")
    parts.append(f"[acat]asplit={len(SIZES)}" + "".join(f"[ao{n}]" for n in range(len(SIZES))))
    inputs = ['-i', SRC]
    for n, (name, W, H) in enumerate(SIZES):
        inputs += ['-framerate', str(FPS), '-start_number', '0',
                   '-i', f'{WORK}/seq_{name}/%06d.png']
        x, y = POS[name]
        parts.append(f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[g{n}]")
        parts.append(f"[g{n}][{n+1}:v]overlay={x}:{y}:eof_action=pass[m{n}]")
    args = ['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', "; ".join(parts)]
    for n, (name, W, H) in enumerate(SIZES):
        args += ['-map', f'[m{n}]', '-map', f'[ao{n}]', *ENC, '-c:a', 'aac',
                 f'{out}/{name}.mp4']
    r = sh(args, text=True)
    encodes = len(SIZES)
    if r.returncode:
        print("خطأ:", r.stderr[-500:])
    d = 0.0

dt = time.time() - t0
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
fr = {n: (frames(f"{out}/{n}.mp4") if os.path.exists(f"{out}/{n}.mp4") else None)
      for n, _, _ in SIZES}
print(f"{'أ) الحالية ' if ARCH=='A' else 'ب) المقترحة'}: {dt:6.1f}s · ذروة {pk:7.1f} MiB · "
      f"{encodes:3d} ترميز · قرص وسيط {d:6.1f} MB")
print(f"   إطارات {fr} (المخطط {TOTAL_F}) "
      + ("✅" if all(v == TOTAL_F for v in fr.values()) else "❌"))

"""
مقارنة نهائية للمرحلة ٠: الخط الأساسي مقابل أ١، **والزوم شغّال بالاتنين**.
نفس الحمل، نفس إعدادات الترميز، ٤ مقاسات، كابشن.

usage: z8.py <A|B> [NOUT]
"""
import subprocess, os, re, sys, time, shutil, resource
from PIL import Image, ImageDraw

FPS, SR = 30, 48000
SRC = "/tmp/realrun/big.mp4"          # ٦٠٠s · 1280×720 · 30fps
SRC_W, SRC_H = 1280, 720
SIZES = [("reel", 1080, 1920), ("square", 1080, 1080),
         ("wide", 1920, 1080), ("story", 720, 1280)]
CYCLE = [1.0, 1.1, 1.04, 1.14]
BIAS, PAN = 0.5, 26
ARCH = sys.argv[1]
NOUT = int(sys.argv[2]) if len(sys.argv) > 2 else 4
SIZES = SIZES[:NOUT]
K, NCAP = 60, 240
WORK = f"/tmp/z8{ARCH}{NOUT}"
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


step = 600.0 / (K + 1)
SEGS = [(round(step * (i + 1) - 0.6, 3), round(step * (i + 1) + 0.6, 3)) for i in range(K)]
PLAN = [max(2, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)
OFF = [sum(PLAN[:i]) for i in range(K)]
ZOOM = [CYCLE[i % len(CYCLE)] for i in range(K)]
bounds = sorted(set([round(i * TOTAL_F / NCAP) for i in range(NCAP)] + [TOTAL_F]))
NC = len(bounds) - 1
for i in range(K - 1):
    assert ST[i] + PLAN[i] <= ST[i + 1]

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


def geom(W, H, z, i):
    sw, sh_ = int(W * z / 2) * 2, int(H * z / 2) * 2
    s = max(sw / SRC_W, sh_ / SRC_H)
    iw, ih = round(SRC_W * s), round(SRC_H * s)
    room = max(0, sw - W)
    dx = max(-room // 2, min(room // 2, (1 if i % 2 == 0 else -1) * PAN))
    return sw, sh_, round((iw - W) / 2 + dx), round((ih - H) * BIAS), dx


out = f"{WORK}/out"
os.makedirs(out)
t0 = time.time()

if ARCH == "A":
    tmp = f"{WORK}/tmp"
    os.makedirs(tmp)
    enc = 0
    for name, W, H in SIZES:
        lst = f"{tmp}/{name}.txt"
        with open(lst, "w") as fh:
            for i, (a, b) in enumerate(SEGS):
                sw, sh_, _, _, dx = geom(W, H, ZOOM[i], i)
                vf = (f"scale={sw}:{sh_}:force_original_aspect_ratio=increase,"
                      f"crop={W}:{H}:(iw-{W})/2{dx:+d}:(ih-{H})*{BIAS:.4f},"
                      f"fps={FPS},setsar=1")
                p = f"{tmp}/{name}_s{i}.mp4"
                sh(['ffmpeg', '-y', '-v', 'error', '-ss', f'{a:.6f}', '-i', SRC,
                    '-frames:v', str(PLAN[i]), '-vf', vf, *ENC, '-c:a', 'aac', p])
                enc += 1
                fh.write(f"file '{p}'\n")
        cur = f"{tmp}/{name}_base.mp4"
        sh(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', lst,
            '-c', 'copy', cur])
        x, y = POS[name]
        for bi in range(0, NC, 60):
            ch_ = list(range(bi, min(bi + 60, NC)))
            ins, ps, last = [], [], "[0:v]"
            for j, i in enumerate(ch_):
                ins += ['-i', f"{WORK}/png_{name}/{i:04d}.png"]
                nxt = f"[o{j}]"
                ps.append(f"{last}[{j+1}:v]overlay={x}:{y}:"
                          f"enable='between(n\\,{bounds[i]}\\,{bounds[i+1]-1})'{nxt}")
                last = nxt
            o = f"{tmp}/{name}_b{bi}.mp4"
            sh(['ffmpeg', '-y', '-v', 'error', '-i', cur, *ins,
                '-filter_complex', ";".join(ps), '-map', last, '-map', '0:a?',
                *ENC, '-c:a', 'copy', o])
            enc += 1
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

    def flat(c):
        return "+".join(
            f"{c[i]}*between(n\\,{OFF[i]}\\,"
            f"{(OFF[i]+PLAN[i]-1) if i < K-1 else 9999999})" for i in range(K))

    SEL = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
    parts = [f"[0:v]fps={FPS},select='{SEL}',settb=1/{FPS},setpts=N,fps={FPS}"
             + (f",split={NOUT}" + "".join(f"[z{n}]" for n in range(NOUT))
                if NOUT > 1 else "[z0]")]
    parts.append(f"[0:a]aresample={SR},asplit={K}" + "".join(f"[d{i}]" for i in range(K)))
    for i in range(K):
        parts.append(f"[d{i}]atrim=start={ST[i]/FPS:.9f}:end={(ST[i]+PLAN[i])/FPS:.9f},"
                     f"asetpts=PTS-STARTPTS[a{i}]")
    parts.append("".join(f"[a{i}]" for i in range(K)) + f"concat=n={K}:v=0:a=1[acat]")
    parts.append(f"[acat]asplit={NOUT}" + "".join(f"[ao{n}]" for n in range(NOUT))
                 if NOUT > 1 else "[acat]anull[ao0]")
    inputs = ['-i', SRC]
    for n, (name, W, H) in enumerate(SIZES):
        inputs += ['-framerate', str(FPS), '-start_number', '0',
                   '-i', f'{WORK}/seq_{name}/%06d.png']
        sws = [geom(W, H, ZOOM[i], i)[0] for i in range(K)]
        shs = [geom(W, H, ZOOM[i], i)[1] for i in range(K)]
        xs = [geom(W, H, ZOOM[i], i)[2] for i in range(K)]
        ys = [geom(W, H, ZOOM[i], i)[3] for i in range(K)]
        x, y = POS[name]
        parts.append(f"[z{n}]scale=w='{flat(sws)}':h='{flat(shs)}':"
                     f"force_original_aspect_ratio=increase:eval=frame,"
                     f"crop={W}:{H}:x='{flat(xs)}':y='{flat(ys)}',setsar=1[g{n}]")
        parts.append(f"[g{n}][{n+1}:v]overlay={x}:{y}:eof_action=pass[m{n}]")
    g = "; ".join(parts)
    open(f"{WORK}/graph.txt", "w").write(g)
    args = ['ffmpeg', '-y', '-v', 'error', *inputs,
            '-filter_complex_script', f"{WORK}/graph.txt"]
    for n, (name, W, H) in enumerate(SIZES):
        args += ['-map', f'[m{n}]', '-map', f'[ao{n}]', *ENC, '-c:a', 'aac',
                 f'{out}/{name}.mp4']
    r = sh(args, text=True)
    enc = NOUT
    d = 0.0
    if r.returncode:
        print("❌", r.stderr[-500:])

dt = time.time() - t0
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
fr = {n: (frames(f"{out}/{n}.mp4") if os.path.exists(f"{out}/{n}.mp4") else None)
      for n, _, _ in SIZES}
print(f"{'أ) الحالية ' if ARCH=='A' else 'ب) أ١      '} مخرجات={NOUT} · {dt:6.1f}s · "
      f"ذروة {pk:7.1f} MiB · {enc:3d} ترميز · قرص وسيط {d:6.1f} MB")
print(f"   إطارات {fr} (المخطط {TOTAL_F}) "
      + ("✅" if all(v == TOTAL_F for v in fr.values()) else "❌"))

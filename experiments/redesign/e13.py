"""
٧) الذاكرة: شو اللي بياكلها فعلًا؟ عدد المخرجات ولا عدد المقاطع؟
   وسؤال تيرمكس: هل ٤ مخرجات بتشغيلة وحدة بتزبط على ٢GB؟

بنقيس الذروة مقابل: عدد المخرجات (١..٤) × عدد المقاطع (٣٠، ١٢٠، ٣٠٠).
مصدر ٦٠٠s مبني هون عشان نوسّع عدد المقاطع لحدود ريل حقيقي.
"""
import subprocess, os, re, sys, time, shutil, resource

FPS, SR = 30, 48000
ALL = [("reel", 1080, 1920), ("square", 1080, 1080),
       ("wide", 1920, 1080), ("story", 720, 1280)]
NOUT = int(sys.argv[1])
K = int(sys.argv[2])
SRC = "/tmp/realrun/big.mp4"
WORK = f"/tmp/e13_{NOUT}_{K}"
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def frames(p):
    f = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', p, '-f', 'null', '-'], text=True).stderr)
    return int(f[-1]) if f else None


if not os.path.exists(SRC):
    sh(['ffmpeg', '-y', '-v', 'error',
        '-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate={FPS}:duration=600',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=600:sample_rate=48000',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-shortest', SRC])

# K مقطع موزّعة على ٦٠٠s، كل واحد ~١.٢s
step = 600.0 / (K + 1)
SEGS = [(round(step * (i + 1) - 0.6, 3), round(step * (i + 1) + 0.6, 3)) for i in range(K)]
PLAN = [max(1, round((b - a) * FPS)) for a, b in SEGS]
ST = [round(a * FPS) for a, _ in SEGS]
TOTAL_F = sum(PLAN)

SIZES = ALL[:NOUT]
vsel = "+".join(f"between(n,{ST[i]},{ST[i]+PLAN[i]-1})" for i in range(K))
parts = [f"[0:v]fps={FPS},select='{vsel}',setpts=N/{FPS}/TB,fps={FPS}"
         + (f",split={NOUT}" + "".join(f"[z{n}]" for n in range(NOUT)) if NOUT > 1 else "[z0]")]
ap = [f"[0:a]aresample={SR},asplit={K}" + "".join(f"[d{i}]" for i in range(K))]
for i in range(K):
    ap.append(f"[d{i}]atrim=start={ST[i]/FPS:.9f}:end={(ST[i]+PLAN[i])/FPS:.9f},"
              f"asetpts=PTS-STARTPTS[a{i}]")
parts += ap
parts.append("".join(f"[a{i}]" for i in range(K)) + f"concat=n={K}:v=0:a=1[acat]")
parts.append(f"[acat]asplit={NOUT}" + "".join(f"[ao{n}]" for n in range(NOUT))
             if NOUT > 1 else "[acat]anull[ao0]")
for n, (name, W, H) in enumerate(SIZES):
    parts.append(f"[z{n}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[m{n}]")

g = "; ".join(parts)
out = f"{WORK}/out"
os.makedirs(out)
args = ['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-filter_complex', g]
for n, (name, W, H) in enumerate(SIZES):
    args += ['-map', f'[m{n}]', '-map', f'[ao{n}]', '-c:v', 'libx264',
             '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
             f'{out}/{name}.mp4']

t0 = time.time()
r = sh(args, text=True)
dt = time.time() - t0
pk = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
got = frames(f"{out}/{SIZES[0][0]}.mp4") if os.path.exists(f"{out}/{SIZES[0][0]}.mp4") else None
print(f"مخرجات={NOUT} مقاطع={K:3d} إطارات={TOTAL_F:5d}: {dt:7.1f}s · "
      f"ذروة {pk:8.1f} MiB · رسم={len(g):6d} محرف · rc={r.returncode} · "
      f"مخرَج={got} " + ("✅" if got == TOTAL_F else "❌"))
if r.returncode:
    print("   خطأ:", (r.stderr or "")[-400:])

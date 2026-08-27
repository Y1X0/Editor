"""
S6 — مدخل لكل مؤثر مقابل مدخل واحد و`asplit`.

الأصول قليلة (whoosh, pop, impact…) والاستعمالات كتيرة. فهل نفتح
الملف N مرة، ولا مرة وحدة ونقسّمه؟
"""
import subprocess, time
import tools as T
SR, DUR = T.SR, 60

def peak_rss(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    hwm = 0
    while p.poll() is None:
        try:
            with open(f"/proc/{p.pid}/status") as f:
                for line in f:
                    if line.startswith("VmHWM:"):
                        hwm = max(hwm, int(line.split()[1])); break
        except OSError:
            break
        time.sleep(0.02)
    err = p.stderr.read().decode("utf-8", "replace"); p.stderr.close()
    if p.returncode != 0:
        raise RuntimeError(err[-800:])
    return hwm / 1024.0

T.run(["-f","lavfi","-i",f"sine=frequency=300:sample_rate={SR}:duration={DUR}",
       "-c:a","pcm_s16le","/tmp/r_speech.wav"])
T.click("/tmp/r_click.wav")
FMT = f"aformat=sample_rates={SR}:channel_layouts=stereo"

def build(n, reuse):
    ins = ["-i","/tmp/r_speech.wav"]
    fc, labels = [], ["[0:a]"]
    pos = [int(SR*DUR*(i+0.5)/n) for i in range(n)]
    if reuse:
        ins += ["-i","/tmp/r_click.wav"]
        fc.append(f"[1:a]{FMT},asplit={n}" + "".join(f"[c{i}]" for i in range(n)))
        for i,p in enumerate(pos):
            fc.append(f"[c{i}]adelay={p}S:all=1[s{i}]"); labels.append(f"[s{i}]")
    else:
        for i,p in enumerate(pos):
            ins += ["-i","/tmp/r_click.wav"]
            fc.append(f"[{i+1}:a]{FMT},adelay={p}S:all=1[s{i}]"); labels.append(f"[s{i}]")
    fc.append("".join(labels)+f"amix=inputs={n+1}:duration=first:normalize=0[a]")
    return ins, ";".join(fc)

print(f"{'N':>5} {'الشكل':<22} {'RSS':>9} {'ثواني':>7} {'الرسم':>9} {'طول':>10}")
for n in (50, 200, 500):
    for reuse, lbl in ((False,"مدخل لكل مؤثر"), (True,"مدخل واحد + asplit")):
        ins, g = build(n, reuse)
        open("/tmp/r_graph.txt","w").write(g)
        cmd = (["ffmpeg","-y","-loglevel","error"]+ins+
               ["-filter_complex_script","/tmp/r_graph.txt","-map","[a]",
                "-c:a","pcm_s16le","/tmp/r_out.wav"])
        t0=time.time(); rss=peak_rss(cmd); el=time.time()-t0
        ns=len(T.pcm("/tmp/r_out.wav"))
        print(f"{n:>5} {lbl:<22} {rss:>8.1f}M {el:>7.2f} {len(g):>8}B {ns:>10}")
    print()

"""
S5 — كلفة N مؤثرًا: ذاكرة، وقت، حجم الرسم.

الدرس من المرحلة ٥: سلسلة overlay طويلة أكلت ٢٧٧١ MiB عند ٢٠٠ كابشن.
السؤال: هل `amix` بمدخلات كتيرة بيعمل نفس الشي؟ وهل عدد **المدخلات**
(‎-i لكل ملف) بيفجّر شي لحاله؟
"""
import os, subprocess, sys, time
import tools as T
SR = T.SR
DUR = 60


def peak_rss(cmd):
    """ذروة RSS بالميغابايت من /proc/<pid>/status — عملية وحدة معزولة."""
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
    err = p.stderr.read().decode("utf-8", "replace")
    p.stderr.close()
    if p.returncode != 0:
        raise RuntimeError(err[-800:])
    return hwm / 1024.0


T.run(["-f", "lavfi", "-i", f"sine=frequency=300:sample_rate={SR}:duration={DUR}",
       "-c:a", "pcm_s16le", "/tmp/sc_speech.wav"])
T.click("/tmp/sc_click.wav")

print(f"سرير {DUR}s · كل مؤثر ملف مدخَل مستقل\n")
print(f"{'N':>5} {'ذروة RSS':>10} {'ثواني':>7} {'حجم الرسم':>11} {'طول المخرَج':>12}")
base = None
for n in (0, 10, 50, 200, 500):
    ins = ["-i", "/tmp/sc_speech.wav"]
    fc = []
    labels = ["[0:a]"]
    for i in range(n):
        ins += ["-i", "/tmp/sc_click.wav"]
        pos = int(SR * DUR * (i + 0.5) / max(1, n))
        fc.append(f"[{i+1}:a]aformat=sample_rates={SR}:channel_layouts=stereo,"
                  f"adelay={pos}S:all=1[s{i}]")
        labels.append(f"[s{i}]")
    if n:
        fc.append("".join(labels) + f"amix=inputs={n+1}:duration=first:normalize=0[a]")
    else:
        fc.append("[0:a]anull[a]")
    graph = ";".join(fc)
    gp = "/tmp/sc_graph.txt"
    open(gp, "w").write(graph)
    out = "/tmp/sc_out.wav"
    cmd = (["ffmpeg", "-y", "-loglevel", "error"] + ins +
           ["-filter_complex_script", gp, "-map", "[a]",
            "-c:a", "pcm_s16le", out])
    t0 = time.time()
    rss = peak_rss(cmd)
    el = time.time() - t0
    ns = len(T.pcm(out))
    if n == 0:
        base = ns
    ok = "" if ns == base else f"  ❌ اختلف عن {base}"
    print(f"{n:>5} {rss:>9.1f}M {el:>7.2f} {len(graph):>10}B {ns:>12}{ok}")

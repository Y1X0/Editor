"""
S2 — سلوك `amix` على مستوى الصوت.

خطران معروفان بالسمعة ولازم ينقاسا مش ينفترضا:
  ١. `normalize=1` (الافتراضي) بيقسّم كل مدخل على عددهن — يعني
     الكلام بيخفت كل ما ضفنا مؤثرًا.
  ٢. `dropout_transition` (٢ ثانية افتراضيًا): لما مدخل يخلص، amix
     بيعيد توزيع الكسب على الباقي **تدريجيًا** — والمؤثرات قصيرة،
     فهاد بيعني تنفّس/ضخّ مستمر بمستوى الكلام.
"""
import tools as T

SR = T.SR
SPEECH = "/tmp/sfx_speech.wav"
CLICK = "/tmp/sfx_click.wav"
# "كلام" = نغمة مستمرة عشان نقيس مستواه بسهولة
T.run(["-f", "lavfi", "-i", f"sine=frequency=300:sample_rate={SR}:duration=6",
       "-c:a", "pcm_s16le", SPEECH])
T.click(CLICK)

BASE = max(abs(v) for v in T.pcm(SPEECH))
print(f"مستوى الكلام لحاله: {BASE:.4f}\n")


def mix(n_sfx, extra="", positions=None):
    """n مؤثرات موزّعة، وقياس مستوى الكلام بمنطقة خالية من المؤثرات."""
    positions = positions or [int(SR * (0.5 + i)) for i in range(n_sfx)]
    ins = ["-i", SPEECH]
    for _ in range(n_sfx):
        ins += ["-i", CLICK]
    fc = []
    labels = ["[0:a]"]
    for i, p in enumerate(positions):
        fc.append(f"[{i+1}:a]adelay={p}S[s{i}]")
        labels.append(f"[s{i}]")
    fc.append("".join(labels) +
              f"amix=inputs={n_sfx+1}:duration=first{extra}[a]")
    out = "/tmp/sfx_s2.wav"
    T.run(ins + ["-filter_complex", ";".join(fc), "-map", "[a]",
                 "-c:a", "pcm_s16le", out])
    s = T.pcm(out)
    # مستوى الكلام بآخر ثانية — بعيد عن كل المؤثرات
    tail = s[int(SR * 5.2):int(SR * 5.8)]
    head = s[:int(SR * 0.3)]
    return max(map(abs, head)), max(map(abs, tail))

print(f"{'مؤثرات':>7} {'إعدادات':<34} {'بداية':>8} {'نهاية':>8} {'مقابل الأصل':>12}")
for n in (1, 2, 5, 20):
    h, t = mix(n)
    print(f"{n:>7} {'(افتراضي)':<34} {h:>8.4f} {t:>8.4f} {t/BASE:>11.2f}×")

print()
for opt, lbl in ((":normalize=0", "normalize=0"),
                 (":normalize=0:dropout_transition=0", "normalize=0 + dropout=0")):
    h, t = mix(20, opt)
    print(f"{20:>7} {lbl:<34} {h:>8.4f} {t:>8.4f} {t/BASE:>11.2f}×")

print("\n--- تنفّس الكسب: المستوى عبر الزمن مع ٥ مؤثرات (افتراضي) ---")
positions = [int(SR * (0.5 + i)) for i in range(5)]
ins = ["-i", SPEECH] + sum([["-i", CLICK] for _ in range(5)], [])
fc = [f"[{i+1}:a]adelay={p}S[s{i}]" for i, p in enumerate(positions)]
fc.append("[0:a]" + "".join(f"[s{i}]" for i in range(5)) +
          "amix=inputs=6:duration=first[a]")
T.run(ins + ["-filter_complex", ";".join(fc), "-map", "[a]",
             "-c:a", "pcm_s16le", "/tmp/sfx_s2b.wav"])
s = T.pcm("/tmp/sfx_s2b.wav")
for sec in range(6):
    w = s[int(SR*(sec+0.30)):int(SR*(sec+0.45))]   # بين المؤثرات
    print(f"  ثانية {sec}: مستوى الكلام {max(map(abs,w)):.4f}")

"""
S3 — هل الكلام بينحفظ **عيّنة بعيّنة** بعد المزج؟

هاي الخاصية اللي بتحمي E2. لو المزج ما بيلمس عيّنات الكلام برّا
مواقع المؤثرات، فتزامن الصوت مع الصورة **ما بيقدر** ينكسر بالبناء.
"""
import tools as T

SR = T.SR
SPEECH, CLICK = "/tmp/sfx_speech.wav", "/tmp/sfx_click.wav"
T.run(["-f", "lavfi", "-i", f"sine=frequency=300:sample_rate={SR}:duration=6",
       "-c:a", "pcm_s16le", SPEECH])
T.click(CLICK)            # ٢٠ms = ٩٦٠ عيّنة

REF = T.pcm(SPEECH)
POS = [int(SR * 1.0), int(SR * 3.0)]      # مؤثران، ومناطق نظيفة واضحة
CLICK_LEN = len(T.pcm(CLICK))


def mixed(extra):
    ins = ["-i", SPEECH, "-i", CLICK, "-i", CLICK]
    fc = [f"[{i+1}:a]adelay={p}S[s{i}]" for i, p in enumerate(POS)]
    fc.append("[0:a][s0][s1]" + f"amix=inputs=3:duration=first{extra}[a]")
    T.run(ins + ["-filter_complex", ";".join(fc), "-map", "[a]",
                 "-c:a", "pcm_s16le", "/tmp/sfx_s3.wav"])
    return T.pcm("/tmp/sfx_s3.wav")


def report(label, got):
    n = min(len(REF), len(got))
    touched = set()
    for p in POS:
        touched.update(range(p - 2, p + CLICK_LEN + 2))
    clean = [i for i in range(n) if i not in touched]
    worst = max(abs(got[i] - REF[i]) for i in clean)
    nz = sum(1 for i in clean if got[i] != REF[i])
    clip = sum(1 for v in got if abs(v) >= 0.999)
    print(f"{label:<32} طول {len(got)} (مرجع {len(REF)}) · "
          f"أقصى فرق بالمناطق النظيفة {worst:.6f} · "
          f"عيّنات متغيّرة {nz} · مقصوصة {clip}")
    return worst


print(f"مرجع: {len(REF)} عيّنة · مواقع المؤثرات {POS} · طول المؤثر {CLICK_LEN}\n")
report("amix افتراضي (normalize=1)", mixed(""))
report("amix normalize=0", mixed(":normalize=0"))
report("amix normalize=0:dropout=0", mixed(":normalize=0:dropout_transition=0"))

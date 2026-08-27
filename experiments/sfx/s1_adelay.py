"""
S1 — دقة وضع المؤثر: `adelay` بالعيّنة (`S`) مقابل الميلي.

السؤال: هل نقدر نحطّ SFX على **عيّنة** محدَّدة بالضبط؟ لو الميلي هو
السقف، كل مؤثر بيحمل خطأ لحد ٠.٥ms وهاد بيتراكم.

**أرضية القياس أولًا.** الكاشف بيرجّع فهرس أول عيّنة فوق العتبة،
والنقرة نفسها بتوصل العتبة بعد عيّنتين من بدايتها. بدون طرح هالأرضية
كل النتائج بتطلع "+2" وبتبيّن خطأً وهي مضبوطة.
"""
import tools as T

SR = T.SR
BED, CLICK = "/tmp/sfx_bed.wav", "/tmp/sfx_click.wav"
T.silence(BED, 6.0)
T.click(CLICK)

FLOOR = T.impulses(T.pcm(CLICK))[0]      # أرضية الكاشف
print(f"أرضية الكاشف: {FLOOR} عيّنة (بتنطرح من كل قياس)\n")


def place(expr, out="/tmp/sfx_s1.wav"):
    T.run(["-i", BED, "-i", CLICK, "-filter_complex",
           f"[1:a]adelay={expr}[d];[0:a][d]amix=inputs=2:duration=first[a]",
           "-map", "[a]", "-c:a", "pcm_s16le", out])
    got = T.impulses(T.pcm(out))
    return (got[0] - FLOOR) if got else None


# أهداف عدائية: بعيدة عن حدود الميلي قدر الإمكان (نص ميلي = ٢٤ عيّنة)
TARGETS = [48000, 48024, 48023, 72055, 100777, 131093, 199999]
print(f"{'المطلوب':>9} | {'S (عيّنة)':>10} {'خطأ':>5} | {'ms':>12} {'مقاس':>8} {'خطأ':>5}")
es, em = [], []
for t in TARGETS:
    ms = t / SR * 1000
    gs = place(f"{t}S")
    gm = place(f"{ms:.6f}")
    ds, dm = gs - t, gm - t
    es.append(abs(ds)); em.append(abs(dm))
    print(f"{t:>9} | {gs:>10} {ds:>+5} | {ms:>12.6f} {gm:>8} {dm:>+5}")

print(f"\nأقصى خطأ — `S` (عيّنة): {max(es)} عيّنة")
print(f"أقصى خطأ — ميلي عشري : {max(em)} عيّنة")

# وهل الميلي **الصحيح** (زي ما بيكتبه إنسان) بيقرّب؟
print("\nالميلي المقرَّب لعدد صحيح (زي ما بينكتب عادةً):")
for t in (48023, 100777):
    ms_int = round(t / SR * 1000)
    g = place(str(ms_int))
    print(f"  هدف {t} -> كتبنا {ms_int}ms -> وقع {g} (خطأ {g-t:+d} عيّنة"
          f" = {(g-t)/SR*1000:+.2f}ms)")

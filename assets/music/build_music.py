#!/usr/bin/env python3
"""
سرير موسيقي محايد — **تركيب رياضي، بلا أي مصدر خارجي**.

نفس منطق `assets/sfx/build_assets.py`: أي ملف منزّل بيحتاج تحقّقًا
بشريًا من الترخيص، وأي شكّ بيخلّيه غير صالح للاستعمال التجاري. اللي
هون **عمل أصلي للمشروع** — مصدره هالسكربت، وترخيصه ترخيص المستودع.

**وهو سرير تجريبي مش خيارًا فنّيًا.** الهدف تشوف أثر الموسيقى على
الإيقاع والمزج بلا ما تنتظر مقطعًا مرخَّصًا. لريل حقيقي حطّ موسيقاك:

    python -m autoreel.cli in.mp4 --music track.mp3 -o out.mp4

    python assets/music/build_music.py

بيطلّع WAV · 48000Hz · ستيريو · PCM s16le · ذروة ٠.٩٠

---

## اللفّة بلا نقرة — **بالبناء مش بالتلاشي**

الموسيقى بتنلفّ بـ`-stream_loop -1`، يعني آخر عيّنة بتلحقها أول عيّنة
مباشرةً. أي تردّد ما بيكمّل **دورات صحيحة** بطول المقطع بيخلق قفزة
عند نقطة اللف — نقرة مسموعة بتتكرّر كل لفّة.

الحل مش crossfade (بيغيّر المحتوى وبيضل بيقرّب): **كل تردّد بينتقرّب
لأقرب مضاعف صحيح لـ`1/المدة`.** عند مدة ٨ ثواني الشبكة ٠.١٢٥Hz —
أدقّ بكتير من تمييز الأذن، وبتضمن استمرارية القيمة والميل عند اللف
رياضيًا.

نفس المبدأ على مغلّف النبض: تردّده مضاعف صحيح كمان.

الفحص تحت بيقيس القفزة عند نقطة اللف مقابل أكبر فرق داخلي — لو
الأولى مش أصغر بكتير، البناء مكسور.
"""
import math
import os
import struct
import wave

SR = 48000
PEAK = 0.90
DUR = 8.0                       # ثواني — ٤ مضروبات عند ١٢٠ نبضة/دقيقة


def _snap(f, dur):
    """أقرب مضاعف صحيح لـ1/dur — هون بتنولد اللفّة النظيفة."""
    return max(1, round(f * dur)) / dur


def _pad(n, dur, notes, seed_phase=0.0):
    """
    وسادة: كل نوتة + خامسها + أوكتافها بسعات نازلة.

    ولا ضجيج ولا عشوائية: المقطع لازم يكون قابلًا لإعادة الإنتاج
    بالبايت، والعشوائية بتكسر تقريب الشبكة كمان.
    """
    out = [0.0] * n
    for k, base in enumerate(notes):
        for h, amp in ((1.0, 1.0), (2.0, 0.45), (3.0, 0.18), (4.0, 0.08)):
            f = _snap(base * h, dur)
            w = 2 * math.pi * f / SR
            ph = seed_phase + k * 0.7          # إزاحة ثابتة بين النوتات
            for i in range(n):
                out[i] += amp * math.sin(w * i + ph)
    return out


def _pulse(n, dur, hz):
    """مغلّف نبض ناعم — جيب مرفوع، تردّده مضاعف صحيح كمان."""
    f = _snap(hz, dur)
    w = 2 * math.pi * f / SR
    return [0.55 + 0.45 * (0.5 * (1 - math.cos(w * i))) ** 1.6 for i in range(n)]


def build(dur=DUR):
    n = int(SR * dur)
    # لا مينور: A2 · C3 · E3 · A3 — محايد، بلا حسم كبير ولا لون حاد
    notes = [110.0, 130.81, 164.81, 220.0]
    pad = _pad(n, dur, notes)
    env = _pulse(n, dur, 2.0)                  # ١٢٠ نبضة/دقيقة
    mono = [p * e for p, e in zip(pad, env)]

    m = max(abs(x) for x in mono) or 1.0
    mono = [x / m * PEAK for x in mono]

    # ستيريو بإزاحة عيّنات صحيحة — الإزاحة الكسرية بتكسر اللفّة
    d = int(SR * 0.011)
    left = mono
    right = mono[-d:] + mono[:-d]
    return left, right


def check_loop(left):
    """
    القفزة عند نقطة اللف لازم تكون **بحجم قفزة داخلية عادية**.

    لو البناء مكسور بتطلع أكبر بمراتب — وهاي نقرة مسموعة كل لفّة.
    """
    seam = abs(left[0] - left[-1])
    inner = max(abs(left[i + 1] - left[i]) for i in range(0, len(left) - 1, 7))
    return seam, inner


def write(path, left, right):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(
            struct.pack("<hh", int(max(-1, min(1, a)) * 32767),
                        int(max(-1, min(1, b)) * 32767))
            for a, b in zip(left, right)))


if __name__ == "__main__":
    left, right = build()
    seam, inner = check_loop(left)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bed.wav")
    write(out, left, right)
    print(f"{out}  {len(left)} عيّنة · {len(left)/SR:.2f}s")
    print(f"قفزة اللف = {seam:.2e}  ·  أكبر قفزة داخلية = {inner:.2e}")
    if seam > inner:
        raise SystemExit("❌ اللفّة بتنقر — تقريب الشبكة مكسور")
    print("✅ اللفّة مستمرة بالبناء")

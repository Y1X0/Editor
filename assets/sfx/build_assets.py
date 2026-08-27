#!/usr/bin/env python3
"""
توليد أصول المؤثرات الصوتية — **تركيب رياضي، بلا أي مصدر خارجي**.

ليش التركيب مش أصول جاهزة: الشرط كان "ولا أصل مجهول الترخيص". أي ملف
منزّل بيحتاج تحقّقًا بشريًا من الترخيص ما بقدر أعمله، وأي شكّ بيخلّي
الأصل غير صالح للاستعمال التجاري. الملفات المولَّدة هون **عمل أصلي
للمشروع**: مصدرها هالسكربت، وترخيصها ترخيص المستودع، وما في طرف تالت
أصلًا.

وفايدة تانية: **قابلة لإعادة الإنتاج بالبايت**. مولّد عشوائي مزروع
بذرة ثابتة، فإعادة التوليد بتعطي نفس الملف — يعني الأصل نفسه بينفحص
زي أي مخرَج تاني.

    python assets/sfx/build_assets.py

بيطلّع WAV · 48000Hz · ستيريو · PCM s16le · ذروة ٠.٩٠

الذروة ٠.٩٠ مقصودة: مع تطبيع الكلام لـ٠.٧٠ وكسب مؤثر ٠.٢٥ بيصير
المجموع ٠.٧٠ + ٠.٩٠×٠.٢٥ = ٠.٩٢٥ < ١.٠ — يعني ولا عيّنة مقصوصة.
"""
import math
import os
import random
import struct
import wave

SR = 48000
PEAK = 0.90


# ------------------------------------------------------------ لبنات

def _noise(n, seed):
    r = random.Random(seed)
    return [r.uniform(-1.0, 1.0) for _ in range(n)]


def _svf(x, cutoff, q=1.0, mode="band"):
    """
    مرشّح متغيّر الحالة — `cutoff` ممكن تكون قائمة (مسح) أو رقمًا.

    بسيط عمدًا: التركيب لازم يضل مقروءًا، والجودة المطلوبة "مؤثر
    قصير مقنع" مش معالجة استوديو.
    """
    lo = bp = 0.0
    out = []
    for i, s in enumerate(x):
        fc = cutoff[i] if isinstance(cutoff, list) else cutoff
        f = 2.0 * math.sin(math.pi * min(fc, SR * 0.45) / SR)
        hi = s - lo - q * bp
        bp += f * hi
        lo += f * bp
        out.append({"low": lo, "band": bp, "high": hi}[mode])
    return out


def _env(n, attack, decay, curve=2.0):
    """غلاف: صعود قصير ثم هبوط أسّي. `attack`/`decay` بالعيّنات."""
    out = []
    for i in range(n):
        if i < attack:
            a = (i / attack) ** 0.5 if attack else 1.0
        else:
            t = (i - attack) / max(1, decay)
            a = math.exp(-curve * t) if t < 1.0 else 0.0
        out.append(a)
    return out


def _sweep(n, f0, f1, curve=1.0):
    """نغمة بتردد بيمشي من f0 لـf1."""
    out, phase = [], 0.0
    for i in range(n):
        t = (i / n) ** curve
        f = f0 + (f1 - f0) * t
        phase += 2.0 * math.pi * f / SR
        out.append(math.sin(phase))
    return out


def _mul(a, b):
    return [x * y for x, y in zip(a, b)]


def _add(*sigs):
    n = max(len(s) for s in sigs)
    out = [0.0] * n
    for s in sigs:
        for i, v in enumerate(s):
            out[i] += v
    return out


def _fade_out(x, ms=4):
    """تلاشي بالآخر — بلاه بيطلع طقّة عند نهاية الملف."""
    k = int(SR * ms / 1000)
    for i in range(min(k, len(x))):
        x[len(x) - 1 - i] *= i / k
    return x


def _normalize(x, peak=PEAK):
    m = max((abs(v) for v in x), default=0.0)
    return [v * peak / m for v in x] if m else x


# ------------------------------------------------------------ الأصول

def tick():
    """نقرة عالية قصيرة جدًا — لتمييز كلمة."""
    n = int(SR * 0.022)
    src = _svf(_noise(n, 11), 5200.0, q=0.6, mode="band")
    return _mul(src, _env(n, int(SR * 0.0004), n, curve=7.0))


def pop():
    """بلوب مرتفع النبرة بهبوط سريع — لظهور كابشن."""
    n = int(SR * 0.085)
    tone = _sweep(n, 880.0, 360.0, curve=0.55)
    body = _mul(tone, _env(n, int(SR * 0.001), n, curve=5.0))
    click = _mul(_svf(_noise(n, 23), 3000.0, q=0.8, mode="band"),
                 _env(n, int(SR * 0.0003), int(SR * 0.004), curve=6.0))
    return _add(body, [v * 0.35 for v in click])


def whoosh():
    """هواء ماشي — لحدّ المقطع أو الزوم."""
    n = int(SR * 0.38)
    # مسح النطاق: بيطلع وبينزل، وهاد اللي بيعطي إحساس المرور
    cut = [420.0 + 3600.0 * math.sin(math.pi * (i / n)) for i in range(n)]
    band = _svf(_noise(n, 37), cut, q=0.55, mode="band")
    env = [math.sin(math.pi * (i / n)) ** 1.6 for i in range(n)]
    return _mul(band, env)


def impact():
    """ضربة منخفضة — للتأكيد أو أول الريل."""
    n = int(SR * 0.42)
    boom = _mul(_sweep(n, 165.0, 42.0, curve=0.42),
                _env(n, int(SR * 0.002), n, curve=3.6))
    crack = _mul(_svf(_noise(n, 53), 1800.0, q=0.9, mode="band"),
                 _env(n, int(SR * 0.0005), int(SR * 0.05), curve=5.0))
    return _add(boom, [v * 0.28 for v in crack])


def riser():
    """صعود — قبل الانتقال أو آخر مقطع."""
    n = int(SR * 1.15)
    cut = [300.0 + 5200.0 * (i / n) ** 2.1 for i in range(n)]
    air = _svf(_noise(n, 71), cut, q=0.5, mode="band")
    tone = _mul(_sweep(n, 220.0, 1500.0, curve=2.2),
                [0.30 * (i / n) ** 2.4 for i in range(n)])
    env = [(i / n) ** 1.7 for i in range(n)]
    return _add(_mul(air, env), tone)


ASSETS = {"tick": tick, "pop": pop, "whoosh": whoosh,
          "impact": impact, "riser": riser}


def write_wav(path, mono):
    """ستيريو بنسختين متطابقتين — الشكل اللي المسار بيتوقّعه."""
    data = _fade_out(_normalize(list(mono)))
    frames = bytearray()
    for v in data:
        s = max(-32768, min(32767, int(round(v * 32767))))
        frames += struct.pack("<hh", s, s)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    return len(data)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    for name, fn in ASSETS.items():
        p = os.path.join(here, f"{name}.wav")
        n = write_wav(p, fn())
        print(f"  {name:<8} {n/SR:6.3f}s  {os.path.getsize(p):>7} بايت  {p}")


if __name__ == "__main__":
    main()

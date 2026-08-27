"""
أزمنة النقرات من مسار الصوت.

بنرجّع زمن **قمة** كل نقرة مش لحظة تجاوز عتبة الصعود: AAC تحويل متداخل
النوافذ، فبينشر طاقة النقرة على ~٤٢ms وبيقدّم لحظة الصعود بشكل متغيّر.
القمة أثبت.

والعتبة نسبية لأقصى قيمة بالملف مش مطلقة — أول محاولة استعملت ٠.٢٥
مطلقة وقمة الإشارة كانت ٠.١٣٧، فرجعت **صفر نبضات من ٢٠**.
"""
import array
import subprocess

from .source import SR


def _samples(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1",
         "-ar", str(SR), "-f", "s16le", "-"],
        capture_output=True).stdout
    a = array.array("h")
    a.frombytes(raw)
    return a


def click_times(path, rel=0.35, gap_ms=120):
    """أزمنة قمم النقرات بالثواني."""
    a = _samples(path)
    if not a:
        return []
    lim = max(abs(v) for v in a) * rel
    out, i, n = [], 0, len(a)
    gap = int(SR * gap_ms / 1000)
    while i < n:
        if abs(a[i]) > lim:
            j, best, bi, quiet = i, abs(a[i]), i, 0
            while j < n and quiet < gap:
                if abs(a[j]) > lim:
                    quiet = 0
                    if abs(a[j]) > best:
                        best, bi = abs(a[j]), j
                else:
                    quiet += 1
                j += 1
            out.append(bi / SR)
            i = j
        else:
            i += 1
    return out


def drift_ms(got, want):
    """
    انزياح كل نقرة بالميلي ثانية.

    بيرفع لو الأعداد اختلفت: مقارنة أول `min(len)` بتخبّي نقرة ضايعة
    وبتطلّع "انزياح صفر" على مخرَج ناقص.
    """
    if len(got) != len(want):
        raise AssertionError(f"عدد النقرات {len(got)} والمتوقَّع {len(want)}")
    return [(g - w) * 1000 for g, w in zip(got, want)]

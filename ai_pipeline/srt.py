"""SRT + النص المصدر ──► `Alignment`.

**مش قارئ SRT عامًّا.** `autoreel.transcribe.from_srt` بتقرا SRT وبترجّع
كلمات بتوقيت — وهاد شي تاني: هون المحاذاة لازم تكون **على النص المصدر**،
يعني عدد الكلمات ونصّها لازم يطابقا `source.tokenize()` بالضبط،
وإلا `check_alignment_matches_source` بترفضها بمرحلة لاحقة.

فالمسؤولية الحقيقية هون هي **الربط والتحقّق**، مش التقطيع:

    كلمات الـSRT  ==  كلمات المصدر ؟   ← لأ: فشل صريح، بلا محاولة تقريب
    توقيت الجملة  ──► توقيت كل كلمة    ← توزيع متساوٍ، معلَن إنه تقريبي

الفشل الصريح مقصود: SRT ما بيطابق النص يعني إما نصّ غلط أو ترجمة
تانية، والتقريب بينتج فيديو نصّه مزحلق عن صوته — وهاد بينكتشف بعد
الرفع مش قبله.

**التوقيت الناتج تقريبي وبقصد.** التوزيع المتساوي داخل الجملة بيعطي
حدود جُمل صحيحة وحدود كلمات تقريبية. وهاد بيكفّي لأن `quantize` بتاخد
حدود **المقاطع** (بداية أول كلمة ونهاية آخر وحدة)، والوكيل بيقسم عند
حدود معنى مش بنص جملة. محاذاة قسرية حقيقية بتيجي مع Whisper.
"""
from __future__ import annotations

import re
from pathlib import Path

from .errors import AlignmentError
from .models.alignment import Alignment, Word

#: سطر توقيت SRT. الفاصلة والنقطة الاتنتان مقبولتان (SRT مقابل WebVTT).
_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*"
                 r"(\d+):(\d+):(\d+)[,.](\d+)")

#: أقصر مدة كلمة بتنقبل بعد التقريب لجزء الألف. أقصر منها بيعني كتلة
#: فيها كلمات أكتر من وقتها، و`Word` بترفض `end <= start` على أي حال —
#: بس برسالة عن كلمة، مش عن الكتلة اللي سبّبتها.
_MIN_WORD_S = 0.001


def _seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_cues(text: str) -> list[tuple[float, float, list[str]]]:
    """`[(بداية, نهاية, كلمات)]` بترتيب الملف.

    **التقسيم على السطر الفاضي قبل قراءة أي كتلة** — مش regex وحدة
    بتمتد عبر الملف. الشكل التاني إله فخّ موثَّق بالمحرر: كتلة نصّها
    فاضي بتبلع سطر الرقم وسطر التوقيت للكتلة اللي بعدها، فبيصيروا
    «كلمات» (`2`, `00:00:02,000`, `-->`) وبيدخلوا بالكابشن.
    """
    out = []
    for block in re.split(r"\n[ \t]*\n", text):
        lines = block.splitlines()
        m = i = None
        for i, ln in enumerate(lines):
            if (m := _TS.search(ln)):
                break
        if not m:
            continue                       # كتلة بلا سطر توقيت — تجاهلها
        g = m.groups()
        a, b = _seconds(*g[:4]), _seconds(*g[4:])
        words = " ".join(lines[i + 1:]).split()
        if not words:
            continue                       # كتلة بلا نص
        if b <= a:
            raise AlignmentError(
                f"كتلة SRT بتبدأ {a:.3f}s وبتنتهي {b:.3f}s — مدة غير صالحة")
        out.append((a, b, words))
    if not out:
        raise AlignmentError("ولا كتلة صالحة بالـSRT")
    for (a1, b1, _), (a2, _, _) in zip(out, out[1:]):
        if a2 < b1:
            raise AlignmentError(
                f"كتل SRT متداخلة: وحدة بتنتهي {b1:.3f}s واللي بعدها "
                f"بتبدأ {a2:.3f}s")
    return out


def alignment_from_srt(path: str | Path, tokens: tuple[str, ...],
                       *, method: str = "srt") -> Alignment:
    """`Alignment` على **كلمات المصدر**، أو `AlignmentError`.

    الفهرس `i` هو موقع الكلمة بالنص المصدر — وهاد اللي بيخلي
    `word_start`/`word_end` بالمقاطع تعني شيئًا مستقرًّا.
    """
    p = Path(path)
    if not p.is_file():
        raise AlignmentError(f"ملف SRT مفقود: {p}")
    cues = parse_cues(p.read_text(encoding="utf-8"))

    flat = [w for _, _, ws in cues for w in ws]
    if len(flat) != len(tokens):
        raise AlignmentError(
            f"الـSRT فيه {len(flat)} كلمة والمصدر {len(tokens)} — "
            f"المحاذاة لازم تكون على المصدر، ولا كلمة بتنزاد ولا بتنقص")
    for i, (got, want) in enumerate(zip(flat, tokens)):
        if got != want:
            raise AlignmentError(
                f"كلمة {i}: الـSRT {got!r} والمصدر {want!r} — "
                f"ولا حرف بيتغيّر (§19)")

    words, i = [], 0
    for a, b, ws in cues:
        step = (b - a) / len(ws)
        for j, w in enumerate(ws):
            s, e = round(a + j * step, 3), round(a + (j + 1) * step, 3)
            if e - s < _MIN_WORD_S:
                raise AlignmentError(
                    f"كتلة SRT [{a:.3f}, {b:.3f}] فيها {len(ws)} كلمة — "
                    f"بتطلع {step * 1000:.1f}ms للكلمة، أقصر من أن تنمثّل")
            words.append(Word(i=i, text=w, start=s, end=e))
            i += 1
    return Alignment(method=method, words=tuple(words))

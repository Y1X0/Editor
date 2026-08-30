"""SRT من أي أداة تلقائية  ──►  توقيت على **نصّك المصدر بالضبط**.

```bash
python tools/srt_transfer.py --script script.txt --asr capcut.srt -o words.srt
```

**ليش موجودة:** المسار بيقارن نصّ العقد بالمصدر **بايت-بايت** ويرمي
`TextIntegrityError` على أي اختلاف — قرار مقصود يمنع النموذج من
تغيير كلامك. بس أدوات التفريغ التلقائي بتكتب النص بصياغتها: بتشيل
التشكيل، بتبدّل الترقيم، بتفصل «الـAI» أو بتدمج «ما» مع اللي بعدها.
فملف صحيح تمامًا بينرفض لأسباب إملائية.

الحل: **التوقيت بيتنقل، والنص ما بينلمس.** بنحاذي تسلسل كلمات
التفريغ على تسلسل كلمات المصدر بمحاذاة عامة (Needleman–Wunsch) على
صيغة مطبَّعة، وبناخد التوقيت فقط. النص المكتوب بالمخرَج هو **كلمة
المصدر**، لا كلمة الأداة.

⚠️ **أداة مساعدة، برّا الحزمة.** المسار ما بينادي هالملف.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_pipeline.source import tokenize                          # noqa: E402
from ai_pipeline.srt import parse_cues                           # noqa: E402

#: تشكيل عربي + تطويل — بتنشال قبل المقارنة، وبتضل بالنص المكتوب.
_MARKS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def norm(w: str) -> str:
    """صيغة المقارنة: بلا تشكيل ولا ترقيم، وألف/ياء/تاء موحّدة.

    **المقارنة فقط** — المخرَج بيحمل كلمة المصدر كما هي.
    """
    w = unicodedata.normalize("NFKC", w)
    w = _MARKS.sub("", w)
    w = re.sub(r"[^\w؀-ۿ]", "", w)
    w = (w.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
          .replace("ى", "ي").replace("ة", "ه"))
    return w.lower()


def sim(a: str, b: str) -> float:
    """تشابه ٠–١ بين كلمتين مطبَّعتين (نسبة أطول بادئة/لاحقة مشتركة)."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    m = min(len(a), len(b))
    pre = next((i for i in range(m) if a[i] != b[i]), m)
    suf = next((i for i in range(m - pre) if a[-1 - i] != b[-1 - i]), m - pre)
    return (pre + suf) / max(len(a), len(b))


def align(src: list[str], asr: list[str]) -> list[int | None]:
    """لكل كلمة مصدر: فهرس كلمة التفريغ اللي بتقابلها، أو `None`.

    Needleman–Wunsch عام: بيسمح بحذف وإضافة، فكلمة زايدة أو ناقصة
    بالتفريغ ما بتزحلق كل اللي بعدها — وهاد بالضبط الانحدار اللي
    بيصير مع أي مطابقة تسلسلية ساذجة.
    """
    n, m = len(src), len(asr)
    GAP = -0.6
    S = [[0.0] * (m + 1) for _ in range(n + 1)]
    B = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        S[i][0] = S[i - 1][0] + GAP
        B[i][0] = 1
    for j in range(1, m + 1):
        S[0][j] = S[0][j - 1] + GAP
        B[0][j] = 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d = S[i - 1][j - 1] + (2 * sim(src[i - 1], asr[j - 1]) - 0.4)
            u, l = S[i - 1][j] + GAP, S[i][j - 1] + GAP
            best = max(d, u, l)
            S[i][j] = best
            B[i][j] = 0 if best == d else (1 if best == u else 2)
    out: list[int | None] = [None] * n
    i, j = n, m
    while i > 0 and j > 0:
        if B[i][j] == 0:
            if sim(src[i - 1], asr[j - 1]) > 0.34:
                out[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif B[i][j] == 1:
            i -= 1
        else:
            j -= 1
    return out


def ts(x: float) -> str:
    return (f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:"
            f"{int(x % 60):02d},{round(x % 1 * 1000):03d}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--script", type=Path, required=True)
    ap.add_argument("--asr", type=Path, required=True,
                    help="SRT من أي أداة — الصياغة ما بتهمّ")
    ap.add_argument("-o", "--out", type=Path, required=True)
    a = ap.parse_args(argv)

    src = list(tokenize(a.script.read_text(encoding="utf-8")))
    cues = parse_cues(a.asr.read_text(encoding="utf-8"))

    # كلمة التفريغ = (نص, بداية, نهاية). لو الـcue فيه أكتر من كلمة
    # بنوزّع زمنه عليهن — بس هاد بيصير جوّا cue قصير، مش عبر الملف.
    asr: list[tuple[str, float, float]] = []
    for s, e, ws in cues:
        if not ws:
            continue
        step = (e - s) / len(ws)
        for k, w in enumerate(ws):
            asr.append((w, s + k * step, s + (k + 1) * step))

    idx = align([norm(w) for w in src], [norm(w) for w, _, _ in asr])
    hit = sum(1 for x in idx if x is not None)
    print(f"مصدر {len(src)} كلمة · تفريغ {len(asr)} كلمة · "
          f"انطابقت {hit} ({100 * hit / len(src):.0f}٪)", file=sys.stderr)
    if hit < 0.6 * len(src):
        raise SystemExit(
            f"المطابقة ضعيفة ({hit}/{len(src)}) — تأكّد إن الـSRT لنفس "
            f"التسجيل ونفس النص.")

    # الكلمات اللي ما انطابقت بتاخد وقتًا مُقحَمًا بين جارتيها المطابقتين
    times: list[tuple[float, float] | None] = [
        (asr[x][1], asr[x][2]) if x is not None else None for x in idx]
    for i, t in enumerate(times):
        if t is not None:
            continue
        p = next((j for j in range(i - 1, -1, -1) if times[j]), None)
        q = next((j for j in range(i + 1, len(times)) if times[j]), None)
        if p is None and q is None:
            raise SystemExit("ولا كلمة انطابقت")
        lo = times[p][1] if p is not None else max(0.0, times[q][0] - 0.4)
        hi = times[q][0] if q is not None else lo + 0.4
        gap = max(1, (q if q is not None else len(times)) - (p if p is not None else -1) - 1)
        k = i - ((p if p is not None else -1) + 1)
        w = (hi - lo) / gap
        times[i] = (lo + k * w, lo + (k + 1) * w)

    # **رتابة صارمة بلا تداخل.** `parse_cues` بترمي على أي كتلة
    # بتبدأ قبل ما تنتهي اللي قبلها، و`quantize` بتقصّ التداخل —
    # فأي تقريب بالميلي لازم ينحلّ هون لا هناك.
    fixed: list[tuple[float, float]] = []
    prev_end = 0.0
    for s, e in times:                                   # type: ignore[misc]
        s = max(s, prev_end)
        e = max(e, s + 0.12)
        fixed.append((round(s, 3), round(e, 3)))
        prev_end = round(e, 3)
    a.out.write_text("\n".join(
        f"{i + 1}\n{ts(s)} --> {ts(e)}\n{w}\n"
        for i, (w, (s, e)) in enumerate(zip(src, fixed))), encoding="utf-8")
    print(f"{a.out}: {len(src)} كلمة بتوقيتها — والنص نصّك بالضبط")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

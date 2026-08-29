"""§15 — هل الخط بيقدر يرسم النص أصلًا؟

**السبب من قياس، مش من احتياط:** `Tajawal` ما فيها علامات الوقف
القرآنية ولا الألف الخنجرية (U+0670)، فبترسم **دوائر منقّطة** مكانهن.
النص بيطلع «شغّال» — بلا استثناء وبلا تحذير من Pillow ولا من ffmpeg —
وبس عين بتقرا عربي بتعرف إنه غلط. وبنصّ ديني هاد أخطر شكل خلل:
مخرَج بيبيّن سليمًا وهو مش سليم.

Pillow ما بتعطي وصولًا للـcmap (فحصنا `dir()` على `FreeTypeFont`
وعلى كائن `_imagingft`)، فمنقراه من الملف. صيغتان بتغطّيا الخطوط
الحديثة كلها عمليًا: 4 (BMP) و12 (كامل).
"""
from __future__ import annotations

import struct
import unicodedata
from functools import lru_cache
from pathlib import Path

from ..errors import TypographyError


@lru_cache(maxsize=8)
def covered_codepoints(font_path: str) -> frozenset[int]:
    """كل النقاط الرمزية اللي الخط بيغطّيها، من جدول `cmap`."""
    data = Path(font_path).read_bytes()
    if len(data) < 12:
        raise TypographyError(f"ملف خط غير صالح (قصير): {font_path}")
    tag = data[:4]
    if tag == b"ttcf":                       # مجموعة خطوط — خُد الأول
        (off,) = struct.unpack_from(">I", data, 12)
    elif tag in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
        off = 0
    else:
        raise TypographyError(
            f"صيغة خط غير مدعومة {tag!r}: {font_path} — المتوقَّع TTF/OTF")

    num_tables = struct.unpack_from(">H", data, off + 4)[0]
    cmap_off = None
    for i in range(num_tables):
        rec = off + 12 + i * 16
        if data[rec:rec + 4] == b"cmap":
            cmap_off = struct.unpack_from(">I", data, rec + 8)[0]
            break
    if cmap_off is None:
        raise TypographyError(f"الخط بلا جدول cmap: {font_path}")

    n_sub = struct.unpack_from(">H", data, cmap_off + 2)[0]
    out: set[int] = set()
    for i in range(n_sub):
        _pid, _eid, sub_off = struct.unpack_from(">HHI", data, cmap_off + 4 + i * 8)
        out |= _read_subtable(data, cmap_off + sub_off)
    if not out:
        raise TypographyError(
            f"ما قدرت أقرا ولا جدول cmap مفهوم من {font_path} "
            f"(المدعوم: صيغة 4 و12)")
    return frozenset(out)


def _read_subtable(data: bytes, off: int) -> set[int]:
    fmt = struct.unpack_from(">H", data, off)[0]
    out: set[int] = set()
    if fmt == 4:
        seg2 = struct.unpack_from(">H", data, off + 6)[0]
        n = seg2 // 2
        ends = struct.unpack_from(f">{n}H", data, off + 14)
        starts = struct.unpack_from(f">{n}H", data, off + 16 + seg2)
        deltas = struct.unpack_from(f">{n}h", data, off + 16 + seg2 * 2)
        ro_off = off + 16 + seg2 * 3
        ranges = struct.unpack_from(f">{n}H", data, ro_off)
        for i in range(n):
            if starts[i] == 0xFFFF:
                continue
            for c in range(starts[i], ends[i] + 1):
                if ranges[i] == 0:
                    g = (c + deltas[i]) & 0xFFFF
                else:
                    gi = ro_off + i * 2 + ranges[i] + (c - starts[i]) * 2
                    if gi + 2 > len(data):
                        continue
                    g = struct.unpack_from(">H", data, gi)[0]
                    if g:
                        g = (g + deltas[i]) & 0xFFFF
                if g:
                    out.add(c)
    elif fmt == 12:
        n = struct.unpack_from(">I", data, off + 12)[0]
        for i in range(n):
            s, e, _g = struct.unpack_from(">III", data, off + 16 + i * 12)
            out.update(range(s, min(e, 0x10FFFF) + 1))
    return out


# محارف الاتجاه والوصل ما إلهن رسم — غيابهن مش خللًا
_INVISIBLE = {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x202A, 0x202B,
              0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069,
              0x0640}


def missing_codepoints(font_path: str, text: str) -> list[int]:
    """النقاط الرمزية اللي بالنص وما بيغطّيها الخط، بترتيب أول ظهور."""
    cov = covered_codepoints(font_path)
    seen, out = set(), []
    for ch in text:
        c = ord(ch)
        if c in seen or c in cov or c in _INVISIBLE or ch.isspace():
            continue
        seen.add(c)
        out.append(c)
    return out


def check_font_can_render(font_path: str | Path, texts) -> None:
    """بيرمي `TypographyError` لو الخط ناقصه محرف من أي نص.

    بيتنادى **قبل** الرندر: اكتشافه بعد الترميز يعني إعادة تشغيلة
    كاملة، واكتشافه بعد النشر يعني نصًّا دينيًا معروضًا غلط.
    """
    p = Path(font_path)
    if not p.is_file():
        raise TypographyError(f"الخط مش موجود: {p}")
    missing: dict[int, str] = {}
    for t in texts:
        for c in missing_codepoints(str(p), t):
            missing.setdefault(c, t)
    if missing:
        rows = "\n".join(
            f"      U+{c:04X}  {unicodedata.name(chr(c), '؟'):<38}  «{missing[c][:28]}»"
            for c in sorted(missing))
        raise TypographyError(
            f"الخط {p.name} ما بيغطّي {len(missing)} محرفًا من النص — "
            f"رح ينرسموا دوائر منقّطة بلا أي خطأ:\n{rows}")

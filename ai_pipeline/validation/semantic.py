"""التحقّق الدلالي — اللي الـschema ما بتقدر تشوفه.

قاعدة: الفحوصات اللي صارت **مستحيلة** بعد إصلاح الـschema مش موجودة
هون. ما منبني مدقّقًا لحالة ما بتقدر تصير.
"""
from __future__ import annotations

from pathlib import Path

from ..errors import AlignmentError, AssetError, ContractError, TextIntegrityError
from ..models.alignment import Alignment
from ..models.assets import AssetsContract
from ..models.segments import SegmentsContract
from ..models.typography import TypographyContract
from ..source import slice_text


def check_text_integrity(
    segments: SegmentsContract, tokens: tuple[str, ...]
) -> None:
    """§19 — ولا حرف بيتغيّر.

    `text_arabic` بالعقد صدى للقراءة البشرية. بينتقارن **بايت-بايت**
    مع شريحة المصدر، وأي اختلاف بيفشل بلا محاولة تصليح.
    """
    for s in segments.segments:
        if s.word_end > len(tokens):
            raise ContractError(
                f"مقطع {s.segment_id}: مدى [{s.word_start}, {s.word_end}) "
                f"خارج نص من {len(tokens)} كلمة"
            )
        want = slice_text(tokens, s.word_start, s.word_end)
        if s.text_arabic != want:
            raise TextIntegrityError(
                f"مقطع {s.segment_id}: النص لا يطابق المصدر عند الكلمات "
                f"{s.word_start}–{s.word_end}\n"
                f"  المصدر : {want!r}\n"
                f"  العقد  : {s.text_arabic!r}"
            )


def check_coverage(segments: SegmentsContract, tokens: tuple[str, ...]) -> None:
    """ولا كلمة من المصدر بتضيع بلا ما تنعرض.

    الفجوات بين المقاطع مسموحة **بصريًا** (وقت بلا نص)، بس كلمة
    مصدرية ما بتظهر بولا مقطع يعني حذف صامت — وهاد ممنوع.
    """
    shown = set()
    for s in segments.segments:
        shown.update(range(s.word_start, s.word_end))
    missing = sorted(set(range(len(tokens))) - shown)
    if missing:
        sample = ", ".join(repr(tokens[i]) for i in missing[:6])
        raise TextIntegrityError(
            f"{len(missing)} كلمة من المصدر ما بتظهر بولا مقطع: {sample}"
            + (" …" if len(missing) > 6 else "")
        )


def check_alignment_covers(
    segments: SegmentsContract, alignment: Alignment
) -> None:
    n = len(alignment.words)
    for s in segments.segments:
        if s.word_end > n:
            raise AlignmentError(
                f"مقطع {s.segment_id}: مدى [{s.word_start}, {s.word_end}) "
                f"خارج محاذاة من {n} كلمة"
            )


def check_alignment_matches_source(
    alignment: Alignment, tokens: tuple[str, ...]
) -> None:
    """المحاذاة لازم تكون على **نص المصدر**، مش على نسخ Whisper."""
    if len(alignment.words) != len(tokens):
        raise AlignmentError(
            f"المحاذاة فيها {len(alignment.words)} كلمة والمصدر "
            f"{len(tokens)} — المحاذاة لازم تكون على المصدر"
        )
    for w, t in zip(alignment.words, tokens):
        if w.text != t:
            raise AlignmentError(
                f"كلمة {w.i}: المحاذاة {w.text!r} والمصدر {t!r}"
            )


def check_assets(
    assets: AssetsContract, segments: SegmentsContract, root: Path
) -> None:
    want = {s.segment_id for s in segments.segments}
    have = {a.segment_id for a in assets.assets}
    if missing := sorted(want - have):
        raise AssetError(f"مقاطع بلا أصل: {missing}")
    if extra := sorted(have - want):
        raise AssetError(f"أصول لمقاطع مش موجودة: {extra}")
    for a in assets.assets:
        p = a.file_path if a.file_path.is_absolute() else root / a.file_path
        if not p.is_file():
            raise AssetError(f"مقطع {a.segment_id}: الأصل مش موجود — {p}")


def check_typography(
    typo: TypographyContract, segments: SegmentsContract, theme_id: str
) -> None:
    if typo.theme != theme_id:
        raise ContractError(
            f"الـtypography بتشير لـtheme {typo.theme!r} والمشروع {theme_id!r}"
        )
    want = {s.segment_id for s in segments.segments}
    have = {s.segment_id for s in typo.segments}
    if missing := sorted(want - have):
        raise ContractError(f"مقاطع بلا typography: {missing}")
    if extra := sorted(have - want):
        raise ContractError(f"typography لمقاطع مش موجودة: {extra}")

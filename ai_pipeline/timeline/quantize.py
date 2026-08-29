"""المُكمِّم — **المكان الوحيد بالمشروع اللي بيحوّل ثواني لإطارات**.

دالة نقية: بتاخد عقودًا وبترجّع `Timeline`. ولا قراءة قرص ولا نداء
ffmpeg. كل رقم بيدخل تعبير فلتر بعدين بيطلع من هون.

ليش مكان واحد: لو كل مستهلك قرّب لحاله (قصّ الأصل، ظهور النص، حدّ
الـtimeline) بتصير تلات تقريبات مستقلة بتنزاح عن بعضها، والانزياح
بيتراكم بصمت.
"""
from __future__ import annotations

from ..errors import AssetError, TimelineError
from ..models.alignment import Alignment
from ..models.assets import AssetsContract
from ..models.project import Output
from ..models.segments import SegmentsContract
from ..models.timeline import Span, Timeline


def quantize(
    output: Output,
    segments: SegmentsContract,
    alignment: Alignment,
    assets: AssetsContract,
    audio_duration: float,
) -> Timeline:
    """`audio_duration` **مقيسة** من الملف، ما بتنخزّن بولا عقد."""
    fps = output.fps
    if audio_duration <= 0:
        raise TimelineError(f"مدة صوت غير صالحة: {audio_duration}")
    total_frames = round(audio_duration * fps)
    if total_frames < 1:
        raise TimelineError(
            f"الصوت أقصر من إطار واحد: {audio_duration}s عند {fps}fps"
        )

    # ── الـspans النصّية ──────────────────────────────────────────────
    raw: list[tuple[int, int, int]] = []
    for s in segments.segments:
        t0, t1 = alignment.span_time(s.word_start, s.word_end)
        f0, f1 = round(t0 * fps), round(t1 * fps)
        if f1 <= f0:
            raise TimelineError(
                f"مقطع {s.segment_id}: أقصر من إطار عند {fps}fps "
                f"({t0:.3f}–{t1:.3f}s) — دمجه بجاره أو زوّد الـfps"
            )
        raw.append((s.segment_id, f0, f1))

    # قصّ التداخل: كابشن واحد بيبيّن بالمرة الوحدة. Whisper بيرجّع
    # تداخلًا جزئيًا بين كلمتين، وهاد بينتقل للمقاطع. القصّ هون قرار
    # عرض معلَن — مش إخفاء خطأ: المصدر بيضل كما هو بالمحاذاة.
    text: list[Span] = []
    for k, (sid, f0, f1) in enumerate(raw):
        if k + 1 < len(raw):
            f1 = min(f1, raw[k + 1][1])
        f1 = min(f1, total_frames)
        if f1 <= f0:
            raise TimelineError(
                f"مقطع {sid}: انطمس بالكامل بعد قصّ التداخل "
                f"[{f0}, {f1}) — المقاطع متلاصقة أكتر من إطار"
            )
        text.append(Span(segment_id=sid, f_start=f0, f_end=f1))

    # ── الـspans البصرية: بتغطّي [0, total_frames) كاملة (F7) ─────────
    cuts = [0] + [s.f_start for s in text[1:]] + [total_frames]
    for a, b in zip(cuts, cuts[1:]):
        if b <= a:
            raise TimelineError(f"حدّ بصري غير متزايد: {a} -> {b}")
    visual = tuple(
        Span(segment_id=text[i].segment_id, f_start=cuts[i], f_end=cuts[i + 1])
        for i in range(len(text))
    )

    # ── الأصول: هل بتكفّي المدى المطلوب؟ ─────────────────────────────
    in_frame: dict[int, int] = {}
    for sp in visual:
        a = assets.by_segment(sp.segment_id)
        f_in = round(a.in_point * fps)
        avail = int((a.probe.duration - a.in_point) * fps)
        if avail < sp.n_frames:
            raise AssetError(
                f"مقطع {sp.segment_id}: الأصل بيعطي {avail} إطار من "
                f"{sp.n_frames} مطلوبة (مدة {a.probe.duration}s، "
                f"in_point {a.in_point}s عند {fps}fps)"
            )
        in_frame[sp.segment_id] = f_in

    return Timeline(
        fps=fps,
        sample_rate=output.sample_rate,
        total_frames=total_frames,
        visual_spans=visual,
        text_spans=tuple(text),
        asset_in_frame=in_frame,
    )

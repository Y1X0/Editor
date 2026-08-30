"""المُكمِّم — **المكان الوحيد بالمشروع اللي بيحوّل ثواني لإطارات**.

دالة نقية: بتاخد عقودًا وبترجّع `Timeline`. ولا قراءة قرص ولا نداء
ffmpeg. كل رقم بيدخل تعبير فلتر بعدين بيطلع من هون.

ليش مكان واحد: لو كل مستهلك قرّب لحاله (قصّ الأصل، ظهور النص، حدّ
الـtimeline) بتصير تلات تقريبات مستقلة بتنزاح عن بعضها، والانزياح
بيتراكم بصمت.
"""
from __future__ import annotations

from typing import Sequence

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
    shots: Sequence[tuple[int, int]] | None = None,
) -> Timeline:
    """`audio_duration` **مقيسة** من الملف، ما بتنخزّن بولا عقد.

    ## `shots` — فصل اللقطة عن المقطع النصّي

    `[(segment_id, f_end), …]` مرتّبة، بتبدأ ضمنيًا من الإطار صفر
    وبتنتهي عند `total_frames`. `segment_id` بيقول **أي أصل** تعرض
    اللقطة، والحدود بتيجي من المترجم لا من هون.

    **`None` بتعطي سلوك اليوم بالضبط**: لقطة لكل مقطع، حدودها بدايات
    النصوص. وهاد شرط الترحيل — والحالة القديمة مش فرعًا خاصًّا، هي
    نفس الشيفرة عند خطة تافهة.

    ### ليش هالتوقيع بالذات

    كان السطر `cuts = [0] + [s.f_start for s in text[1:]] + [total_frames]`
    بيخلق **تقابلًا واحد-لواحد** بين مدى النص ومدى الصورة. فكان
    مستحيلًا التعبير عن لقطة تمتد على تلات جمل، أو تلات لقطات داخل
    جملة. عدد اللقطات = عدد المقاطع، دائمًا.

    عقد `Timeline` نفسه **ما كان بيفرض** هالتقابل — الشرط الوحيد إن
    الـspans البصرية متلاصقة وبتغطّي الشريط، وإن كل مقطع نصّي إله span
    بصري بمعرّفه. فالتقييد كان هون وحده، وهاد السطر شاله.

    ⚠️ **حدّ معروف:** `asset_in_frame` مفتاحه `segment_id`، فلقطتان على
    نفس المقطع بتتشاركا نفس نقطة البدء بالأصل. نافذة مستقلة لكل لقطة
    بتلزمها حقل بعقد `Timeline` — قرار منفصل، وما انتاخد هون.
    """
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
    if shots is None:
        # السلوك التاريخي: لقطة لكل مقطع، حدودها بدايات النصوص.
        ends = [sp.f_start for sp in text[1:]] + [total_frames]
        plan = [(sp.segment_id, e) for sp, e in zip(text, ends)]
    else:
        plan = [(int(sid), int(end)) for sid, end in shots]
        if not plan:
            raise TimelineError("خطة لقطات فاضية")
        known = {s.segment_id for s in segments.segments}
        bad = sorted({sid for sid, _ in plan} - known)
        if bad:
            raise TimelineError(f"لقطات بتشير لمقاطع مش موجودة: {bad}")
        if plan[-1][1] != total_frames:
            raise TimelineError(
                f"آخر لقطة لازم تنتهي عند {total_frames}، انتهت عند "
                f"{plan[-1][1]} — الشريط البصري لازم يغطّي الصوت كاملًا")

    cuts = [0] + [end for _, end in plan]
    for a, b in zip(cuts, cuts[1:]):
        if b <= a:
            raise TimelineError(f"حدّ بصري غير متزايد: {a} -> {b}")
    visual = tuple(
        Span(segment_id=sid, f_start=cuts[i], f_end=cuts[i + 1])
        for i, (sid, _) in enumerate(plan)
    )

    # ── الأصول: هل بتكفّي المدى المطلوب؟ ─────────────────────────────
    # **المدى المطلوب لكل أصل = مجموع لقطاته المتتالية**، لا أطولها:
    # لقطتان متتاليتان على نفس المقطع بتكمّلا نفس النافذة، فالكفاية
    # بتتقاس على المجموع وإلا مرق أصل أقصر من المطلوب.
    need: dict[int, int] = {}
    prev_sid = None
    for sp in visual:
        if sp.segment_id == prev_sid:
            need[sp.segment_id] = need[sp.segment_id] + sp.n_frames
        else:
            need[sp.segment_id] = max(need.get(sp.segment_id, 0), sp.n_frames)
        prev_sid = sp.segment_id

    in_frame: dict[int, int] = {}
    for sp in visual:
        a = assets.by_segment(sp.segment_id)
        f_in = round(a.in_point * fps)
        avail = int((a.probe.duration - a.in_point) * fps)
        if avail < need[sp.segment_id]:
            raise AssetError(
                f"مقطع {sp.segment_id}: الأصل بيعطي {avail} إطار من "
                f"{need[sp.segment_id]} مطلوبة (مدة {a.probe.duration}s، "
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

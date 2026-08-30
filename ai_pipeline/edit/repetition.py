"""منع التكرار — **على الخطة، قبل أي ترميز**.

مقيس على مخرَج حقيقي قبل هالطبقة: أصل واحد غطّى **41٪** من الزمن،
وأصل تاني حمل **٤ لقطات من ٧**، وطلع **٨ rewind** بتشغيلة وحدة —
قفزة داخل نفس الملف بلا قطع مقصود.

## الفرق بين القطع والـrewind

لقطتان متتاليتان على نفس الأصل بنافذة **متّصلة** = لقطة وحدة، والقطع
بينهما غير مرئي بقصد. بنافذة **راجعة** = قطع حقيقي — الصورة بتقفز.
والسلطة على التمييز هي `timeline.asset_in_frame` **بالإطارات**، لا
هوية الأصل: هوية واحدة ما بتعني استمرارية.

## العقوبة والحرّاس

العقوبة ترجيح ناعم (`penalty`)، والحرّاس **قاطعون** (`hard_guards`).
الاتنان منفصلان بقصد: الترجيح بيفاضل بين مرشّحين، والحارس بيرفض
نتيجة. خلطهما بيخلّي رقمًا كبيرًا يشتري مخالفة.
"""
from __future__ import annotations

from ..models.assets import AssetsContract
from ..models.timeline import Timeline
from .pacing import Violation

#: أصل واحد ما بيغطّي أكتر من هيك من زمن الفيديو.
MAX_ASSET_SHARE = 0.35
#: ولا بيظهر بأكتر من هالعدد من المواضع غير المتجاورة.
MAX_ASSET_RUNS = 2
#: تسامح الاستمرارية بالإطارات — مشتقّ لا مختار: `in_point` بتتقرّب
#: للملي و`quantize` للإطار، فالفرق المتراكم ≤ إطار.
CONTINUITY_TOLERANCE = 1


def asset_runs(timeline: Timeline) -> list[tuple[int, int, int]]:
    """`[(segment_id, أول لقطة, عدد اللقطات)]` — اللقطات المتجاورة تُدمج.

    الدمج **بالفهرس لا بالهوية**: لقطتان بنفس الأصل ونافذة متّصلة
    لقطة وحدة، وبنافذة راجعة لقطتان.
    """
    runs: list[tuple[int, int, int]] = []
    prev_sid, prev_end = None, None
    for i, sp in enumerate(timeline.visual_spans):
        start = timeline.asset_in_frame.get(sp.segment_id)
        joins = (sp.segment_id == prev_sid and start is not None
                 and prev_end is not None
                 and abs(start - prev_end) <= CONTINUITY_TOLERANCE)
        if joins:
            sid, first, n = runs[-1]
            runs[-1] = (sid, first, n + 1)
        else:
            runs.append((sp.segment_id, i, 1))
        prev_sid = sp.segment_id
        prev_end = None if start is None else start + sp.n_frames
    return runs


def penalty(segment_id: int, used: list[int], position: int) -> float:
    """عقوبة ترجيح — **ناعمة**، بتفاضل ولا بترفض.

        count²  +  1 ÷ (المسافة لآخر استعمال)

    التربيع بقصد: الاستعمال التاني مقبول، والرابع مش أربع مرات أسوأ —
    هو أسوأ بكتير. والمسافة بتخفّف عقوبة أصل رجع بعد بُعد.
    """
    count = used.count(segment_id)
    if count == 0:
        return 0.0
    last = max(i for i, s in enumerate(used) if s == segment_id)
    distance = max(1, position - last)
    return count ** 2 + 1.0 / distance


def hard_guards(timeline: Timeline,
                assets: AssetsContract | None = None) -> list[Violation]:
    """الحرّاس القاطعون — **مخالفة بدليل، لا درجة**."""
    out: list[Violation] = []
    total = timeline.total_frames
    spans = timeline.visual_spans

    share: dict[int, int] = {}
    for sp in spans:
        share[sp.segment_id] = share.get(sp.segment_id, 0) + sp.n_frames
    for sid, n in sorted(share.items()):
        if n / total > MAX_ASSET_SHARE:
            out.append(Violation(
                "asset_dominance",
                f"مقطع {sid} بياخد {n / total:.0%} > {MAX_ASSET_SHARE:.0%} "
                f"({n} من {total} إطار)", (sid,)))

    runs = asset_runs(timeline)
    per: dict[int, int] = {}
    for sid, _, _ in runs:
        per[sid] = per.get(sid, 0) + 1
    for sid, n in sorted(per.items()):
        if n > MAX_ASSET_RUNS:
            out.append(Violation(
                "asset_reappearance",
                f"مقطع {sid} بيظهر بـ{n} موضع غير متجاور > {MAX_ASSET_RUNS}",
                (sid,)))

    # rewind: نفس الأصل، نافذة راجعة ⟶ **قطع حقيقي مخفي كاستمرار**
    prev_sid, prev_end = None, None
    for i, sp in enumerate(spans):
        start = timeline.asset_in_frame.get(sp.segment_id)
        if (sp.segment_id == prev_sid and start is not None
                and prev_end is not None
                and start < prev_end - CONTINUITY_TOLERANCE):
            out.append(Violation(
                "hidden_rewind",
                f"اللقطة {i}: الأصل رجع من الإطار {prev_end} لـ{start} — "
                f"قطع حقيقي مخفي كاستمرار", (i,)))
        prev_sid = sp.segment_id
        prev_end = None if start is None else start + sp.n_frames
    return out

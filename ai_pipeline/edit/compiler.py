"""المترجم — **نيّة نسبية ⟶ زمن مطلق، وولا شي غير هذا**.

    EditPlan (brief|normal|extended)  ──►  Timeline (إطارات)

**حتمي بالكامل:** ولا نداء نموذج، ولا قراءة شبكة، ولا قرص. نفس المدخل
بيعطي نفس المخرج بايت-بايت.

**ولا يخترع نيّة.** نيّة ناقصة بترمي، ما بتاخد قيمة افتراضية صامتة —
نفس قرار `Duration: N/A` بـ`cuts.probe`: الرقم المخترَع بينتشر لكل ما
بعده، والفشل الصريح أرخص.

**و`quantize` تبقى المعبر الوحيد** من الثواني للإطارات. المترجم ما
بيحسب إطارًا واحدًا لحاله — بيحسب **حدود اللقطات** وبيمرّرها لها.

---

## بوابة الترحيل

`compile_plan(trivial_plan(segments), …)` لازم يعطي **نفس** الـTimeline
اللي بيعطيه `quantize(…)` بالضبط. الفحص بيقارن `model_dump_json()`
بايت-بايت، مش الحقول وحدة وحدة — لأن حقلًا جديدًا بينضاف لاحقًا
بيمرق من المقارنة الحقلية وبيكسر الترحيل بصمت.
"""
from __future__ import annotations

from ..errors import TimelineError
from ..models.alignment import Alignment
from ..models.assets import AssetsContract
from ..models.project import Output
from ..models.segments import SegmentsContract
from ..models.timeline import Timeline
from ..timeline.quantize import quantize
from .plan import EditPlan

#: وزن كل `ShotWeight` عند توزيع إطارات الـbeat على لقطاته.
#: **نسب لا ثوانٍ** — الرقم النهائي بيطلع من مدة الـbeat.
WEIGHT = {"brief": 1.0, "normal": 1.6, "extended": 2.4}


def check_plan_covers(plan: EditPlan, segments: SegmentsContract) -> None:
    """كل مقطع نصّي لازم يكون بـbeat، وكل beat لازم يكون بالمقاطع.

    **الاتجاهان مقصودان.** مقطع بلا beat بيصير نصًّا بلا صورة، وbeat
    بمقطع مش موجود بيصير لقطة معلّقة — والاتنين بيمرقوا لو فحصنا
    اتجاهًا واحدًا.
    """
    have = {s.segment_id for s in segments.segments}
    planned: set[int] = set()
    for b in plan.beats:
        planned |= set(b.segment_ids)
    missing = sorted(have - planned)
    if missing:
        raise TimelineError(
            f"الخطة ما بتغطّي المقاطع {missing} — المترجم ما بيخترع beat")
    unknown = sorted(planned - have)
    if unknown:
        raise TimelineError(
            f"الخطة بتشير لمقاطع مش موجودة بـsegments.json: {unknown}")


def shot_cuts(plan: EditPlan, segments: SegmentsContract,
              alignment: Alignment, output: Output,
              audio_duration: float) -> list[int]:
    """حدود اللقطات بالإطارات — **المخرَج الوحيد للمترجم نحو `quantize`**.

    الطريقة:

    ١· حدود الـbeats = بدايات مقاطعها النصّية (نفس قاعدة اليوم).
    ٢· داخل كل beat، إطاراته بتنوزّع على لقطاته **بنسبة أوزانها**.
    ٣· الحدود بتتقرّب للإطار، وبتتشدّ لتضل متزايدة تمامًا.

    ولقطة واحدة بالـbeat بتعطي **نفس حدود اليوم بالضبط** — وهاد أساس
    بوابة الترحيل: بلا حالة خاصة ولا فرع منفصل، الحالة التافهة هي
    الحالة العامة عند n=1.
    """
    fps = output.fps
    total_frames = round(audio_duration * fps)
    by_id = {s.segment_id: s for s in segments.segments}

    # حدود الـbeats — أول مقطع بكل beat بيفتح حدًّا (عدا الأول: الإطار 0)
    order = sorted(plan.beats, key=lambda b: min(b.segment_ids))
    edges: list[int] = [0]
    for b in order[1:]:
        first = by_id[min(b.segment_ids)]
        t0, _ = alignment.span_time(first.word_start, first.word_end)
        edges.append(round(t0 * fps))
    edges.append(total_frames)

    cuts: list[int] = [0]
    for b, lo, hi in zip(order, edges, edges[1:]):
        shots = plan.shots_of(b.beat_id)
        span = hi - lo
        if span <= 0:
            raise TimelineError(
                f"beat {b.beat_id}: مدى فارغ [{lo}, {hi}) — المقاطع متلاصقة")
        if len(shots) == 1:
            cuts.append(hi)
            continue
        if span < len(shots):
            raise TimelineError(
                f"beat {b.beat_id}: {len(shots)} لقطات على {span} إطار — "
                f"ما بيكفي إطارًا لكل لقطة. قلّل `shot_count` أو زوّد الـfps")
        w = [WEIGHT[s.weight] for s in shots]
        tot, acc = sum(w), 0.0
        for k, x in enumerate(w[:-1]):
            acc += x
            c = lo + round(span * acc / tot)
            # **متزايدة تمامًا مع إطار لكل لقطة باقية.** بلا الشدّ الأعلى
            # آخر لقطة ممكن تصير صفر إطار، و`Span` بترمي وقتها برسالة
            # بتوجّه لمكان غلط.
            remaining = len(shots) - k - 1
            c = max(c, cuts[-1] + 1)
            c = min(c, hi - remaining)
            cuts.append(c)
        cuts.append(hi)
    return cuts


def compile_plan(plan: EditPlan, output: Output, segments: SegmentsContract,
                 alignment: Alignment, assets: AssetsContract,
                 audio_duration: float) -> Timeline:
    """`EditPlan` ──► `Timeline`. **حتمي، وبيمرّ من `quantize` وحدها.**"""
    check_plan_covers(plan, segments)
    return quantize(output, segments, alignment, assets, audio_duration)

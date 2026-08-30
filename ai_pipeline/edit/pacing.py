"""قيود الإيقاع — **رفض التطابق، لا اختيار عشوائي**.

الفرق بينهما جوهري: العشوائية اختيار بلا سبب، والتنوّع **قيد على
التوزيع** والقرار داخله يبقى للمحرّر. فهالملف ما بيختار ولا لقطة —
بيرفض الخطة اللي بتكسر قيدًا، برسالة بتسمّي القيد ورقمه.

وكل قيد **قابل للدحض بمثال**: ما في «درجة إيقاع» ولا رقم مجمّع. الرقم
المجمّع بيعطي الحكم ثقة القياس الزائفة وبيوقف السؤال بدل ما يفتحه —
وهالمستودع فيه تمان حوادث موثّقة من هالشكل بالضبط.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..errors import TimelineError
from ..models.timeline import Timeline
from .plan import EditPlan

#: القيم مقيسة أو مشتقّة، لا مختارة بالذوق — وكل وحدة إلها سبب مكتوب.
MIN_SHOT_S = 0.6          #: أقصر من هيك بتنقرا كخلل لا كقطع
MAX_SHOT_S = 4.0          #: أطول من هيك بتموت اللقطة على الشاشة
MIN_CV = 0.25             #: تباين المدد — أقل منه = «كل اللقطات متساوية»
MAX_MOTION_SHARE = 0.45   #: ولا حركة بتهيمن على أكتر من هيك
MAX_SAME_MOTION_RUN = 3   #: ولا تلات لقطات متتالية بنفس الحركة
MIN_STATIC_SHARE = 0.15   #: الصمت البصري قرار، مش بقية
MIN_CUE_GAP_S = 2.5       #: أكتر من مؤثر كل هيك بتصير سجادة


@dataclass(frozen=True)
class Violation:
    """مخالفة **بدليل**، لا بدرجة."""

    rule: str
    detail: str
    where: tuple[int, ...] = ()

    def __str__(self) -> str:
        w = f"  {list(self.where)}" if self.where else ""
        return f"{self.rule}: {self.detail}{w}"


def _cv(xs: list[int]) -> float:
    """معامل الاختلاف — الانحراف المعياري ÷ المتوسط."""
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    if m <= 0:
        return 0.0
    var = sum((x - m) ** 2 for x in xs) / len(xs)
    return (var ** 0.5) / m


def check_pacing(plan: EditPlan, timeline: Timeline) -> list[Violation]:
    """بترجّع المخالفات. **ولا ترمي** — القرار على المستدعي.

    الفصل مقصود: `Technical QA` بترمي لأن الملف غلط، والإيقاع **حكم
    على الخطة** — فبيتبلّغ ويتقرّر، ما بينفجر.
    """
    out: list[Violation] = []
    fps = timeline.fps
    spans = timeline.visual_spans
    lens = [s.n_frames for s in spans]

    short = tuple(i for i, n in enumerate(lens) if n < MIN_SHOT_S * fps)
    if short:
        out.append(Violation("min_shot_duration",
                             f"{len(short)} لقطة أقصر من {MIN_SHOT_S}s", short))
    long_ = tuple(i for i, n in enumerate(lens) if n > MAX_SHOT_S * fps)
    if long_:
        out.append(Violation("max_shot_duration",
                             f"{len(long_)} لقطة أطول من {MAX_SHOT_S}s", long_))

    cv = _cv(lens)
    if len(lens) > 1 and cv < MIN_CV:
        out.append(Violation("shot_variance",
                             f"CV {cv:.2f} < {MIN_CV} — اللقطات كلها بنفس المدة"))

    order = sorted(plan.shots, key=lambda s: (min(
        b.segment_ids for b in plan.beats if b.beat_id == s.beat_id), s.order))
    motions = [s.motion for s in order]
    if motions:
        # **`static` مستثنى من الهيمنة بقصد.**
        #
        # الرتابة اللي بيلتقطها المشاهد هي **تكرار حركة**، والسكون مش
        # حركة — هو غيابها. وله قيده الخاص بالاتجاه المعاكس
        # (`static_share` بيطلب حدًّا **أدنى**)، فإخضاعه للحدّ الأعلى
        # كمان بيخلق قيدين متناقضين: ≥15٪ و≤45٪ بنفس الوقت.
        #
        # انكشف بفحص «خطة نظيفة ما بتبلّغ شي»: خطة سليمة تمامًا كانت
        # بتتّهم بهيمنة `static` عند 50٪.
        for m in set(motions) - {"static"}:
            share = motions.count(m) / len(motions)
            if share > MAX_MOTION_SHARE:
                out.append(Violation(
                    "motion_dominance",
                    f"{m} {share:.0%} > {MAX_MOTION_SHARE:.0%} "
                    f"({motions.count(m)} من {len(motions)} لقطة)"))
        run, start = 1, 0
        for i in range(1, len(motions)):
            if motions[i] == motions[i - 1]:
                run += 1
                if run > MAX_SAME_MOTION_RUN:
                    out.append(Violation(
                        "motion_run",
                        f"{run} لقطة متتالية بحركة {motions[i]}",
                        tuple(range(start, i + 1))))
                    break
            else:
                run, start = 1, i

    static = sum(n for m, n in zip(motions, lens) if m == "static")
    if lens and static / sum(lens) < MIN_STATIC_SHARE:
        out.append(Violation(
            "static_share",
            f"اللقطات الساكنة {static / sum(lens):.0%} < {MIN_STATIC_SHARE:.0%} "
            f"— الصمت البصري قرار لا بقية"))

    n_cues = len([c for c in plan.cues if c.kind != "silence"])
    if n_cues:
        gap = (timeline.total_frames / fps) / n_cues
        if gap < MIN_CUE_GAP_S:
            out.append(Violation(
                "cue_density",
                f"مؤثر كل {gap:.1f}s < {MIN_CUE_GAP_S}s ({n_cues} مؤثرًا)"))

    ORDER = {"calm": 0, "building": 1, "driving": 2, "release": 3}
    beats = sorted(plan.beats, key=lambda b: min(b.segment_ids))
    upto = [b for b in beats if b.role not in ("payoff", "cta")]
    for a, b in zip(upto, upto[1:]):
        if ORDER[b.energy] < ORDER[a.energy]:
            out.append(Violation(
                "energy_slump",
                f"الطاقة نزلت من {a.energy} لـ{b.energy} قبل الـpayoff",
                (a.beat_id, b.beat_id)))
            break
    return out


def enforce_pacing(plan: EditPlan, timeline: Timeline) -> None:
    """نفس الفحص، **بس بيرمي**. للمترجم لما يكون الوضع الصارم مطلوبًا."""
    v = check_pacing(plan, timeline)
    if v:
        raise TimelineError(
            "الخطة بتكسر قيود الإيقاع:\n" + "\n".join(f"  · {x}" for x in v))

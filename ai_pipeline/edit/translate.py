"""ترجمة النيّة إلى القيم الموجودة — **بلا فتح عقد مجمَّد**.

    EmphasisProposal  ──►  حقول `TypographyContract` الحالية
    CueProposal       ──►  خريطة أحداث `autoreel.sfx` الحالية

## ليش طبقة لا حقل

إضافة `emphasis` جوّا `TypographyContract` بتفتح عقدًا مجمَّدًا **وبتخلط
نيّة بقيمة**: العقد بيحمل `font_size` و`text_color`، والنيّة بتحمل
«هالكلمة أهم». الطبقة الخارجية بتترجم لنفس الحقول الموجودة، فالعقد
بيضل مغلقًا والراسم ما بيتغيّر.

## والقيود المقيسة تحت ما بتتغيّر

`normalize=0` إلزامية · `all=1` و`aformat` قبل `adelay` · ولا
`alimiter` · الهامش المحسوب 0.925 < 1.0. هالملف بيقرّر **أي مؤثر
وأين**، لا **كيف ينمزج**.
"""
from __future__ import annotations

from ..agents.schemas import TypographyProposal
from .plan import CueProposal, EditPlan, EmphasisProposal

#: `EmphasisLevel` ──► (`size_step`, `color_role`, `animation`).
#: القيم كلها **موجودة أصلًا** بـ`TypographyContract` — ولا حقل جديد.
EMPHASIS = {
    "normal": (0, "primary", "fade_in_up"),
    "strong": (1, "accent", "fade_in_up"),
    "peak":   (2, "accent", "fade_in_scale"),
}

#: `CueKind` ──► اسم الأصل بـ`assets/sfx/`. `silence` ما إلها أصل
#: **بقصد**: هي قرار بمنع مؤثر، لا مؤثر صامت.
CUE_ASSET = {
    "impact": "impact", "whoosh": "whoosh",
    "pop": "pop", "riser": "riser", "silence": None,
}

#: `CueWeight` ──► كسب. القيم من `autoreel/config.json` المعايَرة،
#: والهامش المحسوب بيضل صالحًا: 0.70 + 0.90 × 0.30 = 0.97 < 1.0.
CUE_GAIN = {"subtle": 0.12, "normal": 0.22, "heavy": 0.30}


def typography_overrides(plan: EditPlan) -> dict[int, tuple[int, str, str]]:
    """`{segment_id: (size_step, color_role, animation)}` من أعلى إبراز.

    **الأعلى بيفوز عند التزاحم.** مقطع فيه كلمة `peak` وأخرى `strong`
    بياخد معاملة `peak` — لأن العقد بيعطي قيمة **لكل مقطع** لا لكل
    كلمة، فالاختيار بينهما لازم يكون معلَنًا لا ضمنيًا.
    """
    rank = {"normal": 0, "strong": 1, "peak": 2}
    best: dict[int, EmphasisProposal] = {}
    for e in plan.emphasis:
        cur = best.get(e.segment_id)
        if cur is None or rank[e.level] > rank[cur.level]:
            best[e.segment_id] = e
    return {sid: EMPHASIS[e.level] for sid, e in sorted(best.items())}


def cue_events(plan: EditPlan) -> list[tuple[int, str, str, float]]:
    """`[(beat_id, مرساة, اسم الأصل, كسب)]` — و`silence` **بتنشال**.

    ولا مؤثر بلا `CueProposal`. الحدّ اللي كان بيربط مؤثرًا بكل حدّ
    لقطة انكسر هون: المؤثر صار قرارًا، والصمت قرارًا مساويًا له.
    """
    out = []
    for c in plan.cues:
        asset = CUE_ASSET[c.kind]
        if asset is None:
            continue
        out.append((c.beat_id, c.at, asset, CUE_GAIN[c.weight]))
    return out


def silenced_beats(plan: EditPlan) -> set[int]:
    """الـbeats اللي طلب المحرّر صمتها. **قرار، لا فراغ.**"""
    return {c.beat_id for c in plan.cues if c.kind == "silence"}


def apply_emphasis(
    proposal: TypographyProposal, plan: EditPlan
) -> TypographyProposal:
    """اقتراح الخطّ + نيّة الإبراز ──► اقتراح خطّ **بنفس المفردات**.

    هون بيقع الحدّ فعليًا: المخرَج بيمرق على
    `expand_typography_proposal` نفسها — نفس التوسعة اللي المسار
    القديم بيمرق عليها. فلو الترجمة طلّعت قيمة مخترَعة، بتفشل هناك
    لا هون، وعلى العقد المجمَّد نفسه.

    **والمقاطع بلا إبراز بتمرق كما هي** — ولا قيمة افتراضية بتنزرع
    مكان قرار ما انتّخذ.
    """
    ov = typography_overrides(plan)
    out = []
    for s in proposal.segments:
        hit = ov.get(s.segment_id)
        if hit is None:
            out.append(s)
            continue
        step, color, anim = hit
        out.append(s.model_copy(update={
            "size_step": step, "color_role": color, "animation": anim}))
    return TypographyProposal(segments=tuple(out))

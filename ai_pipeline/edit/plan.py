"""ما **يُسمح** للمحرّر أن يقوله — ولا حرف أكثر.

نفس مبدأ `agents/schemas.py`، ومطبَّق على طبقة أعلى: قوّة هالملف مش
بشو بيرفض، بشو **ما بيقدر يعبّر عنه**.

| ناقص عمدًا | مالكه |
|---|---|
| `start` · `end` · `duration` · `seconds` | `quantize` |
| `frame` · `sample` · `timestamp` | المترجم |
| `file_path` · `provider_ref` · `sha256` | الـResolver |
| `font_size` · ألوان hex | الـtheme |
| `gain` | `sfx.py` |

**الأوزان نسبية بقصد.** `weight: brief|normal|extended` مش «١.٢ ثانية»
— لأن حقل الثواني **غير موجود**. المترجم بيحوّل النسبي لإطارات حسب
مدة الـbeat وقيود المدة، فمحاولة كتابة رقم تنفيذي بتفشل عند القراءة
لا عند مدقّق لاحق.

وفي حارس على هالمبدأ نفسه (`test_the_plan_cannot_express_time`) بيمشي
على كل حقول كل DTO ويرفض أي اسم من قائمة الممنوعات — فإضافة حقل زمني
لاحقًا بتفشل، حتى لو كتبها أحد بحسن نيّة.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ..models.base import StrictModel
from ..models.segments import SegmentsContract

# ── مفردات مغلقة ─────────────────────────────────────────────────────
BeatRole = Literal["hook", "problem", "escalation", "turn",
                   "solution", "demonstration", "payoff", "cta"]
Importance = Literal["low", "normal", "high", "peak"]
Energy = Literal["calm", "building", "driving", "release"]
ShotCount = Literal["single", "few", "many"]
Pace = Literal["hold", "steady", "accelerate"]

ShotWeight = Literal["brief", "normal", "extended"]
ShotIntent = Literal["establish", "detail", "action", "reaction", "reveal", "hold"]
MotionIntent = Literal["static", "push", "pull", "drift", "follow", "micro"]
TransitionIntent = Literal["cut", "soft", "match", "hard"]
Continuity = Literal["new", "continue", "return"]

EmphasisLevel = Literal["normal", "strong", "peak"]

CueAnchor = Literal["beat_start", "shot_change", "emphasis", "beat_end"]
CueKind = Literal["impact", "whoosh", "pop", "riser", "silence"]
CueWeight = Literal["subtle", "normal", "heavy"]

#: أسماء ممنوعة بأي DTO هون. الحارس بيمشي على `model_fields` فعليًا،
#: فما بيكفي إن ما حدا كتبها اليوم — لازم تفشل لو كتبها أحد بكرا.
FORBIDDEN_FIELD_NAMES = frozenset({
    "start", "end", "duration", "seconds", "frame", "frames", "sample",
    "samples", "timestamp", "time", "at_seconds", "offset",
    "file_path", "path", "provider_ref", "sha256", "asset_id",
    "font_size", "size_px", "color", "hex", "gain", "volume", "y_ratio",
})


class BeatProposal(StrictModel):
    """وحدة سردية — بتغطّي مقطعًا نصّيًا أو أكثر."""

    beat_id: int = Field(ge=1)
    segment_ids: tuple[int, ...] = Field(min_length=1)
    role: BeatRole
    importance: Importance = "normal"
    energy: Energy = "calm"
    shot_count: ShotCount = "single"
    pace: Pace = "steady"
    visual_idea: str = Field("", max_length=300)


class ShotProposal(StrictModel):
    """لقطة — **وحدة بصرية مستقلة عن المقطع النصّي**.

    `weight` نسبي: المترجم بيوزّع إطارات الـbeat على لقطاته بنسبة
    الأوزان، ضمن حدّي المدة الدنيا والقصوى.
    """

    shot_id: int = Field(ge=1)
    beat_id: int = Field(ge=1)
    order: int = Field(ge=0)
    weight: ShotWeight = "normal"
    intent: ShotIntent = "establish"
    motion: MotionIntent = "static"
    entry: TransitionIntent = "cut"
    continuity: Continuity = "new"


class EmphasisProposal(StrictModel):
    """كلمة مُبرَزة. `word_index` **نسبي للمقطع**، لا مطلق بالنص."""

    segment_id: int = Field(ge=1)
    word_index: int = Field(ge=0)
    level: EmphasisLevel = "normal"


class CueProposal(StrictModel):
    """مؤثر صوتي **بقرار**، لا كنتيجة لحدّ لقطة.

    `kind="silence"` قرار صريح: بيمنع أي مؤثر بنافذته.
    """

    beat_id: int = Field(ge=1)
    at: CueAnchor = "beat_start"
    kind: CueKind = "impact"
    weight: CueWeight = "normal"


class EditPlan(StrictModel):
    beats: tuple[BeatProposal, ...] = Field(min_length=1)
    shots: tuple[ShotProposal, ...] = Field(min_length=1)
    emphasis: tuple[EmphasisProposal, ...] = ()
    cues: tuple[CueProposal, ...] = ()

    @model_validator(mode="after")
    def _structure(self) -> "EditPlan":
        bids = [b.beat_id for b in self.beats]
        if len(set(bids)) != len(bids):
            raise ValueError(f"beat_id مكرّر: {sorted({i for i in bids if bids.count(i) > 1})}")
        sids = [s.shot_id for s in self.shots]
        if len(set(sids)) != len(sids):
            raise ValueError(f"shot_id مكرّر: {sorted({i for i in sids if sids.count(i) > 1})}")

        known = set(bids)
        for s in self.shots:
            if s.beat_id not in known:
                raise ValueError(f"لقطة {s.shot_id}: beat_id {s.beat_id} مش موجود")
        for c in self.cues:
            if c.beat_id not in known:
                raise ValueError(f"مؤثر عند beat_id {c.beat_id} مش موجود")

        # كل beat لازم يحمل لقطة — beat بلا لقطات فراغ بصري صامت
        with_shots = {s.beat_id for s in self.shots}
        empty = sorted(known - with_shots)
        if empty:
            raise ValueError(f"beats بلا لقطات: {empty}")

        # المقاطع النصّية موزّعة بلا تكرار — مقطع بـbeatين تناقض سردي
        seen: set[int] = set()
        for b in self.beats:
            dup = seen & set(b.segment_ids)
            if dup:
                raise ValueError(f"beat {b.beat_id}: مقاطع مكرّرة عبر beats: {sorted(dup)}")
            seen |= set(b.segment_ids)

        # ترتيب اللقطات داخل الـbeat متتالٍ من الصفر — الترتيب معنى لا زخرفة
        for bid in bids:
            orders = sorted(s.order for s in self.shots if s.beat_id == bid)
            if orders != list(range(len(orders))):
                raise ValueError(
                    f"beat {bid}: ترتيب اللقطات لازم 0..n-1 بلا فجوة، وصل {orders}")
        return self

    def shots_of(self, beat_id: int) -> tuple[ShotProposal, ...]:
        return tuple(sorted((s for s in self.shots if s.beat_id == beat_id),
                            key=lambda s: s.order))


def trivial_plan(segments: SegmentsContract) -> EditPlan:
    """**خطة تافهة تمثّل سلوك النظام القديم بالضبط**: مقطع = لقطة واحدة.

    هاي مش أداة عرض — هاي **بوابة الترحيل**. المترجم عليها لازم يعطي
    نفس الـtimeline اللي بيعطيه المسار القديم، بايت-بايت. لو اختلف
    بايت واحد، الترحيل غلط قبل ما نضيف أي ذكاء.

    ولا `role` ولا `energy` هون تعني شيئًا — كلها الافتراضي. الخطة
    التافهة **بلا نيّة تحريرية بقصد**.
    """
    beats, shots = [], []
    for i, s in enumerate(segments.segments, start=1):
        beats.append(BeatProposal(beat_id=i, segment_ids=(s.segment_id,),
                                  role="demonstration"))
        shots.append(ShotProposal(shot_id=i, beat_id=i, order=0))
    return EditPlan(beats=tuple(beats), shots=tuple(shots))

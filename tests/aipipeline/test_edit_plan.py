"""`EditPlan` + المترجم — **وبوابة الترحيل قبل أي ذكاء**.

الفحص الأهم بهالملف مش على ميزة جديدة: هو إن **الخطة التافهة تعطي
نفس الـtimeline القديم بايت-بايت**. لو اختلف بايت، الترحيل غلط قبل ما
نضيف أي سلوك إبداعي.
"""
import pytest

from ai_pipeline.edit import (
    BeatProposal, CueProposal, EditPlan, EmphasisProposal, ShotProposal,
    trivial_plan,
)
from ai_pipeline.edit.compiler import (
    WEIGHT, check_plan_covers, compile_plan, shot_cuts,
)
from ai_pipeline.edit.plan import FORBIDDEN_FIELD_NAMES
from ai_pipeline.errors import TimelineError
from ai_pipeline.models.alignment import Alignment, Word
from ai_pipeline.models.assets import Asset, AssetsContract, Probe
from ai_pipeline.models.project import Output
from ai_pipeline.models.segments import Segment, SegmentsContract
from ai_pipeline.timeline.quantize import quantize


# ── تركيبة صغيرة وحقيقية ─────────────────────────────────────────────
WORDS = [("بتتخيل", 0.20, 0.70), ("تعمل", 0.70, 1.20), ("فيديو", 1.20, 1.80),
         ("بدل", 2.40, 2.90), ("ما", 2.90, 3.30), ("تضيع", 3.30, 4.00),
         ("وبالنهاية", 4.80, 5.40), ("جاهز", 5.40, 6.00)]


@pytest.fixture
def alignment():
    return Alignment(method="srt", words=tuple(
        Word(i=k, text=t, start=a, end=b)
        for k, (t, a, b) in enumerate(WORDS)))


@pytest.fixture
def segments():
    spans = [(0, 3), (3, 6), (6, 8)]
    return SegmentsContract(segments=tuple(
        Segment(segment_id=i, word_start=a, word_end=b,
                text_arabic=" ".join(w[0] for w in WORDS[a:b]),
                visual_mood_prompt=f"idea {i}")
        for i, (a, b) in enumerate(spans, start=1)))


@pytest.fixture
def assets(tmp_path):
    return AssetsContract(assets=tuple(
        Asset(segment_id=i, source_type="local", provider="p",
              provider_ref=f"r{i}", file_path=tmp_path / f"{i}.mp4",
              sha256="c" * 64, license="CC0",
              probe=Probe(width=1920, height=1080, fps=30.0, duration=40.0),
              in_point=0.0)
        for i in (1, 2, 3)))


@pytest.fixture
def output():
    return Output(width=1080, height=1920, fps=30, sample_rate=48000)


# ══════════ بوابة الترحيل ══════════════════════════════════════════
def test_the_trivial_plan_reproduces_the_old_timeline_byte_for_byte(
        output, segments, alignment, assets):
    """**الفحص الحاسم.** مقطع = لقطة واحدة ⟶ نفس الـtimeline بالضبط.

    المقارنة على `model_dump_json()` **بايت-بايت**، لا حقلًا حقلًا:
    حقل جديد بينضاف لاحقًا بيمرق من المقارنة الحقلية وبيكسر الترحيل
    بصمت — وهاد بالضبط شكل الأخطاء اللي هالمستودع بيعاقب عليها.
    """
    old = quantize(output, segments, alignment, assets, 6.4)
    new = compile_plan(trivial_plan(segments), output, segments, alignment,
                       assets, 6.4)
    assert new.model_dump_json() == old.model_dump_json()


def test_the_trivial_plan_has_one_shot_per_segment(segments):
    p = trivial_plan(segments)
    assert len(p.beats) == len(p.shots) == 3
    assert all(len(p.shots_of(b.beat_id)) == 1 for b in p.beats)


# ══════════ الخطة لا تقدر تعبّر عن الزمن ═══════════════════════════
def test_the_plan_cannot_express_time():
    """**الحارس على المبدأ، لا على الحالة.**

    ما بيكفي إن ولا حقل زمني مكتوب اليوم — الفحص بيمشي على
    `model_fields` فعليًا، فأي حقل زمني بينضاف بكرا بيفشل هون حتى لو
    كتبه أحد بحسن نيّة.
    """
    for dto in (BeatProposal, ShotProposal, EmphasisProposal, CueProposal,
                EditPlan):
        bad = set(dto.model_fields) & FORBIDDEN_FIELD_NAMES
        assert not bad, f"{dto.__name__} فيه حقول تنفيذية: {sorted(bad)}"


@pytest.mark.parametrize("field", ["start", "end", "duration", "frame",
                                   "seconds", "timestamp", "file_path", "gain"])
def test_injecting_an_executive_field_fails_at_read_time(field):
    """`extra="forbid"` بيرفض الحقن **عند القراءة**، قبل أي مدقّق دلالي."""
    import json
    raw = json.dumps({"shot_id": 1, "beat_id": 1, "order": 0, field: 1.5})
    with pytest.raises(Exception):
        ShotProposal.model_validate_json(raw)


@pytest.mark.parametrize("dto,field,bad", [
    (BeatProposal, "role", "intro"), (BeatProposal, "importance", "huge"),
    (BeatProposal, "energy", "loud"), (BeatProposal, "pace", "fast"),
    (ShotProposal, "weight", "long"), (ShotProposal, "intent", "cutaway"),
    (ShotProposal, "motion", "zoom_in"), (ShotProposal, "entry", "dissolve"),
    (ShotProposal, "continuity", "same"), (EmphasisProposal, "level", "huge"),
    (CueProposal, "kind", "boom"), (CueProposal, "at", "middle"),
])
def test_the_vocabulary_is_closed(dto, field, bad):
    base = {BeatProposal: {"beat_id": 1, "segment_ids": (1,), "role": "hook"},
            ShotProposal: {"shot_id": 1, "beat_id": 1, "order": 0},
            EmphasisProposal: {"segment_id": 1, "word_index": 0},
            CueProposal: {"beat_id": 1}}[dto]
    with pytest.raises(Exception):
        dto(**{**base, field: bad})


# ══════════ بنية الخطة ═════════════════════════════════════════════
def beat(i, segs=(1,), **kw):
    return BeatProposal(beat_id=i, segment_ids=segs, role="demonstration", **kw)


def shot(i, b, o=0, **kw):
    return ShotProposal(shot_id=i, beat_id=b, order=o, **kw)


def test_a_beat_without_shots_is_rejected():
    """beat بلا لقطات = فراغ بصري صامت."""
    with pytest.raises(Exception, match="بلا لقطات"):
        EditPlan(beats=(beat(1), beat(2, (2,))), shots=(shot(1, 1),))


def test_a_shot_pointing_at_a_missing_beat_is_rejected():
    with pytest.raises(Exception, match="مش موجود"):
        EditPlan(beats=(beat(1),), shots=(shot(1, 1), shot(9, 7)))


def test_a_segment_in_two_beats_is_rejected():
    """تناقض سردي: نفس الكلام بدورين."""
    with pytest.raises(Exception, match="مكرّرة"):
        EditPlan(beats=(beat(1, (1, 2)), beat(2, (2, 3))),
                 shots=(shot(1, 1), shot(2, 2)))


def test_shot_order_must_be_contiguous_from_zero():
    """الترتيب معنى لا زخرفة — فجوة فيه تعني لقطة ضايعة."""
    with pytest.raises(Exception, match="ترتيب اللقطات"):
        EditPlan(beats=(beat(1),), shots=(shot(1, 1, 0), shot(2, 1, 2)))


def test_duplicate_ids_are_rejected():
    with pytest.raises(Exception, match="beat_id مكرّر"):
        EditPlan(beats=(beat(1), beat(1, (2,))), shots=(shot(1, 1),))
    with pytest.raises(Exception, match="shot_id مكرّر"):
        EditPlan(beats=(beat(1),), shots=(shot(1, 1, 0), shot(1, 1, 1)))


# ══════════ التغطية باتجاهين ═══════════════════════════════════════
def test_a_plan_that_misses_a_segment_is_rejected(segments):
    """المترجم **ما بيخترع beat** لمقطع منسي."""
    p = EditPlan(beats=(beat(1, (1, 2)),), shots=(shot(1, 1),))
    with pytest.raises(TimelineError, match="ما بتغطّي المقاطع"):
        check_plan_covers(p, segments)


def test_a_plan_referencing_an_unknown_segment_is_rejected(segments):
    """الاتجاه الثاني — بلاه اللقطة المعلّقة بتمرق."""
    p = EditPlan(beats=(beat(1, (1, 2, 3, 99)),), shots=(shot(1, 1),))
    with pytest.raises(TimelineError, match="مش موجودة"):
        check_plan_covers(p, segments)


# ══════════ توزيع الأوزان ══════════════════════════════════════════
def test_one_shot_per_beat_gives_the_old_boundaries(
        output, segments, alignment, assets):
    """الحالة التافهة **هي الحالة العامة عند n=1** — بلا فرع خاص.

    هاد الفحص هو اللي بيثبت إن `shot_cuts` جاهزة للمرحلة الجاية:
    بتعطي حدود اليوم بالضبط قبل ما توصلها أي نيّة تحريرية.
    """
    cuts = shot_cuts(trivial_plan(segments), segments, alignment, output, 6.4)
    old = quantize(output, segments, alignment, assets, 6.4)
    assert cuts == [s.f_start for s in old.visual_spans] + [old.total_frames]


def test_weights_split_a_beat_proportionally(output, segments, alignment):
    """`extended` بتاخد أكتر من `brief` — والنسبة من `WEIGHT` لا من رقم."""
    p = EditPlan(
        beats=(beat(1, (1, 2, 3)),),
        shots=(shot(1, 1, 0, weight="brief"), shot(2, 1, 1, weight="extended")))
    cuts = shot_cuts(p, segments, alignment, output, 6.4)
    assert len(cuts) == 3
    first, second = cuts[1] - cuts[0], cuts[2] - cuts[1]
    assert second > first
    assert abs(second / first - WEIGHT["extended"] / WEIGHT["brief"]) < 0.25


def test_every_shot_gets_at_least_one_frame(output, segments, alignment):
    """الشدّ الأعلى: آخر لقطة ما بتصير صفر إطار."""
    p = EditPlan(beats=(beat(1, (1, 2, 3)),),
                 shots=tuple(shot(i + 1, 1, i, weight="extended" if i == 0
                                  else "brief") for i in range(5)))
    cuts = shot_cuts(p, segments, alignment, output, 6.4)
    assert all(b > a for a, b in zip(cuts, cuts[1:])), cuts


def test_more_shots_than_frames_fails_loudly(output, segments, alignment):
    p = EditPlan(beats=(beat(1, (1, 2, 3)),),
                 shots=tuple(shot(i + 1, 1, i) for i in range(400)))
    with pytest.raises(TimelineError, match="ما بيكفي إطارًا"):
        shot_cuts(p, segments, alignment, output, 6.4)


# ══════════ الحتمية ════════════════════════════════════════════════
def test_the_compiler_is_deterministic(output, segments, alignment, assets):
    p = trivial_plan(segments)
    a = compile_plan(p, output, segments, alignment, assets, 6.4)
    b = compile_plan(p, output, segments, alignment, assets, 6.4)
    assert a.model_dump_json() == b.model_dump_json()


def test_the_compiler_calls_no_model_and_touches_no_disk():
    """قائمة سالبة على شجرة الكود — أرخص من انتظار الخلل."""
    import ast
    import pathlib
    src = pathlib.Path("ai_pipeline/edit/compiler.py").read_text()
    tree = ast.parse(src)
    names = {n.names[0].name.split(".")[0] for n in ast.walk(tree)
             if isinstance(n, ast.Import)}
    names |= {n.module.split(".")[0] for n in ast.walk(tree)
              if isinstance(n, ast.ImportFrom) and n.module}
    for banned in ("subprocess", "requests", "httpx", "anthropic", "socket",
                   "urllib", "random", "time"):
        assert banned not in names, f"المترجم بيستورد {banned}"


# ══════════ حراسة الحارس نفسه ══════════════════════════════════════
def test_the_forbidden_list_is_not_empty():
    """**الحارس على الحارس.**

    `test_the_plan_cannot_express_time` بيقارن تقاطعًا مع
    `FORBIDDEN_FIELD_NAMES` — وقائمة فاضية بتعطي تقاطعًا فاضيًا فبيمرّ
    الفحص على فراغ. انمسكت بطفرة أفرغت القائمة.
    """
    for name in ("start", "end", "duration", "seconds", "frame", "sample",
                 "timestamp", "file_path", "provider_ref", "sha256",
                 "font_size", "gain"):
        assert name in FORBIDDEN_FIELD_NAMES, f"{name} مش بقائمة الممنوعات"
    assert len(FORBIDDEN_FIELD_NAMES) >= 20


# ══════════ الحالة الضيّقة: إطار واحد لكل لقطة ═════════════════════
def _tight(short_first: bool):
    """beat واحد بأضيق مدى ممكن — والترتيب يقرّر أي شدّ يشتغل.

    عند fps=1 المدى ٦ إطارات. و**كل ترتيب يلمس شدًّا واحدًا فقط**:

    * `short_first`: أول لقطة `brief` ⟶ 1/13 × 6 = 0.46 بتتقرّب لـ0،
      أي نفس الحدّ السابق ⟶ **الشدّ الأدنى** هو اللي بينقذها.
    * وإلا: الطويلات بالأول بتاكل المدى ⟶ **الشدّ الأعلى** هو اللي
      بيترك إطارًا لكل لقطة باقية.

    مقيس: فحص بترتيب واحد بيخلّي طفرة الشدّ الآخر **تمرق**. صار هيك
    مرتين بالجولات الأولى.
    """
    out = Output(width=1080, height=1920, fps=1, sample_rate=48000)
    if short_first:
        shots = (shot(1, 1, 0, weight="brief"),) + tuple(
            shot(i + 2, 1, i + 1, weight="extended") for i in range(5))
    else:
        shots = tuple(shot(i + 1, 1, i, weight="extended") for i in range(2)) + \
                tuple(shot(i + 3, 1, i + 2, weight="brief") for i in range(3))
    return out, EditPlan(beats=(beat(1, (1, 2, 3)),), shots=shots)


def test_the_lower_clamp_keeps_cuts_strictly_increasing(segments, alignment):
    """بلا الشدّ الأدنى بتصير لقطة **صفر إطار** — و`Span` بترمي برسالة
    بتوجّه لمكان غلط."""
    out, p = _tight(short_first=True)
    cuts = shot_cuts(p, segments, alignment, out, 6.4)
    assert cuts == sorted(set(cuts)), f"حدود متكرّرة أو راجعة: {cuts}"
    assert all(b - a >= 1 for a, b in zip(cuts, cuts[1:])), cuts


def test_the_upper_clamp_leaves_room_for_the_last_shots(segments, alignment):
    """بلا الشدّ الأعلى، لقطة مبكّرة بتاكل مدى اللقطات اللي بعدها."""
    out, p = _tight(short_first=False)
    cuts = shot_cuts(p, segments, alignment, out, 6.4)
    assert cuts == sorted(set(cuts)), f"حدود متكرّرة أو راجعة: {cuts}"
    assert len(cuts) == 6, cuts
    assert cuts[0] == 0 and cuts[-1] == 6
    for k, b in enumerate(cuts[1:-1]):
        remaining = len(cuts) - k - 3
        assert cuts[-1] - b >= remaining, f"اللقطة {k} أكلت مدى الباقيات: {cuts}"

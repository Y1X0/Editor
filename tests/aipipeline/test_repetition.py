"""منع التكرار — والتمييز بين **القطع** و**الـrewind**.

مقيس على مخرَج حقيقي قبل هالطبقة: أصل غطّى 41٪، وأصل حمل 4 لقطات من
7، و8 rewind بتشغيلة وحدة.
"""
import pytest

from ai_pipeline.edit.repetition import (
    CONTINUITY_TOLERANCE, MAX_ASSET_RUNS, MAX_ASSET_SHARE, asset_runs,
    hard_guards, penalty,
)
from ai_pipeline.models.timeline import Span, Timeline


def tl(spec, in_frame):
    """`spec = [(segment_id, n_frames)]`."""
    acc, spans = 0, []
    for sid, n in spec:
        spans.append(Span(segment_id=sid, f_start=acc, f_end=acc + n))
        acc += n
    return Timeline(fps=30, sample_rate=48000, total_frames=acc,
                    visual_spans=tuple(spans),
                    text_spans=(Span(segment_id=spec[0][0], f_start=0, f_end=acc),),
                    asset_in_frame=in_frame)


def rules(v):
    return {x.rule for x in v}


# ── القطع مقابل الـrewind ────────────────────────────────────────────
def test_a_continuous_window_is_one_run():
    """نفس الأصل + نافذة متّصلة = **لقطة وحدة**، والقطع غير مرئي.

    ⚠️ **الحدّ المعروف:** `asset_in_frame` مفتاحه `segment_id`، فلقطتان
    على نفس المقطع بتتشاركا نقطة البدء — واللقطة التانية بتبلّش من وين
    بلّشت الأولى، لا من وين انتهت. فالدمج بيتحقّق **فقط** لما تكون
    اللقطة الأولى إطارًا واحدًا (0 + 1 ≈ 0 ضمن التسامح).

    الفحص هون بيثبت إن **منطق الدمج صحيح** لما يصير قابلًا للوصول —
    أي لما تاخد كل لقطة نافذتها. وبدونه كان فرع الدمج ميتًا بلا فحص،
    ومرقت طفرة عطّلته بالكامل.
    """
    t = tl([(1, 1), (1, 60)], {1: 0})
    assert len(asset_runs(t)) == 1, "النافذة متّصلة ⟶ لقطة وحدة"
    # وبنافذة راجعة فعليًا: لقطتان
    t2 = tl([(1, 60), (1, 60)], {1: 0})
    assert len(asset_runs(t2)) == 2


def test_different_assets_are_different_runs():
    t = tl([(1, 40), (2, 40), (1, 40)], {1: 0, 2: 0})
    assert len(asset_runs(t)) == 3


def test_a_rewind_is_reported_as_a_hidden_cut():
    """**قطع حقيقي مخفي كاستمرار.** نفس الأصل، نافذة راجعة."""
    t = tl([(1, 60), (1, 60)], {1: 0})
    v = hard_guards(t)
    assert "hidden_rewind" in rules(v)
    assert "رجع من الإطار" in next(x for x in v if x.rule == "hidden_rewind").detail


# ── الحرّاس القاطعون ─────────────────────────────────────────────────
def test_a_dominant_asset_is_flagged():
    """أصل غطّى 41٪ كان مخرَج النظام قبل هالطبقة."""
    t = tl([(1, 100), (2, 50), (3, 50)], {1: 0, 2: 0, 3: 0})
    v = hard_guards(t)
    assert "asset_dominance" in rules(v)
    assert "50%" in next(x for x in v if x.rule == "asset_dominance").detail


def test_a_balanced_timeline_passes_dominance():
    t = tl([(1, 60), (2, 70), (3, 70)], {1: 0, 2: 0, 3: 0})
    assert "asset_dominance" not in rules(hard_guards(t))


def test_too_many_reappearances_are_flagged():
    """أ ب أ ب أ — الأصل الأول بتلات مواضع غير متجاورة."""
    t = tl([(1, 30), (2, 30), (1, 30), (2, 30), (1, 30), (3, 60)],
           {1: 0, 2: 0, 3: 0})
    v = hard_guards(t)
    assert "asset_reappearance" in rules(v)


def test_two_reappearances_are_allowed():
    t = tl([(1, 30), (2, 60), (1, 30), (3, 90)], {1: 0, 2: 0, 3: 0})
    assert "asset_reappearance" not in rules(hard_guards(t))


def test_a_clean_timeline_reports_nothing():
    t = tl([(1, 60), (2, 70), (3, 70)], {1: 0, 2: 0, 3: 0})
    assert hard_guards(t) == []


# ── العقوبة الناعمة ──────────────────────────────────────────────────
def test_an_unused_asset_costs_nothing():
    assert penalty(5, [1, 2, 3], 3) == 0.0


def test_the_penalty_grows_faster_than_the_count():
    """**التربيع بقصد.** الاستعمال الرابع مش أربع مرات أسوأ من الأول.

    **الموضع بعيد بقصد (1000).** أول كتابة استعملت موضعًا قريبًا،
    فحدّ المسافة (`1 ÷ d`) كان بيتغيّر بين القياسات ويقنّع الفرق بين
    الخطّي والتربيعي — ومرقت طفرة `count**2 ⟶ count`. بموضع بعيد
    حدّ المسافة بيصير مهمَلًا والتربيع لحاله بيقرّر.
    """
    one = penalty(1, [1], 1000)
    two = penalty(1, [1, 1], 1000)
    three = penalty(1, [1, 1, 1], 1000)
    assert one < two < three
    assert (three - two) > (two - one) + 0.5


def test_distance_softens_the_penalty():
    """أصل رجع بعد بُعد أرخص من أصل رجع فورًا."""
    near = penalty(1, [1, 2], 2)
    far = penalty(1, [1, 2, 3, 4, 5, 6], 6)
    assert near > far


def test_the_penalty_never_rejects_only_ranks():
    """**الترجيح بيفاضل، الحارس بيرفض.** خلطهما بيخلّي رقمًا كبيرًا
    يشتري مخالفة."""
    assert isinstance(penalty(1, [1] * 9, 20), float)   # ولا استثناء


# ── الشكل: دليل لا درجة ──────────────────────────────────────────────
def test_guards_return_evidence_not_a_score():
    t = tl([(1, 200), (2, 20), (3, 20)], {1: 0, 2: 0, 3: 0})
    v = hard_guards(t)
    assert v and all(hasattr(x, "rule") and hasattr(x, "detail") for x in v)
    assert all(not hasattr(x, "score") for x in v)

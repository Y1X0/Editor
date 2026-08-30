"""قيود الإيقاع — **مخالفة بدليل، لا درجة مجمّعة**.

كل فحص هون بيسأل سؤالًا واحدًا: هل القيد **بيقدر يفشل**؟ قيد ما بيقدر
يفشل مش قيدًا — هو تعليق.
"""
import pytest

from ai_pipeline.edit import BeatProposal, CueProposal, EditPlan, ShotProposal
from ai_pipeline.edit.pacing import (
    MAX_MOTION_SHARE, MAX_SAME_MOTION_RUN, MAX_SHOT_S, MIN_CUE_GAP_S, MIN_CV,
    MIN_SHOT_S, MIN_STATIC_SHARE, Violation, check_pacing, enforce_pacing,
)
from ai_pipeline.errors import TimelineError
from ai_pipeline.models.timeline import Span, Timeline


def tl(lengths):
    """timeline بمديات لقطات معطاة، 30fps."""
    acc, spans = 0, []
    for i, n in enumerate(lengths, start=1):
        spans.append(Span(segment_id=i, f_start=acc, f_end=acc + n))
        acc += n
    return Timeline(fps=30, sample_rate=48000, total_frames=acc,
                    visual_spans=tuple(spans),
                    text_spans=(Span(segment_id=1, f_start=0, f_end=acc),))


def plan(motions, energies=None, cues=(), roles=None):
    n = len(motions)
    roles = roles or ["demonstration"] * n
    energies = energies or ["calm"] * n
    beats = tuple(BeatProposal(beat_id=i + 1, segment_ids=(i + 1,),
                               role=roles[i], energy=energies[i])
                  for i in range(n))
    shots = tuple(ShotProposal(shot_id=i + 1, beat_id=i + 1, order=0,
                               motion=motions[i]) for i in range(n))
    return EditPlan(beats=beats, shots=shots, cues=tuple(cues))


def rules(v):
    return {x.rule for x in v}


# ── كل قيد بيقدر يفشل، وبيقدر ينجح ──────────────────────────────────
def test_a_shot_shorter_than_the_floor_is_flagged():
    v = check_pacing(plan(["static"] * 3), tl([10, 90, 60]))
    assert "min_shot_duration" in rules(v)
    assert any(0 in x.where for x in v if x.rule == "min_shot_duration")


def test_a_shot_longer_than_the_ceiling_is_flagged():
    v = check_pacing(plan(["static"] * 3), tl([30, 200, 60]))
    assert "max_shot_duration" in rules(v)


def test_identical_shot_lengths_are_flagged():
    """**«كل اللقطات بنفس المدة»** — أوضح بصمة آلية بالمونتاج."""
    v = check_pacing(plan(["static"] * 4), tl([60, 60, 60, 60]))
    assert "shot_variance" in rules(v)


def test_varied_shot_lengths_pass_the_variance_rule():
    v = check_pacing(plan(["static"] * 4), tl([25, 60, 40, 110]))
    assert "shot_variance" not in rules(v)


def test_one_motion_dominating_is_flagged():
    v = check_pacing(plan(["push"] * 5 + ["static"] * 2),
                     tl([25, 60, 40, 110, 35, 70, 50]))
    assert "motion_dominance" in rules(v)


def test_a_long_run_of_the_same_motion_is_flagged():
    """الهيمنة والتتابع **قيدان مختلفان**: حركة 40٪ بس متتالية بتضرب."""
    v = check_pacing(plan(["push"] * 4 + ["static"] * 6),
                     tl([25, 60, 40, 110, 35, 70, 50, 30, 90, 45]))
    assert "motion_run" in rules(v)


def test_a_broken_run_passes():
    v = check_pacing(plan(["push", "push", "static", "push", "static",
                           "drift", "static", "micro"]),
                     tl([25, 60, 40, 110, 35, 70, 50, 30]))
    assert "motion_run" not in rules(v)


def test_too_little_stillness_is_flagged():
    """الصمت البصري قرار لا بقية."""
    v = check_pacing(plan(["push", "drift", "pull", "micro"]),
                     tl([25, 60, 40, 110]))
    assert "static_share" in rules(v)


def test_enough_stillness_passes():
    v = check_pacing(plan(["static", "drift", "pull", "micro"]),
                     tl([80, 60, 40, 110]))
    assert "static_share" not in rules(v)


def test_dense_cues_are_flagged():
    """٢١ مؤثرًا بـ٤٠ ثانية كان مخرَج النظام قبل هالمرحلة."""
    cues = tuple(CueProposal(beat_id=1, kind="whoosh") for _ in range(20))
    v = check_pacing(plan(["static"] * 3, cues=cues), tl([30, 60, 90]))
    assert "cue_density" in rules(v)


def test_silence_cues_do_not_count_toward_density():
    """`silence` قرار بمنع مؤثر — بيعدّه مؤثرًا بيقلب معناه."""
    cues = tuple(CueProposal(beat_id=1, kind="silence") for _ in range(20))
    v = check_pacing(plan(["static"] * 3, cues=cues), tl([30, 60, 90]))
    assert "cue_density" not in rules(v)


def test_energy_falling_before_the_payoff_is_flagged():
    v = check_pacing(
        plan(["static"] * 3, energies=["driving", "calm", "release"],
             roles=["hook", "escalation", "payoff"]),
        tl([25, 60, 110]))
    assert "energy_slump" in rules(v)


def test_energy_may_fall_at_the_payoff_itself():
    """الهبوط **عند** الـpayoff انفراج، مش ترهّلًا — والقيد بيستثنيه."""
    v = check_pacing(
        plan(["static"] * 3, energies=["calm", "driving", "calm"],
             roles=["hook", "escalation", "payoff"]),
        tl([25, 60, 110]))
    assert "energy_slump" not in rules(v)


# ── الشكل: دليل لا درجة ──────────────────────────────────────────────
def test_a_violation_carries_evidence_not_a_score():
    """**ممنوع `visual_score`.** المخالفة بتسمّي القاعدة وبتعطي الدليل."""
    v = check_pacing(plan(["static"] * 4), tl([60, 60, 60, 60]))
    x = next(i for i in v if i.rule == "shot_variance")
    assert isinstance(x, Violation)
    assert "CV" in x.detail and str(MIN_CV) in x.detail
    assert not hasattr(x, "score")
    for name in ("score", "visual_score", "rating", "grade"):
        assert not any(name in f for f in Violation.__dataclass_fields__)


def test_a_clean_plan_reports_nothing():
    v = check_pacing(plan(["static", "push", "static", "drift"]),
                     tl([80, 45, 100, 30]))
    assert v == [], [str(x) for x in v]


def test_enforce_raises_and_names_the_rules():
    with pytest.raises(TimelineError, match="shot_variance"):
        enforce_pacing(plan(["static"] * 4), tl([60, 60, 60, 60]))


def test_check_never_raises_even_on_a_terrible_plan():
    """الفصل مقصود: الإيقاع **حكم على الخطة**، ما بينفجر."""
    v = check_pacing(plan(["push"] * 8), tl([10] * 8))
    assert len(v) >= 4 and all(isinstance(x, Violation) for x in v)


def test_stillness_is_exempt_from_the_dominance_rule():
    """**قيدان متناقضان لولا الاستثناء.**

    `static_share` بيطلب حدًّا **أدنى** للسكون، و`motion_dominance`
    بيطلب حدًّا **أعلى** لكل حركة. لو خضع السكون للاتنين، أي خطة
    بسكون بين 45٪ و... مستحيلة. والرتابة اللي بيلتقطها المشاهد هي
    تكرار **حركة**، والسكون غيابها.

    انكشف بفحص «خطة نظيفة»: خطة سليمة اتُّهمت بهيمنة `static` عند 50٪.
    """
    v = check_pacing(plan(["static"] * 5 + ["push", "drift"]),
                     tl([80, 45, 100, 30, 60, 35, 90]))
    assert "motion_dominance" not in rules(v)
    assert "static_share" not in rules(v)
    # وحركة حقيقية بنفس النسبة **بتضرب**
    v2 = check_pacing(plan(["push"] * 5 + ["static", "drift"]),
                      tl([80, 45, 100, 30, 60, 35, 90]))
    assert "motion_dominance" in rules(v2)

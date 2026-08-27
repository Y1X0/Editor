"""
خطة المؤثرات — وحدات نقية، ولا نداء ffmpeg.

نفس منهج `test_graph.py`: أرقام داخل، أرقام برّا. أي شي بيحتاج ffmpeg
مكانه `test_sfx_acceptance.py`.
"""
import pytest

from autoreel import sfx as X

FPS, SR = 30, 48000
SPF = SR // FPS                      # ١٦٠٠ عيّنة للإطار
PLAN = [60, 75, 60, 45]              # ٢٤٠ إطار، حدود عند ٦٠ · ١٣٥ · ١٩٥


def cfg(**kw):
    """إعداد بكل الأحداث مطفية إلا اللي بينطلب — عشان يُعزل الفحص."""
    events = {k: {"enabled": False} for k in X.PRIORITY}
    for k in kw.pop("on", ()):
        events[k] = {"enabled": True}
    base = {"events": events}
    base.update(kw)
    return base


# ------------------------------------------------------- التحويل الصحيح

def test_frame_to_sample_is_integer_multiplication():
    assert X.frame_to_sample(0, FPS) == 0
    assert X.frame_to_sample(1, FPS) == 1600
    assert X.frame_to_sample(180, FPS) == 288000
    assert X.frame_to_sample(50, 25) == 96000


def test_frame_to_sample_refuses_a_rate_that_does_not_divide():
    """
    ٤٨٠٠٠/٢٩ مش عددًا صحيحًا، يعني الحدث ما إله موقع عيّنة واحد.
    الفشل هون أوضح من تقريب صامت بينزاح مع الطول.
    """
    with pytest.raises(ValueError):
        X.frame_to_sample(1, 29)
    with pytest.raises(ValueError):
        X.samples_per_frame(29)


def test_every_cue_sample_is_its_frame_times_spf():
    cues = X.plan_cues(PLAN, FPS, caption_frames=[10, 40, 100, 200],
                       cfg=cfg(on=("caption",)))
    assert cues
    for c in cues:
        assert c.sample == c.frame * SPF


def test_seconds_reach_frames_only_once_at_the_edge():
    assert X.seconds_to_frames(0.12, 30) == 4
    assert X.seconds_to_frames(0.12, 25) == 3
    assert X.seconds_to_frames(0, 30) == 0
    assert X.seconds_to_frames(-1, 30) == 0


# ------------------------------------------------------- مصادر الأحداث

def test_segment_and_cut_frames_come_from_the_plan():
    assert X.segment_start_frames(PLAN) == [0, 60, 135, 195]
    assert X.cut_frames(PLAN) == [60, 135, 195]


def test_the_first_frame_is_not_a_cut():
    assert 0 not in X.cut_frames(PLAN)


def test_zoom_events_only_where_the_value_changed():
    assert X.zoom_change_frames(PLAN, [1.0, 1.0, 1.0, 1.0]) == []
    assert X.zoom_change_frames(PLAN, [1.0, 1.1, 1.1, 1.0]) == [60, 195]


def test_zoom_length_must_match_the_plan():
    with pytest.raises(ValueError):
        X.zoom_change_frames(PLAN, [1.0, 1.1])


def test_finale_is_the_last_segment_start_and_needs_two_segments():
    assert X.finale_frame(PLAN) == 195
    assert X.finale_frame([240]) is None


def test_events_outside_the_output_range_are_dropped():
    ev = X.collect_events(PLAN, caption_frames=[-5, 0, 239, 240, 900],
                          cfg=cfg(on=("caption",)))
    assert [e.frame for e in ev] == [0, 239]


def test_word_events_are_off_by_default():
    """مقيس: ٥٨ مؤثر/دقيقة بدون `word`، و٢١١ معه."""
    assert X.DEFAULTS["events"]["word"]["enabled"] is False
    ev = X.collect_events(PLAN, word_frames=[5, 15, 25])
    assert not [e for e in ev if e.kind == "word"]


# ------------------------------------------------------------ min_gap

def test_min_gap_keeps_one_cue_per_window():
    ev = [X.Event(f, "caption") for f in (10, 11, 12, 30, 31, 100)]
    kept = X.suppress(ev, gap_frames=4)
    assert [e.frame for e in kept] == [10, 30, 100]


def test_min_gap_zero_keeps_everything():
    ev = [X.Event(f, "caption") for f in (10, 11, 12)]
    assert len(X.suppress(ev, 0)) == 3


def test_the_stronger_event_wins_the_window_not_the_earlier_one():
    """
    **الحالة اللي فرضت قاعدة الأولوية.** مقيس على كلام واقعي: تغيّرات
    الزوم بتقع على نفس إطارات حدود المقاطع (١٥ و١٥). لو "الأول بيفوز"،
    `zoom` اللي سبق `cut` بإطار بيبلع القطة.
    """
    kept = X.suppress([X.Event(59, "zoom"), X.Event(60, "cut")], gap_frames=4)
    assert [(e.frame, e.kind) for e in kept] == [(60, "cut")]


def test_same_frame_collision_resolves_by_priority():
    kept = X.suppress([X.Event(60, "zoom"), X.Event(60, "cut"),
                       X.Event(60, "caption")], gap_frames=4)
    assert [e.kind for e in kept] == ["cut"]


def test_a_tie_in_priority_takes_the_earlier_frame():
    kept = X.suppress([X.Event(12, "caption"), X.Event(10, "caption")], 4)
    assert [e.frame for e in kept] == [10]


def test_the_window_is_bounded_and_does_not_chain():
    """
    لو النافذة كانت سلسلة متصلة، كابشنات متتابعة كل واحد بعد التاني
    بإطارين بتنبلع كلها بمؤثر واحد. النافذة الثابتة بتحدّ الابتلاع.
    """
    ev = [X.Event(f, "caption") for f in range(0, 40, 2)]
    kept = X.suppress(ev, gap_frames=4)
    assert len(kept) == 10
    assert [e.frame for e in kept] == list(range(0, 40, 4))


def test_min_gap_is_applied_through_plan_cues():
    cues = X.plan_cues(PLAN, FPS, caption_frames=[10, 11, 12],
                       cfg=cfg(on=("caption",), min_gap=0.12))
    assert [c.frame for c in cues] == [10]


# -------------------------------------------------------- max_concurrent

def test_concurrency_is_not_enforced_without_durations():
    """موثّق صراحة: بلا مدد ما في تطبيق — مش سكوتًا."""
    cues = [X.Cue(f, f * SPF, "caption", "pop", 0.25) for f in (0, 1, 2, 3)]
    assert len(X.limit_concurrent(cues, 2, durations=None)) == 4


def test_concurrency_limit_drops_the_weakest():
    cues = [X.Cue(0, 0, "caption", "pop", 0.25),
            X.Cue(1, SPF, "zoom", "whoosh", 0.18),
            X.Cue(2, 2 * SPF, "cut", "whoosh", 0.22)]
    kept = X.limit_concurrent(cues, 2, durations={"pop": 30, "whoosh": 30})
    assert len(kept) == 2
    # الأقوى بيبقوا — والمخرَج مرتّب **بالإطار** مش بالأولوية
    assert {c.kind for c in kept} == {"cut", "zoom"}
    assert [c.frame for c in kept] == [1, 2]


def test_non_overlapping_cues_are_never_dropped():
    cues = [X.Cue(f, f * SPF, "caption", "pop", 0.25) for f in (0, 50, 100)]
    kept = X.limit_concurrent(cues, 1, durations={"pop": 10})
    assert len(kept) == 3


# ------------------------------------------------------------ الخطة

def test_plan_is_deterministic():
    a = X.plan_cues(PLAN, FPS, zooms=[1.0, 1.1, 1.0, 1.1],
                    caption_frames=[5, 40, 100, 210])
    b = X.plan_cues(PLAN, FPS, zooms=[1.0, 1.1, 1.0, 1.1],
                    caption_frames=[5, 40, 100, 210])
    assert a == b


def test_disabled_yields_nothing():
    assert X.plan_cues(PLAN, FPS, caption_frames=[10],
                       cfg={"enabled": False}) == []


def test_cues_are_sorted_by_frame():
    cues = X.plan_cues(PLAN, FPS, zooms=[1.0, 1.1, 1.2, 1.0],
                       caption_frames=[3, 40, 100, 150, 210])
    assert [c.frame for c in cues] == sorted(c.frame for c in cues)


def test_every_cue_carries_a_known_asset_and_a_positive_gain():
    cues = X.plan_cues(PLAN, FPS, zooms=[1.0, 1.1, 1.2, 1.0],
                       caption_frames=[3, 40, 100, 150, 210])
    assert cues
    for c in cues:
        assert c.asset in ("tick", "pop", "whoosh", "impact", "riser")
        assert 0.0 < c.gain <= 1.0


def test_the_gain_ceiling_respects_the_measured_headroom():
    """
    الهامش المقاس: كلام مطبَّع ٠.٧٠ + ذروة أصل ٠.٩٠ × كسب. الكسب
    ٠.٢٥ بيعطي ٠.٩٢٥ < ١.٠ — ولا عيّنة مقصوصة. أي كسب افتراضي
    بيتعدّى ٠.٣٣ بيكسر الحدّ.
    """
    for kind, spec in X.DEFAULTS["events"].items():
        assert 0.70 + 0.90 * spec["gain"] < 1.0, f"{kind} بيكسر الهامش"


def test_asset_usage_counts_for_asplit():
    cues = [X.Cue(0, 0, "caption", "pop", 0.25),
            X.Cue(10, 16000, "caption", "pop", 0.25),
            X.Cue(20, 32000, "cut", "whoosh", 0.22)]
    assert X.asset_usage(cues) == {"pop": 2, "whoosh": 1}


def test_asset_usage_is_empty_for_no_cues():
    assert X.asset_usage([]) == {}


# ------------------------------------------------------------ الحرّاس

def test_assert_within_rejects_out_of_range():
    with pytest.raises(ValueError):
        X.assert_within([X.Cue(240, 384000, "cut", "whoosh", 0.22)], 240)


def test_assert_within_rejects_two_cues_on_one_frame():
    """مؤثران بنفس اللحظة بيجمعوا ذروتهن — أقرب طريق للقصّ."""
    with pytest.raises(ValueError):
        X.assert_within([X.Cue(5, 8000, "cut", "whoosh", 0.22),
                         X.Cue(5, 8000, "caption", "pop", 0.25)], 240)


def test_a_real_plan_passes_its_own_guard():
    cues = X.plan_cues(PLAN, FPS, zooms=[1.0, 1.1, 1.2, 1.0],
                       caption_frames=[3, 40, 100, 150, 210])
    X.assert_within(cues, sum(PLAN))


def test_unknown_event_kind_is_refused():
    with pytest.raises(ValueError):
        X.Event(0, "explosion")


# ------------------------------------------------- الحالة الواقعية المقاسة

def test_the_measured_collision_case_collapses_to_one_cue():
    """
    السيناريو المقاس بـ§C.5: كل حدّ مقطع بيحمل `cut` و`zoom` سوا.
    النتيجة لازم تكون مؤثرًا واحدًا لكل حدّ، مش اتنين.
    """
    zooms = [1.0, 1.1, 1.2, 1.0]                 # الزوم بيتغيّر بكل حدّ
    cues = X.plan_cues(PLAN, FPS, zooms=zooms, cfg=cfg(on=("cut", "zoom")))
    assert [c.frame for c in cues] == [60, 135, 195]
    assert {c.kind for c in cues} == {"cut"}

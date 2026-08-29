"""
`graph.zoom_plan` — نوافذ الزوم مفكوكة عن المقاطع.

اللي بينكسر بصمت لو انكسر: مجموع الخطة. الصورة والصوت والكابشن
التلاتة مبنيين على `Σ frame_plan`، فأي نافذة بتزيد أو تنقص إطارًا
بتزحلق المخرَج كله.
"""
import pytest

from autoreel import graph as G

CFG = {"motion": {"enabled": True, "zoom_cycle": [1.0, 1.1], "zoom_every": 2.0}}


def cfg(**over):
    c = {"motion": dict(CFG["motion"])}
    c["motion"].update(over)
    return c


def test_sum_is_preserved_exactly():
    """المجموع هو مصدر الحقيقة — لا إطار بيزيد ولا بينقص."""
    for plan in ([300], [137, 401, 59], [1], [29, 30, 31], [7] * 40):
        out = G.zoom_plan(plan, 30, cfg())
        assert sum(out) == sum(plan), (plan, out)


def test_zero_or_missing_keeps_the_old_behaviour():
    plan = [300, 150]
    assert G.zoom_plan(plan, 30, cfg(zoom_every=0)) == plan
    assert G.zoom_plan(plan, 30, {"motion": {"enabled": True,
                                             "zoom_cycle": [1.0]}}) == plan
    assert G.zoom_plan(plan, 30, {}) == plan


def test_disabled_motion_never_subdivides():
    """`enabled: false` بتسطّح الزوم، فتقسيم النوافذ بلا معنى."""
    assert G.zoom_plan([300], 30, cfg(enabled=False)) == [300]


def test_windows_do_not_exceed_the_interval():
    out = G.zoom_plan([300], 30, cfg(zoom_every=2.0))
    assert max(out) <= 60, out


def test_segment_boundaries_stay_window_boundaries():
    """
    التقسيم جوّا كل مقطع. لو نافذة عبرت حدّ مقطع، القطة الحقيقية بتفقد
    تغيّر الزوم اللي كان عندها.
    """
    plan = [100, 100]
    out = G.zoom_plan(plan, 30, cfg(zoom_every=1.0))
    edges, acc = set(), 0
    for n in out:
        acc += n
        edges.add(acc)
    assert 100 in edges and 200 in edges, out


def test_windows_inside_a_segment_are_even():
    """بقية غير موزّعة = شظية بتلمع لإطارين."""
    out = G.zoom_plan([100], 30, cfg(zoom_every=1.0))
    assert max(out) - min(out) <= 1, out


def test_segment_shorter_than_the_interval_stays_whole():
    assert G.zoom_plan([12], 30, cfg(zoom_every=2.0)) == [12]


def test_every_window_is_positive():
    """نافذة صفر بتعطي `between(n,a,a-1)` — حدّ ميت بالمجموع."""
    for plan in ([1], [3], [61], [59]):
        assert all(n > 0 for n in G.zoom_plan(plan, 30, cfg())), plan


def test_piecewise_accepts_the_subdivided_plan():
    """العقد الحقيقي: `piecewise` بتلزمها تطابق الأطوال التلاتة."""
    plan = G.zoom_plan([300, 150], 30, cfg())
    zooms = G.zoom_values(CFG, len(plan))
    expr = G.piecewise(zooms, G.offsets_of(plan), plan)
    assert expr.count("between") == len(plan)

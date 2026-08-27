"""
باني رسم المسار الواحد — دوال نقية، بلا ffmpeg.

U1..U7 من `REDESIGN-SPEC.md` §9.3، وزيادة: فحوص بتقارن هندسة الزوم
الجديدة بـ`render.segment_filter` القائمة، حتى ما يصير نسختين من نفس
الحساب بتفترقوا مع الوقت.
"""
import re

import pytest

from autoreel import graph as G
from autoreel import render as R


def cfg_of(base, **over):
    c = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in over.items():
        a, b = k.split(".")
        c[a] = dict(c.get(a, {}))
        c[a][b] = v
    return c


# ------------------------------------------------------- U6: fps كسري

@pytest.mark.parametrize("fps", [29.97, 59.94, 23.976])
def test_u6_fractional_fps_is_rejected_with_a_clear_error(fps):
    with pytest.raises(ValueError, match="كسري"):
        G.validate_fps(fps)


@pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
def test_u6_integer_rates_that_divide_48k_are_accepted(fps):
    assert G.validate_fps(fps) == fps


def test_u6_rate_that_does_not_divide_the_sample_rate_is_rejected():
    """
    ٤٤١٠٠ مع ٣٢fps = ١٣٧٨.١٢٥ عيّنة/إطار. حدود العيّنات بتتقرّب وبينزاح
    الصوت. (٤٤١٠٠/٣٠ = ١٤٧٠ بالضبط، فهي مش مثال صالح — أول نسخة من
    هالفحص وقعت بهالغلطة.)
    """
    with pytest.raises(ValueError, match="ما بينقسم"):
        G.validate_fps(32, sr=44100)


def test_u6_float_that_is_a_whole_number_is_fine():
    assert G.validate_fps(30.0) == 30


# ------------------------------------------------ U1: تعبير select

def test_u1_select_covers_exactly_the_planned_frames():
    starts, plan = [10, 40, 100], [5, 7, 3]
    kept = _frames_kept(G.select_expr(starts, plan), 200)
    assert len(kept) == sum(plan) == 15
    assert kept == [10, 11, 12, 13, 14, 40, 41, 42, 43, 44, 45, 46, 100, 101, 102]


def test_u1_ranges_are_inclusive_on_both_ends():
    """مدى `between(n,s,s+n-1)` لازم يعطي `n` إطار بالضبط، مش n±1."""
    for n in (1, 2, 17):
        assert len(_frames_kept(G.select_expr([5], [n]), 100)) == n


def test_u1_overlapping_ranges_are_rejected_not_silently_shortened():
    """
    `select` بتمرّر إطار المصدر مرة وحدة، فالتداخل بيقلّل العدد بصمت.
    """
    with pytest.raises(ValueError, match="متداخلة"):
        G.assert_disjoint([10, 12], [5, 5])


def test_u1_touching_ranges_are_allowed():
    """مقطع بينتهي عند ١٥ والتاني بيبلّش ١٥ — ما في تداخل."""
    G.assert_disjoint([10, 15], [5, 5])


def test_u1_start_frames_land_on_the_grid():
    segs = [(1.237, 2.0), (4.512, 5.0)]
    assert G.start_frames(segs, 30) == [37, 135]


def _frames_kept(expr, upto):
    """تقييم تعبير `select` بايثونيًا — نفس دلالة `between` المغلقة."""
    terms = [(int(a), int(b)) for a, b in
             re.findall(r"between\(n,(\d+),(\d+)\)", expr)]
    return [n for n in range(upto) if any(a <= n <= b for a, b in terms)]


# --------------------------------------------- piecewise (أساس الزوم)

def _eval_piecewise(expr, n):
    total = 0.0
    for v, a, b in re.findall(r"(-?[\d.]+)\*between\(n\\,(\d+)\\,(\d+)\)", expr):
        if int(a) <= n <= int(b):
            total += float(v)
    return total


def test_piecewise_picks_exactly_one_term_per_frame():
    plan = [4, 3, 5]
    off = G.offsets_of(plan)
    expr = G.piecewise([100, 200, 300], off, plan)
    got = [_eval_piecewise(expr, n) for n in range(sum(plan))]
    assert got == [100] * 4 + [200] * 3 + [300] * 5


def test_piecewise_keeps_a_value_past_the_last_frame():
    """
    لو طلب المرمِّز إطارًا بعد الآخر، المجموع لازم يضل صالحًا. صفر
    بـ`scale` = خطأ تشغيل.
    """
    plan = [3, 3]
    expr = G.piecewise([10, 20], G.offsets_of(plan), plan)
    assert _eval_piecewise(expr, 99) == 20


def test_piecewise_escapes_the_comma():
    """الفاصلة غير المهروبة بتفصل وسائط الفلتر وبتكسر الرسم."""
    expr = G.piecewise([1], [0], [1])
    assert "\\," in expr and re.search(r"between\(n,[^\\]", expr) is None


def test_offsets_are_cumulative():
    assert G.offsets_of([4, 3, 5]) == [0, 4, 7]


# ------------------------------------------------------- U2: حدود الصوت

def test_u2_audio_boundaries_are_whole_samples():
    """
    الحدود بفهرس العيّنة، بلا أي عائمة.

    ملاحظة أمانة: قِسنا الثواني مقابل العيّنات على ٤٠ مقطع وطلعوا
    **متطابقين** (١.٩٨ms أقصى، تراكم صفر، ٧٦٨٠٠٠ عيّنة للاتنين). يعني
    هاد مش تصليح لخلل مقاس — هاد ضبط **بالبناء** بدل الاعتماد على
    تفاصيل طباعة عشرية وتحليل مدّة داخل ffmpeg.
    """
    fps, sr = 30, 48000
    starts, plan = [37, 135], [18, 24]
    parts = " ".join(G.audio_chain(fps, starts, plan, ["ao0"], sr=sr))
    pairs = re.findall(r"atrim=start_sample=(\d+):end_sample=(\d+)", parts)
    assert len(pairs) == len(plan), "الحدود مش بفهرس العيّنة"
    for (a, b), s, n in zip(pairs, starts, plan):
        assert int(a) == s * (sr // fps)
        assert int(b) == (s + n) * (sr // fps)


def test_u2_audio_segments_sum_to_the_video_duration():
    fps, plan = 30, [18, 24, 7]
    starts = [37, 135, 300]
    parts = " ".join(G.audio_chain(fps, starts, plan, ["ao0"]))
    spans = [(int(a), int(b)) for a, b in
             re.findall(r"atrim=start_sample=(\d+):end_sample=(\d+)", parts)]
    sr = G.DEFAULT_SR
    assert sum(b - a for a, b in spans) == sum(plan) * (sr // fps)
    assert sum(b - a for a, b in spans) / sr == pytest.approx(sum(plan) / fps)


def test_u2_audio_is_never_encoded_before_the_output():
    """
    كل الترميز لازم يصير مرة وحدة بالمخرَج النهائي — هاد اللي بيلغي
    تراكم priming padding.
    """
    parts = " ".join(G.audio_chain(30, [0], [10], ["ao0"]))
    assert "aac" not in parts and "libmp3" not in parts


def test_u2_one_output_gets_anull_not_asplit_of_one():
    """مخرَج واحد ما بده `asplit` — بس انتبه: في `asplit` تاني للمقاطع."""
    parts = " ".join(G.audio_chain(30, [0], [10], ["ao0"]))
    assert "[acat]anull[ao0]" in parts
    assert "asplit=1[ao0]" not in parts


def test_u2_several_outputs_each_get_their_own_audio_label():
    """
    قيد ffmpeg: تسمية مخرَج الفلتر بتنربط **مرة وحدة**. بدون `asplit`
    التشغيلة بتفشل بـ"label does not exist… or was already used".
    """
    parts = " ".join(G.audio_chain(30, [0], [10], ["ao0", "ao1", "ao2"]))
    assert "asplit=3[ao0][ao1][ao2]" in parts


# -------------------------------------------------- U3: إطارات الكابشن

def test_u3_caption_frames_are_indices_not_seconds():
    caps = [("a.png", 0.0, 0.5), ("b.png", 0.5, 1.0)]
    assert G.caption_frames(caps, 30, 30) == [("a.png", 0, 15), ("b.png", 15, 30)]


def test_u3_caption_frames_never_overlap():
    caps = [("a.png", 0.0, 0.60), ("b.png", 0.50, 1.0)]
    out = G.caption_frames(caps, 30, 30)
    for i in range(len(out) - 1):
        assert out[i][2] <= out[i + 1][1]


def test_u3_caption_frames_are_clamped_to_the_output():
    caps = [("a.png", 0.0, 99.0)]
    assert G.caption_frames(caps, 30, 12) == [("a.png", 0, 12)]


def test_u3_captions_past_the_end_are_dropped():
    caps = [("a.png", 0.0, 0.2), ("late.png", 50.0, 51.0)]
    assert [p for p, _, _ in G.caption_frames(caps, 30, 12)] == ["a.png"]


def test_u3_every_caption_gets_at_least_one_frame():
    """كابشن أقصر من إطار لازم ياخد إطارًا، مش يختفي."""
    caps = [("a.png", 0.0, 0.001), ("b.png", 0.001, 0.5)]
    assert all(b > a for _, a, b in G.caption_frames(caps, 30, 30))


# --------------------------------------------------- U4: تسلسل الكابشن

def test_u4_sequence_has_one_entry_per_output_frame():
    seq = G.caption_sequence([("a.png", 0, 4), ("b.png", 4, 9)], 9)
    assert len(seq) == 9


def test_u4_each_frame_points_at_the_right_png():
    seq = G.caption_sequence([("a.png", 0, 4), ("b.png", 4, 9)], 9)
    assert seq == ["a.png"] * 4 + ["b.png"] * 5


def test_u4_frames_with_no_caption_are_none():
    seq = G.caption_sequence([("a.png", 2, 4)], 6)
    assert seq == [None, None, "a.png", "a.png", None, None]


def test_u4_sequence_is_not_affected_by_floats():
    """
    الفهرس هو الزمن. لو دخل حساب زمني هون بترجع مشكلة قاعدة ١/٢٥
    من الباب الخلفي.
    """
    caps = G.caption_frames([("a.png", 6.3, 6.7)], 30, 300)
    assert caps[0][1] == 189 and caps[0][2] == 201


# ----------------------------------------------- الجذع: ترتيب الفلاتر

def test_stem_puts_fps_after_setpts():
    """
    `setpts` بتمسح معدّل الإطارات، فبدون `fps` بعدها ffmpeg بيرجع لـ٢٥
    ويعيد التشكيل — ٦٠٠ إطار بتصير ٥٠١.
    """
    s = G.video_stem(30, [0], [10])
    assert s.index("setpts=N") < s.index("fps=30[")


def test_stem_uses_settb_not_a_float_division():
    """
    `setpts=N/FPS/TB` بتحسب بعائمة وبتسقّط إطارًا وتكرّر تاني مع بقاء
    العدد صحيح. مقاس ٢ من ٣٣٦ — وE1 عمياء عنه.
    """
    s = G.video_stem(30, [0], [10])
    assert "settb=1/30" in s and "setpts=N," in s
    assert "/TB" not in s


def test_stem_normalises_before_select():
    """`n` لازم يكون فهرس شبكة، مش رقم الإطار المفكوك من مصدر VFR."""
    s = G.video_stem(30, [0], [10])
    assert s.index("fps=30,select") < s.index("select=")+1


def test_stem_rejects_overlapping_segments():
    with pytest.raises(ValueError, match="متداخلة"):
        G.video_stem(30, [0, 5], [10, 10])


def test_split_of_one_is_not_a_split():
    assert G.split_chain("stem", ["z0"]) == "[stem]null[z0]"


def test_split_of_many_feeds_every_size():
    assert G.split_chain("stem", ["z0", "z1", "z2"]) == "[stem]split=3[z0][z1][z2]"


# ------------------------------- الزوم: مطابقة `render.segment_filter`

BASE = {
    "output": {"width": 1080, "height": 1920, "fps": 30, "crf": 20},
    "motion": {"enabled": True, "zoom_cycle": [1.0, 1.1, 1.04, 1.14], "pan_px": 26},
    "geometry": {"fit": "crop", "crop_bias": 0.5, "pad_blur": 24},
    "captions": {"y_ratio": 0.72},
}


def _dims_from_segment_filter(cfg, zoom, pan_dir):
    vf = R.segment_filter(cfg, zoom=zoom, pan_dir=pan_dir)
    m = re.search(r"scale=(\d+):(\d+)", vf)
    return int(m.group(1)), int(m.group(2))


@pytest.mark.parametrize("zoom", [1.0, 1.04, 1.1, 1.14, 1.25])
def test_zoom_dims_match_the_existing_segment_filter(zoom):
    """
    نسختين من نفس الحساب بيفترقوا مع الوقت. هالفحص بيربطهن: لو حدا
    غيّر تقريب `_even` بمكان وما غيّره بالتاني، بينكسر.
    """
    sws, shs = G.zoom_dims(BASE, [zoom])
    assert (sws[0], shs[0]) == _dims_from_segment_filter(BASE, zoom, 0)


def _dx_from_segment_filter(cfg, zoom, pan_dir):
    vf = R.segment_filter(cfg, zoom=zoom, pan_dir=pan_dir)
    m = re.search(r"crop=\d+:\d+:\(iw-\d+\)/2([+-]\d+)", vf)
    return int(m.group(1))


@pytest.mark.parametrize("zoom", [1.0, 1.04, 1.1, 1.14])
def test_pan_offsets_match_the_existing_segment_filter(zoom):
    """الـpan محدود بالهامش المتاح — نفس الحدّ بالمكانين."""
    assert G.pan_offsets(BASE, [zoom])[0] == _dx_from_segment_filter(BASE, zoom, 1)
    assert G.pan_offsets(BASE, [zoom, zoom])[1] == _dx_from_segment_filter(
        BASE, zoom, -1)


def test_zoom_values_follow_the_cycle():
    assert G.zoom_values(BASE, 6) == [1.0, 1.1, 1.04, 1.14, 1.0, 1.1]


def test_zoom_disabled_means_no_zoom():
    assert G.zoom_values(cfg_of(BASE, **{"motion.enabled": False}), 4) == [1.0] * 4


def test_size_chain_never_anchors_with_iw_or_ih():
    """
    **حارس انحدار على خلل حقيقي.**

    `crop` بتقيّم `x`/`y` لكل إطار، بس `iw`/`ih` جواتهن بتتقيّدوا وقت
    ضبط الوصلة وما بيتتبّعوا مقاس مدخَل متغيّر. قِسناها: مع `scale`
    متغيّر، `x='(iw-540)/2'` أعطى إطارًا **مختلفًا** عن الرقم الصح ٣٧.
    الأثر كان مقاطع الزوم العالي بتنقصّ من مكان غلط.

    بالمعمارية القديمة التعبير كان صح (كل مقطع تشغيلة بمقاس ثابت).
    بالمسار الواحد لازم أرقام محسوبة.
    """
    c = G.size_chain(BASE, [5, 5], [1.0, 1.1], "z0", "g0", 640, 1138)
    x = re.search(r"crop=\d+:\d+:x='([^']+)':y='([^']+)'", c)
    assert x, "ما لقيت تعبير القصّ"
    assert "iw" not in x.group(1) and "ih" not in x.group(2)
    assert "in_w" not in c and "in_h" not in c


def test_size_chain_anchor_matches_the_scaled_dimensions():
    """المرساة لازم تنحسب على أبعاد **بعد** `increase`، مش على sw/sh."""
    cfg = cfg_of(BASE, **{"output.width": 540, "output.height": 960})
    c = G.size_chain(cfg, [5], [1.14], "z0", "g0", 640, 1138)
    iw, ih = G.scaled_dims(640, 1138, 614, 1094)
    assert (iw, ih) == (615, 1094)
    xs = [int(v) for v in re.findall(r"(-?\d+)\*between", 
                                     re.search(r"x='([^']+)'", c).group(1))]
    assert xs[0] == (615 - 540) // 2 + G.pan_offsets(cfg, [1.14])[0]


@pytest.mark.parametrize("sw,sh,want", [
    (540, 960, (540, 960)),
    (594, 1056, (594, 1056)),
    (560, 998, (561, 998)),
    (614, 1094, (615, 1094)),
])
def test_scaled_dims_matches_ffmpeg_increase(sw, sh, want):
    """قيم مقاسة من ffmpeg على مصدر ٦٤٠×١١٣٨ — منها حالتان بنسبة مختلفة."""
    assert G.scaled_dims(640, 1138, sw, sh) == want


def test_size_chain_uses_eval_frame():
    """بدونها الزوم بينتقيّم مرة وحدة وبينثبت على أول مقطع."""
    assert "eval=frame" in G.size_chain(BASE, [5], [1.0], "z0", "g0", 640, 1138)


def test_size_chain_pad_zooms_only_the_background():
    """
    نمط `pad`: ما في punch-in على المقدّمة. لو كبّرناها بترجع تنقصّ
    وبيلغي سبب وجود `pad`.
    """
    c = G.size_chain(cfg_of(BASE, **{"geometry.fit": "pad"}), [5], [1.1],
                     "z0", "g0", 640, 1138)
    assert "gblur" in c and "eval=frame" in c
    assert c.count("eval=frame") == 1, "الزوم انطبق على المقدّمة كمان"
    assert "decrease" in c


def test_size_chain_rejects_unknown_fit():
    with pytest.raises(ValueError, match="fit"):
        G.size_chain(cfg_of(BASE, **{"geometry.fit": "stretch"}), [5], [1.0],
                     "z0", "g0", 640, 1138)


# --------------------------------------------------- U5/U7: الرسم كامل

def test_build_graph_makes_one_map_per_size():
    g, maps = G.build_graph(BASE, [5, 5], [0, 10],
                            [("reel", BASE), ("square", BASE)], 640, 1138)
    assert [n for n, _, _ in maps] == ["reel", "square"]
    assert len({a for _, a, _ in maps}) == 2
    assert len({a for _, _, a in maps}) == 2, "مقاسان بيتقاسموا نفس تسمية الصوت"


def test_build_graph_has_a_single_source_decode():
    g, _ = G.build_graph(BASE, [5], [0], [("reel", BASE)] * 3, 640, 1138)
    assert g.count("[0:v]") == 1 and g.count("[0:a]") == 1


def test_build_graph_wires_captions_when_given():
    g, maps = G.build_graph(BASE, [5], [0], [("reel", BASE)], 640, 1138,
                            caption_inputs={"reel": 1})
    assert "[1:v]fps=30[cap0]" in g and "overlay" in g
    assert maps[0][1] == "m0"


def test_build_graph_without_captions_maps_the_zoomed_stream():
    g, maps = G.build_graph(BASE, [5], [0], [("reel", BASE)], 640, 1138)
    assert "overlay" not in g and maps[0][1] == "g0"


def test_build_graph_rejects_a_fractional_fps():
    with pytest.raises(ValueError, match="كسري"):
        G.build_graph(cfg_of(BASE, **{"output.fps": 29.97}), [5], [0],
                      [("reel", BASE)], 640, 1138)


def test_build_graph_rejects_overlapping_segments():
    with pytest.raises(ValueError, match="متداخلة"):
        G.build_graph(BASE, [10, 10], [0, 5], [("reel", BASE)], 640, 1138)


def test_u7_graph_is_long_enough_to_need_a_script_file():
    """
    ٣٠٠ مقطع بتعطي عشرات الكيلوبايتات. حدود سطر الأوامر على أندرويد
    أضيق من لينكس، فـ`-filter_complex_script` شرط مش تفضيل.
    """
    plan = [3] * 300
    starts = [i * 10 for i in range(300)]
    g, _ = G.build_graph(BASE, plan, starts, [("reel", BASE)], 640, 1138)
    assert len(g) > 20_000


def test_caption_overlay_is_centred_at_the_configured_ratio():
    g, _ = G.build_graph(BASE, [5], [0], [("reel", BASE)], 640, 1138,
                         caption_inputs={"reel": 1})
    assert f"y={int(1920 * 0.72)}-h/2" in g

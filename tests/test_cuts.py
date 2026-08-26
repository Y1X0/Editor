"""خطة القص وإعادة تخطيط التوقيتات — دوال نقية، بلا ffmpeg."""
import pytest

from autoreel.cuts import remap_words, segments_from_words, total_after_cut
from conftest import words


# ---------------------------------------------------------------- segments

def test_no_words_returns_whole_clip():
    assert segments_from_words([], 12.0) == [(0.0, 12.0)]


def test_long_gap_splits_short_gap_does_not():
    w = words(("a", 0.0, 0.5), ("b", 0.7, 1.2), ("c", 3.0, 3.5))
    segs = segments_from_words(w, 5.0, min_gap=0.45, pad=0.10)
    assert len(segs) == 2                      # 0.20 ما بتقص، 1.80 بتقص
    assert segs[0] == pytest.approx((0.0, 1.3))
    assert segs[1] == pytest.approx((2.9, 3.6))


def test_gap_exactly_min_gap_survives():
    """الشرط `> min_gap` — الفجوة اللي بتساويه بالضبط بتنجى."""
    w = words(("a", 0.0, 0.5), ("b", 0.95, 1.4))
    assert len(segments_from_words(w, 3.0, min_gap=0.45, pad=0.10)) == 1


def test_pad_clamped_to_clip_bounds():
    w = words(("a", 0.05, 0.5), ("b", 2.0, 2.95))
    segs = segments_from_words(w, 3.0, min_gap=0.45, pad=0.50)
    assert segs[0][0] == 0.0                   # ما بينزل تحت الصفر
    assert segs[-1][1] <= 3.0                  # ولا بيتعدى مدة الفيديو


def test_short_segment_dropped_and_its_words_vanish():
    """`min_seg` بتشيل المقطع بصمت — سلوك موثّق، مش مرغوب بالضرورة."""
    w = words(("aa", 0.0, 0.5), ("bb", 2.0, 2.05), ("cc", 4.0, 4.6))
    segs = segments_from_words(w, 6.0, min_gap=0.45, pad=0.10, min_seg=0.35)
    assert len(segs) == 2
    assert [x["word"] for x in remap_words(w, segs)] == ["aa", "cc"]


def test_overlapping_pads_merge_instead_of_duplicating():
    w = words(("a", 0.0, 0.5), ("b", 1.2, 1.8))
    segs = segments_from_words(w, 3.0, min_gap=0.45, pad=0.50)
    assert len(segs) == 1                      # ما بينتجوا مقطعين متداخلين


def test_all_segments_dropped_falls_back_to_whole_clip():
    w = words(("a", 1.0, 1.02))
    assert segments_from_words(w, 5.0, min_seg=0.35) == [(0.0, 5.0)]


def test_total_after_cut():
    assert total_after_cut([(0.0, 1.5), (3.0, 4.25)]) == pytest.approx(2.75)


# ------------------------------------------------------------------ remap

def test_single_full_segment_is_identity():
    w = words(("a", 0.5, 1.0), ("b", 1.2, 1.6))
    out = remap_words(w, [(0.0, 3.0)])
    assert [(x["word"], x["start"], x["end"]) for x in out] == [
        ("a", 0.5, 1.0), ("b", 1.2, 1.6)]


def test_times_shift_by_removed_duration():
    w = words(("a", 0.0, 0.5), ("b", 4.0, 4.5))
    out = remap_words(w, [(0.0, 1.0), (3.8, 5.0)])
    assert out[0]["start"] == pytest.approx(0.0)
    assert out[1]["start"] == pytest.approx(1.0 + 0.2)   # طول المقطع الأول + الإزاحة


def test_words_inside_removed_span_are_dropped():
    w = words(("keep", 0.0, 0.5), ("gone", 2.0, 2.5), ("keep2", 4.0, 4.5))
    out = remap_words(w, [(0.0, 0.6), (3.9, 4.6)])
    assert [x["word"] for x in out] == ["keep", "keep2"]


def test_weak_overlap_below_45_percent_is_ignored():
    w = words(("edge", 0.9, 1.9))               # ١٠٪ بس جوا المقطع
    assert remap_words(w, [(0.0, 1.0)]) == []


def test_strong_overlap_is_kept_and_clipped():
    w = words(("edge", 0.9, 1.4))               # ٢٠٪ برّا -> بينقبل وبينقص
    out = remap_words(w, [(0.0, 1.3)])
    assert len(out) == 1
    assert out[0]["end"] == pytest.approx(1.3)


def test_output_is_monotonic():
    w = words(("a", 0.0, 0.4), ("b", 1.0, 1.4), ("c", 5.0, 5.4))
    out = remap_words(w, [(0.0, 1.5), (4.9, 5.5)])
    starts = [x["start"] for x in out]
    assert starts == sorted(starts)
    for x in out:
        assert x["end"] > x["start"]


@pytest.mark.xfail(reason="عتبة الـ٤٥٪ بتنحسب لكل مقطع لحاله، فكلمة موزّعة "
                          "٤٣٪/٢٩٪ بتنرمى رغم إنها ٧٢٪ حاضرة إجمالًا",
                   strict=False)
def test_word_split_across_two_kept_segments_survives():
    w = words(("مرحبا", 0.9, 1.6))
    assert [x["word"] for x in remap_words(w, [(0.0, 1.2), (1.4, 2.0)])] == ["مرحبا"]


@pytest.mark.xfail(reason="منع التكرار بيقارن النص بس بدون تمييز حدود المقاطع، "
                          "فكلمتين حقيقيتين متطابقتين بتنصهروا",
                   strict=False)
def test_genuinely_repeated_word_is_not_merged():
    w = words(("لا", 1.00, 1.20), ("لا", 1.22, 1.42), ("صحيح", 1.5, 2.0))
    assert [x["word"] for x in remap_words(w, [(0.0, 3.0)])] == ["لا", "لا", "صحيح"]

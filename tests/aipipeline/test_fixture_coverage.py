"""الطقم الأخضر مش دليل تغطية لو الـfixture ما بتمرق بالطريق الخطر.

هالملف بيفحص **الـfixtures**، مش الكود. سببه حادثة حقيقية: بعد ٥٠
فحصًا خضرا، شيل قصّ التداخل من `quantize()` **مرق بلا ولا فشل** — لأن
`alignment` ما فيها كلمات متداخلة أصلًا، فالمسار ما كان مغطًّى.

كل فحص هون بيثبّت خاصية بالـfixture **بيعتمد عليها فحص خطر تاني**.
لو أحد عدّل الـfixture وكسر الخاصية، بيفشل هون بدل ما يفقد التغطية
بصمت.
"""
import pytest

from ai_pipeline.models.timeline import Timeline
from ai_pipeline.timeline.quantize import quantize


def test_alignment_starts_after_frame_zero(alignment):
    """`test_text_starts_after_video` بيعتمد عليها (F7)."""
    assert alignment.words[0].start > 1 / 30, "الكلام بيبلّش بالإطار 0 — تغطية F7 ضاعت"


def test_alignment_has_gaps_between_words(alignment):
    """بلا فراغات، ما في فرق بين `max(end)` و`end` الأخيرة."""
    gaps = [b.start - a.end for a, b in zip(alignment.words, alignment.words[1:])]
    assert all(g > 0 for g in gaps), "الـfixture ملتصقة — القصّ ما بينختبر"


def test_segments_cover_every_source_word(segments, tokens):
    """`check_coverage` بينختبر بالحالتين — التغطية الكاملة والناقصة."""
    shown = {i for s in segments.segments
             for i in range(s.word_start, s.word_end)}
    assert shown == set(range(len(tokens)))


def test_the_fixture_text_actually_carries_tashkeel(tokens):
    """فحوص السلامة بتشتغل على حذف حركة — بلا حركات ما بتعني شي."""
    import unicodedata
    marks = sum(1 for t in tokens for c in t
                if unicodedata.category(c) == "Mn")
    assert marks >= 15, f"الـfixture فيها {marks} حركة بس — فحص التشكيل بلا أسنان"


def test_assets_are_long_enough_but_not_absurdly(assets, output, segments,
                                                 alignment, audio_duration):
    """لازم تمرق بالحالة السليمة، وتفشل لما نقصّرها — الاتنين مغطّيان."""
    tl = quantize(output, segments, alignment, assets, audio_duration)
    for sp in tl.visual_spans:
        a = assets.by_segment(sp.segment_id)
        assert a.probe.duration * output.fps > sp.n_frames


@pytest.mark.parametrize("prop", ["visual_covers_all", "text_leaves_gaps"])
def test_timeline_shape_from_the_fixture(output, segments, alignment, assets,
                                         audio_duration, prop):
    tl: Timeline = quantize(output, segments, alignment, assets, audio_duration)
    if prop == "visual_covers_all":
        assert tl.visual_spans[0].f_start == 0
        assert tl.visual_spans[-1].f_end == tl.total_frames
    else:
        head = tl.text_spans[0].f_start - tl.visual_spans[0].f_start
        tail = tl.visual_spans[-1].f_end - tl.text_spans[-1].f_end
        assert head > 0 and tail > 0, (
            "الـfixture ما بتترك فجوة نصّية — الفرق بين نوعي الـspans "
            "مش مغطًّى")

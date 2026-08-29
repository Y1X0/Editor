"""المُكمِّم — الحدّ بين الثواني والإطارات."""
import pytest

from pipeline.errors import AssetError, TimelineError
from pipeline.models.alignment import Alignment, Word
from pipeline.models.assets import Asset, AssetsContract, Probe
from pipeline.models.project import Output
from pipeline.timeline.quantize import quantize


def test_covers_whole_strip(output, segments, alignment, assets, audio_duration):
    tl = quantize(output, segments, alignment, assets, audio_duration)
    assert tl.visual_spans[0].f_start == 0
    assert tl.visual_spans[-1].f_end == tl.total_frames
    assert sum(s.n_frames for s in tl.visual_spans) == tl.total_frames


def test_text_starts_after_video(output, segments, alignment, assets, audio_duration):
    """F7 — الكلام بيبلّش 0.82s، والفيديو من الإطار 0."""
    tl = quantize(output, segments, alignment, assets, audio_duration)
    assert tl.text_spans[0].f_start == round(0.82 * 30) == 25
    assert tl.visual_spans[0].f_start == 0
    assert tl.text_spans[0].f_start > tl.visual_spans[0].f_start


def test_frame_boundaries_are_exact(output, segments, alignment, assets, audio_duration):
    tl = quantize(output, segments, alignment, assets, audio_duration)
    for sp, seg in zip(tl.text_spans, segments.segments):
        t0, _ = alignment.span_time(seg.word_start, seg.word_end)
        assert sp.f_start == round(t0 * 30)


def test_audio_length_derives_from_frames(output, segments, alignment, assets,
                                          audio_duration):
    tl = quantize(output, segments, alignment, assets, audio_duration)
    assert tl.total_samples == tl.total_frames * 1600
    assert tl.total_samples % 1600 == 0


def test_segment_shorter_than_a_frame_fails(output, segments, assets):
    words = tuple(
        Word(i=i, text=f"w{i}", start=1.0 + i * 0.001, end=1.0 + i * 0.001 + 0.0005)
        for i in range(10)
    )
    with pytest.raises(TimelineError, match="أقصر من إطار|انطمس"):
        quantize(output, segments, Alignment(method="t", words=words), assets, 5.0)


def test_asset_too_short_fails(output, segments, alignment, assets, audio_duration,
                               tmp_path):
    short = tuple(
        a.model_copy(update={"probe": Probe(width=1920, height=1080, fps=25.0,
                                            duration=0.5)})
        for a in assets.assets
    )
    with pytest.raises(AssetError, match="بيعطي"):
        quantize(output, segments, alignment,
                 AssetsContract(assets=short), audio_duration)


def test_in_point_becomes_a_frame_index(output, segments, alignment, assets,
                                        audio_duration):
    shifted = tuple(a.model_copy(update={"in_point": 1.0}) for a in assets.assets)
    tl = quantize(output, segments, alignment,
                  AssetsContract(assets=shifted), audio_duration)
    assert set(tl.asset_in_frame.values()) == {30}


def test_zero_duration_audio_fails(output, segments, alignment, assets):
    with pytest.raises(TimelineError, match="غير صالحة"):
        quantize(output, segments, alignment, assets, 0.0)


def test_is_pure(output, segments, alignment, assets, audio_duration):
    """نفس المدخلات -> نفس المخرَج، بالضبط."""
    a = quantize(output, segments, alignment, assets, audio_duration)
    b = quantize(output, segments, alignment, assets, audio_duration)
    assert a == b


def test_overlapping_words_are_clipped(output, segments, alignment, assets,
                                       audio_duration):
    """Whisper بيرجّع تداخلًا جزئيًا، و`span_time` بتاخد `max(end)`.

    بلا قصّ، كابشنان بيتقاطعوا بنفس الإطار — و`Timeline` بترفض. القصّ
    قرار عرض معلَن؛ المحاذاة بتضل كما هي.
    """
    ws = list(alignment.words)
    # خلّي كلمة 3 (آخر المقطع الأول) تمتد لجوّا المقطع الثاني
    ws[3] = ws[3].model_copy(update={"end": ws[5].start + 0.30})
    over = alignment.model_copy(update={"words": tuple(ws)})

    t0, t1 = over.span_time(0, 4)
    assert round(t1 * 30) > round(over.span_time(4, 7)[0] * 30), "الـfixture ما بتتداخل"

    tl = quantize(output, segments, over, assets, audio_duration)
    assert tl.text_spans[0].f_end == tl.text_spans[1].f_start
    for a, b in zip(tl.text_spans, tl.text_spans[1:]):
        assert a.f_end <= b.f_start


def test_fully_swallowed_segment_fails(output, segments, alignment, assets,
                                       audio_duration):
    """مقطعان بيبلّشوا بنفس الإطار -> الأول بينطمس، وبيفشل.

    القصّ ما بيقدر يعطي مدى سالبًا (البدايات غير متناقصة)، بس بيقدر
    يعطي **مدى فاضيًا** لما المقطع التالي يبدأ بنفس إطار الحالي. صفر
    إطار كابشن مش خيارًا صامتًا.
    """
    ws = list(alignment.words)
    t = ws[4].start
    for i in (5, 6, 7):
        ws[i] = ws[i].model_copy(update={"start": t, "end": max(ws[i].end, t + 0.1)})
    over = alignment.model_copy(update={"words": tuple(ws)})
    assert round(over.span_time(4, 7)[0] * 30) == round(over.span_time(7, 10)[0] * 30)
    with pytest.raises(TimelineError, match="انطمس"):
        quantize(output, segments, over, assets, audio_duration)

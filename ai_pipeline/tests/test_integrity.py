"""§19 — سلامة النص الديني. أهم ملف اختبارات بالمشروع."""
import pytest

from pipeline.errors import AlignmentError, AssetError, ContractError, TextIntegrityError
from pipeline.models.segments import Segment, SegmentsContract
from pipeline.validation.semantic import (
    check_alignment_covers, check_alignment_matches_source, check_assets,
    check_coverage, check_text_integrity,
)


def test_faithful_echo_passes(segments, tokens):
    check_text_integrity(segments, tokens)


@pytest.mark.parametrize("mutate,name", [
    (lambda s: s.replace("وَمَن", "ومن"), "حذف تشكيل"),
    (lambda s: s.replace("يَتَوَكَّلْ", "يتوكّل"), "تشكيل ناقص"),
    (lambda s: s + " فقط", "كلمة زيادة"),
    (lambda s: s.rsplit(" ", 1)[0], "كلمة ناقصة"),
    (lambda s: s.replace("عَلَى", "على"), "استبدال"),
    (lambda s: s.replace("اللَّهِ", "الله"), "اسم الجلالة بلا تشكيل"),
])
def test_any_deviation_fails(segments, tokens, mutate, name):
    """ولا حرف. حذف حركة وحدة كافٍ ليفشل."""
    s0 = segments.segments[0]
    bad = SegmentsContract(segments=(
        s0.model_copy(update={"text_arabic": mutate(s0.text_arabic)}),
        *segments.segments[1:],
    ))
    with pytest.raises(TextIntegrityError, match="لا يطابق المصدر"):
        check_text_integrity(bad, tokens)


def test_error_shows_both_sides(segments, tokens):
    s0 = segments.segments[0]
    bad = SegmentsContract(segments=(
        s0.model_copy(update={"text_arabic": "نص مختلف تمامًا"}),
        *segments.segments[1:],
    ))
    with pytest.raises(TextIntegrityError) as e:
        check_text_integrity(bad, tokens)
    msg = str(e.value)
    assert "[TEXT_INTEGRITY_ERROR]" in msg
    assert "المصدر" in msg and "العقد" in msg


def test_dropped_word_is_caught(tokens):
    """الوكيل ممكن يتجاهل كلمات بدل ما يغيّرهن — كمان حذف صامت."""
    part = SegmentsContract(segments=(
        Segment(segment_id=1, word_start=0, word_end=4,
                text_arabic=" ".join(tokens[0:4]), visual_mood_prompt="m"),
    ))
    check_text_integrity(part, tokens)          # الصدى سليم
    with pytest.raises(TextIntegrityError, match="ما بتظهر"):
        check_coverage(part, tokens)            # بس ٦ كلمات ضاعت


def test_full_coverage_passes(segments, tokens):
    check_coverage(segments, tokens)


def test_span_beyond_source_fails(tokens):
    bad = SegmentsContract(segments=(
        Segment(segment_id=1, word_start=0, word_end=99,
                text_arabic="x", visual_mood_prompt="m"),
    ))
    with pytest.raises(ContractError, match="خارج نص"):
        check_text_integrity(bad, tokens)


def test_alignment_must_be_on_source(alignment, tokens):
    check_alignment_matches_source(alignment, tokens)
    short = alignment.model_copy(update={"words": alignment.words[:-1]})
    with pytest.raises(AlignmentError, match="لازم تكون على المصدر"):
        check_alignment_matches_source(short, tokens)


def test_alignment_word_mismatch_fails(alignment, tokens):
    """محاذاة على نسخ Whisper (بلا تشكيل) بتنرفض."""
    w0 = alignment.words[0]
    drifted = alignment.model_copy(update={
        "words": (w0.model_copy(update={"text": "ومن"}), *alignment.words[1:])})
    with pytest.raises(AlignmentError, match="المحاذاة"):
        check_alignment_matches_source(drifted, tokens)


def test_segments_within_alignment(segments, alignment):
    check_alignment_covers(segments, alignment)
    short = alignment.model_copy(update={"words": alignment.words[:5]})
    with pytest.raises(AlignmentError, match="خارج محاذاة"):
        check_alignment_covers(segments, short)


def test_missing_asset_file_fails(assets, segments, tmp_path):
    check_assets(assets, segments, tmp_path)
    assets.assets[0].file_path.unlink()
    with pytest.raises(AssetError, match="مش موجود"):
        check_assets(assets, segments, tmp_path)


def test_asset_for_unknown_segment_fails(assets, segments, tmp_path):
    from pipeline.models.assets import AssetsContract
    extra = assets.assets[0].model_copy(update={"segment_id": 9})
    with pytest.raises(AssetError, match="مش موجودة"):
        check_assets(AssetsContract(assets=(*assets.assets, extra)),
                     segments, tmp_path)

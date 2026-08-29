"""Phase 1 — العقود. كل حالة فشل بـ§9 لسا ممكنة إلها اختبار."""
import json

import pytest
from pydantic import ValidationError

from ai_pipeline.models.project import Output
from ai_pipeline.models.segments import SegmentsContract
from ai_pipeline.models.timeline import Span, Timeline
from ai_pipeline.models.typography import TypographyContract


def _seg(sid, a, b, text="نص"):
    return dict(segment_id=sid, word_start=a, word_end=b,
                text_arabic=text, visual_mood_prompt="mood")


def _load(segs):
    return SegmentsContract.model_validate_json(json.dumps({"segments": segs}))


# ── العقود بتنقرا من JSON بالوضع الصارم ──────────────────────────────
def test_loads_from_json():
    c = _load([_seg(1, 0, 3)])
    assert c.segments[0].segment_id == 1


def test_rejects_string_where_int_expected():
    """LLM بيرجّع "1" بدل 1 — والقبول الصامت بيخفي قرارًا مخترَعًا."""
    with pytest.raises(ValidationError):
        _load([{**_seg(1, 0, 3), "segment_id": "1"}])


def test_rejects_unknown_key():
    """مفتاح زيادة = قرار ما حدا طلبه. `extra=forbid`."""
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        _load([{**_seg(1, 0, 3), "start": 0.82}])


def test_contract_is_frozen():
    c = _load([_seg(1, 0, 3)])
    with pytest.raises(ValidationError):
        c.segments[0].segment_id = 2


# ── حالات §9 اللي لسا ممكنة ──────────────────────────────────────────
def test_duplicate_segment_id():
    with pytest.raises(ValidationError, match="مكرّرة"):
        _load([_seg(1, 0, 3), _seg(1, 3, 6)])


def test_out_of_order_ids():
    with pytest.raises(ValidationError, match="1..n"):
        _load([_seg(2, 0, 3), _seg(1, 3, 6)])


def test_overlapping_word_spans():
    with pytest.raises(ValidationError, match="تداخل"):
        _load([_seg(1, 0, 4), _seg(2, 3, 6)])


def test_empty_span():
    with pytest.raises(ValidationError, match="مدى فاضي"):
        _load([_seg(1, 3, 3)])


def test_negative_index():
    with pytest.raises(ValidationError):
        _load([_seg(1, -1, 3)])


# ── حالات §9 اللي صارت **مستحيلة بالبناء** ───────────────────────────
def test_segments_contract_has_no_time_fields():
    """`start`/`end`/`duration` مش بالعقد أصلًا.

    لهيك «start >= end» و«توقيت سالب» و«duration mismatch» ما بيقدروا
    يصيروا — الوكيل ما عنده مكان يكتبهن فيه.
    """
    banned = {"start", "end", "duration", "timestamp"}
    fields = set(SegmentsContract.model_json_schema()["$defs"]["Segment"]["properties"])
    assert not (fields & banned), f"حقل زمني رجع للعقد: {fields & banned}"


def test_typography_has_no_shaping_engine_or_paths():
    fields = set(TypographyContract.model_json_schema()["properties"])
    seg_fields = set(
        TypographyContract.model_json_schema()["$defs"]["TypographySegment"]["properties"]
    )
    assert "shaping_engine" not in fields | seg_fields
    assert "rendered_image_path" not in fields | seg_fields
    assert not ({"start", "end"} & seg_fields)


# ── Output ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("fps", [29, 23, 60])
def test_rejects_fps_with_fractional_samples(fps):
    if 48000 % fps == 0:
        pytest.skip("قسمة صحيحة")
    with pytest.raises(ValidationError, match="بينقسم|صحيحًا"):
        Output(fps=fps)


@pytest.mark.parametrize("fps", [24, 25, 30, 48, 50])
def test_accepts_fps_with_integer_samples(fps):
    assert Output(fps=fps).samples_per_frame * fps == 48000


def test_rejects_odd_dimensions():
    with pytest.raises(ValidationError, match="أزواجًا"):
        Output(width=1081)


# ── Timeline ─────────────────────────────────────────────────────────
def _tl(**kw):
    S = lambda i, a, b: Span(segment_id=i, f_start=a, f_end=b)
    base = dict(fps=30, sample_rate=48000, total_frames=270,
                visual_spans=(S(1, 0, 102), S(2, 102, 270)),
                text_spans=(S(1, 25, 102), S(2, 102, 246)))
    base.update(kw)
    return Timeline(**base)


def test_timeline_total_samples():
    assert _tl().total_samples == 270 * 1600


@pytest.mark.parametrize("kw,msg", [
    (dict(visual_spans=(Span(segment_id=1, f_start=1, f_end=270),)), "الإطار 0"),
    (dict(visual_spans=(Span(segment_id=1, f_start=0, f_end=100),
                        Span(segment_id=2, f_start=102, f_end=270))), "فجوة"),
    (dict(visual_spans=(Span(segment_id=1, f_start=0, f_end=269),)), "تنتهي عند"),
    (dict(text_spans=(Span(segment_id=1, f_start=25, f_end=110),
                      Span(segment_id=2, f_start=102, f_end=246))), "تداخل"),
    (dict(text_spans=(Span(segment_id=1, f_start=25, f_end=280),)), "بيتجاوز"),
])
def test_timeline_guards(kw, msg):
    with pytest.raises(ValidationError, match=msg):
        _tl(**kw)

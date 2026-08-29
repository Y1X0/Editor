"""ما **يقدر** الوكيل يقوله — والأهم: ما **ما بيقدر**.

كل فحص سالب هون بيثبت إن الحقل الخطر **ما إله مكان بالـschema**، مش إنه
انرفض بمدقّق لاحق. الفرق عملي: الرفض المتأخّر بيعتمد على مدقّق حدا ممكن
ينساه أو يعطّله؛ غياب الحقل بيعتمد على الـschema نفسه.
"""
import json

import pytest
from pydantic import ValidationError

from ai_pipeline.agents.schemas import (
    MAX_KEYWORDS, PROPOSALS, SIZE_STEP_RANGE,
    AssetIntent, SegmentsProposal, TypographyProposal,
)

SEG = {"segment_id": 1, "word_start": 0, "word_end": 5,
       "visual_mood_prompt": "dark moody rain on a window"}
INT = {"segment_id": 1, "query": "slow motion rain",
       "shot_type": "wide", "palette": "charcoal"}
TYP = {"segment_id": 1}


def _seg(*items):
    return SegmentsProposal.model_validate_json(json.dumps({"segments": list(items)}))


def _int(*items):
    return AssetIntent.model_validate_json(json.dumps({"intents": list(items)}))


def _typ(*items):
    return TypographyProposal.model_validate_json(json.dumps({"segments": list(items)}))


# ── الحالة السليمة ───────────────────────────────────────────────────
def test_a_valid_segments_proposal_loads():
    p = _seg(SEG)
    assert p.segments[0].word_start == 0 and p.segments[0].word_end == 5


def test_a_valid_asset_intent_loads():
    assert _int(INT).intents[0].motion == "none"


def test_a_valid_typography_proposal_loads():
    s = _typ(TYP).segments[0]
    assert (s.animation, s.font_role, s.size_step) == ("fade_in_scale", "body", 0)


# ── ١· حقل ناقص ──────────────────────────────────────────────────────
@pytest.mark.parametrize("drop", ["segment_id", "word_start", "word_end",
                                  "visual_mood_prompt"])
def test_missing_field_fails(drop):
    with pytest.raises(ValidationError, match="missing|Field required"):
        _seg({k: v for k, v in SEG.items() if k != drop})


@pytest.mark.parametrize("drop", ["segment_id", "query", "shot_type", "palette"])
def test_missing_intent_field_fails(drop):
    with pytest.raises(ValidationError):
        _int({k: v for k, v in INT.items() if k != drop})


# ── ٢· حقل زائد — `extra="forbid"` ───────────────────────────────────
@pytest.mark.parametrize("extra", ["note", "confidence", "reasoning", "_meta"])
def test_any_extra_field_fails(extra):
    """الـLLM بيخترع مفاتيح؛ والتجاهل الصامت بيمرّر قرارًا ما حدا طلبه."""
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        _seg({**SEG, extra: "whatever"})


@pytest.mark.parametrize("model", PROPOSALS, ids=lambda m: m.__name__)
def test_every_proposal_forbids_extras(model):
    """فحص على الإعداد نفسه، مش على السلوك بس.

    السلوكي بيمسك حالة؛ وهاد بيمسك أي Proposal جديد بينكتب بإعداد أرخى.
    """
    assert model.model_config["extra"] == "forbid", model.__name__
    assert model.model_config["frozen"] is True, model.__name__
    assert model.model_config["strict"] is True, model.__name__


# ── ٣· enum غير صالح ─────────────────────────────────────────────────
@pytest.mark.parametrize("field,bad", [
    ("shot_type", "cinematic"), ("palette", "neon"), ("motion", "spin"),
])
def test_invalid_enum_in_asset_intent_fails(field, bad):
    with pytest.raises(ValidationError, match="literal_error|Input should be"):
        _int({**INT, field: bad})


@pytest.mark.parametrize("field,bad", [
    ("animation", "explode"), ("font_role", "comic"), ("color_role", "neon"),
])
def test_invalid_enum_in_typography_fails(field, bad):
    with pytest.raises(ValidationError, match="literal_error|Input should be"):
        _typ({**TYP, field: bad})


# ── ٤· حقن توقيت ─────────────────────────────────────────────────────
@pytest.mark.parametrize("key,value", [
    ("start", 0.82), ("end", 3.41), ("duration", 2.59),
    ("timestamp", 1.0), ("start_time", 0.0), ("t0", 0.0),
])
def test_timestamp_injection_is_rejected_by_the_schema(key, value):
    """الوكيل ما عنده حقل زمني — فالمحاولة بتفشل عند القراءة."""
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        _seg({**SEG, key: value})


def test_no_time_field_exists_on_any_proposal():
    """إثبات على شكل الـschema: الحقول الزمنية **مش موجودة أصلًا**."""
    banned = {"start", "end", "duration", "timestamp", "start_time", "end_time"}
    for model in PROPOSALS:
        schema = model.model_json_schema()
        for name, spec in (schema.get("$defs") or {}).items():
            found = set(spec.get("properties", {})) & banned
            assert not found, f"{model.__name__}.{name} فيه {found}"


def test_no_text_field_exists_on_any_proposal():
    """§19 — الوكيل ما بيقدر يبعث نصًّا عربيًا، فما بيقدر يغيّره."""
    banned = {"text", "text_arabic", "content", "script"}
    for model in PROPOSALS:
        for name, spec in (model.model_json_schema().get("$defs") or {}).items():
            found = set(spec.get("properties", {})) & banned
            assert not found, f"{model.__name__}.{name} فيه {found}"


# ── ٥· معرّف أصل مهلوَس ──────────────────────────────────────────────
@pytest.mark.parametrize("key,value", [
    ("provider_ref", "px_8562341"), ("asset_id", "px_8562341"),
    ("provider", "pexels"), ("file_path", "input/assets/segment_1.mp4"),
    ("sha256", "a" * 64), ("license", "pexels-free"), ("url", "https://x/y.mp4"),
])
def test_asset_identity_cannot_be_proposed(key, value):
    """الهلوسة ما إلها مكان: ولا حقل هوية أصل بالـschema."""
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        _int({**INT, key: value})


# ── ٦· مسار خط / hex / محرّك تشكيل ───────────────────────────────────
@pytest.mark.parametrize("key,value", [
    ("font_path", "/etc/passwd"), ("font", "fonts/Whatever.ttf"),
    ("text_color", "#F3E5AB"), ("stroke_color", "#000000"),
    ("shaping_engine", "python-bidi + arabic-reshaper"),
    ("font_size", 72), ("position", "center"),
])
def test_typography_cannot_invent_values(key, value):
    """أدوار فقط. و`shaping_engine` بالذات: في shaper واحد صحيح."""
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        _typ({**TYP, key: value})


# ── الحدود العددية ───────────────────────────────────────────────────
def test_the_locked_limits_are_what_the_spec_says():
    """الحدود **مثبَّتة بالرقم**، مش مقروءة من الوحدة المفحوصة.

    فحص بيستورد الثابت اللي المفروض يحرسه ما بيقدر يحرسه: لو صار
    `MAX_KEYWORDS = 50` بيرتفع سقف الفحص معه ويمرق. مقيسة — الطفرة
    5 -> 50 مرقت بالصيغة الأولى.
    """
    assert MAX_KEYWORDS == 5
    assert SIZE_STEP_RANGE == 2


def test_keyword_lists_are_capped_at_five():
    _int({**INT, "must_include": ["a"] * 5})
    for key in ("must_include", "must_avoid"):
        with pytest.raises(ValidationError, match="too_long|at most"):
            _int({**INT, key: ["a"] * 6})


@pytest.mark.parametrize("step", [-2, -1, 0, 1, 2])
def test_size_step_inside_the_range(step):
    assert _typ({**TYP, "size_step": step}).segments[0].size_step == step


@pytest.mark.parametrize("step", [-3, 3, 99])
def test_size_step_outside_the_range_fails(step):
    with pytest.raises(ValidationError, match="less_than_equal|greater_than_equal"):
        _typ({**TYP, "size_step": step})


def test_empty_collections_fail():
    for model, key in ((SegmentsProposal, "segments"), (AssetIntent, "intents"),
                       (TypographyProposal, "segments")):
        with pytest.raises(ValidationError, match="too_short|at least"):
            model.model_validate_json(json.dumps({key: []}))


def test_string_where_int_expected_is_rejected():
    """الوضع الصارم: الـLLM بيرجّع "1" مكان 1، والقبول الصامت بيمرّره."""
    with pytest.raises(ValidationError):
        _seg({**SEG, "segment_id": "1"})


def test_proposals_are_frozen():
    p = _seg(SEG)
    with pytest.raises(ValidationError):
        p.segments[0].word_start = 3

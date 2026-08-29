"""§2 عقد مفقود · §3 JSON مشوَّه — وكل ما بينهن."""
import json

import pytest

from ai_pipeline.errors import ContractError
from ai_pipeline.io import contracts as IO
from ai_pipeline.models.segments import SegmentsContract

GOOD = {"segments": [{"segment_id": 1, "word_start": 0, "word_end": 3,
                      "text_arabic": "نص", "visual_mood_prompt": "mood"}]}


def _write(tmp_path, text, name="segments.json"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_a_good_contract(tmp_path):
    c = IO.load(_write(tmp_path, json.dumps(GOOD)), SegmentsContract)
    assert c.segments[0].segment_id == 1


# ── §2 ───────────────────────────────────────────────────────────────
def test_missing_contract_names_the_path_and_the_model(tmp_path):
    with pytest.raises(ContractError) as e:
        IO.load(tmp_path / "segments.json", SegmentsContract)
    assert "عقد مفقود" in str(e.value)
    assert "segments.json" in str(e.value)
    assert "SegmentsContract" in str(e.value)


def test_empty_file_is_not_an_empty_contract(tmp_path):
    with pytest.raises(ContractError, match="عقد فاضي"):
        IO.load(_write(tmp_path, "   \n"), SegmentsContract)


# ── §3 ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,name", [
    ('{"segments": [', "قوس مفتوح"),
    ("not json at all", "نص عادي"),
    ('{"segments": [],}', "فاصلة زايدة"),
    ("﻿" + json.dumps(GOOD), "BOM"),
])
def test_malformed_json_fails_loudly(tmp_path, text, name):
    with pytest.raises(ContractError) as e:
        IO.load(_write(tmp_path, text), SegmentsContract)
    assert "segments.json" in str(e.value), name
    # الرسالة لازم تقول **JSON غير صالح**، مش «خطأ تحقّق». pydantic
    # بيرمي `ValidationError` للحالتين، والخلط بينهن بيبعت القارئ
    # يدوّر على حقل غلط بملف مش JSON أصلًا.
    assert "JSON غير صالح" in str(e.value), f"{name}: رسالة مضلّلة"


def test_schema_violation_points_at_the_field(tmp_path):
    bad = {"segments": [{**GOOD["segments"][0], "word_end": 0}]}
    with pytest.raises(ContractError) as e:
        IO.load(_write(tmp_path, json.dumps(bad)), SegmentsContract)
    assert "خطأ تحقّق" in str(e.value) and "segments" in str(e.value)


def test_a_list_in_python_is_not_a_shortcut(tmp_path):
    """الوضع الصارم بيرفض list مكان tuple بالبايثون، وبيقبل مصفوفة JSON.

    اللي بيحمي: `"1"` مكان `1` بينرفض بالحالتين — الـLLM بيرجّع نصوصًا
    مكان أرقام، والقبول الصامت بيمرّر قرارًا مخترَعًا للرندر.
    """
    with pytest.raises(ContractError):
        IO.load(_write(tmp_path, json.dumps(
            {"segments": [{**GOOD["segments"][0], "segment_id": "1"}]})),
            SegmentsContract)


def test_round_trip_loses_nothing(tmp_path):
    c = IO.load(_write(tmp_path, json.dumps(GOOD)), SegmentsContract)
    assert IO.round_trip(c) == c
    p = IO.save(tmp_path / "out" / "segments.json", c)
    assert IO.load(p, SegmentsContract) == c

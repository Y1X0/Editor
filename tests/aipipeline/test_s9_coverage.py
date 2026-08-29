"""خريطة §9: كل حالة فشل مطلوبة -> المدقّق اللي بيمسكها -> الفحص.

**ليش الخريطة فحصًا مش وثيقة:** الوثيقة بتتقادم بصمت. هون، لو انحذف
فحص أو انعاد تسميته، الخريطة بتفشل وبتقول أي حالة §9 فقدت تغطيتها.

عمود `kind`:
  `guard`       مدقّق صريح بيرمي
  `structural`  الـschema بترفضها
  `impossible`  ما بتقدر تصير بالبناء — والفحص بيثبت **غياب** الحقل
"""
import ast
import pathlib

import pytest

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[1]

# (حالة §9، النوع، الوحدة اللي بتمسكها، ملف الفحص، اسم الفحص)
S9 = [
    ("missing audio",            "guard",      "validation/inputs.py",   "test_inputs.py",          "test_missing_audio_fails"),
    ("missing audio stream",     "guard",      "validation/inputs.py",   "test_inputs.py",          "test_a_file_with_no_audio_stream_fails"),
    ("missing contract",         "guard",      "io/contracts.py",        "test_contract_io.py",     "test_missing_contract_names_the_path_and_the_model"),
    ("malformed JSON",           "guard",      "io/contracts.py",        "test_contract_io.py",     "test_malformed_json_fails_loudly"),
    ("missing segment",          "guard",      "validation/semantic.py", "test_integrity.py",       "test_dropped_word_is_caught"),
    ("duplicate segment ID",     "structural", "models/segments.py",     "test_contracts.py",       "test_duplicate_segment_id"),
    ("wrong segment ID order",   "structural", "models/segments.py",     "test_contracts.py",       "test_out_of_order_ids"),
    ("overlapping segments",     "structural", "models/segments.py",     "test_contracts.py",       "test_overlapping_word_spans"),
    ("start >= end",             "impossible", "models/segments.py",     "test_contracts.py",       "test_segments_contract_has_no_time_fields"),
    ("negative timestamp",       "impossible", "models/segments.py",     "test_contracts.py",       "test_segments_contract_has_no_time_fields"),
    ("duration mismatch",        "impossible", "models/segments.py",     "test_contracts.py",       "test_segments_contract_has_no_time_fields"),
    ("wrong project_id",         "impossible", "validation/semantic.py", "test_integrity.py",       "test_theme_mismatch_fails"),
    ("missing asset",            "guard",      "validation/semantic.py", "test_integrity.py",       "test_missing_asset_file_fails"),
    ("asset duration too short", "guard",      "timeline/quantize.py",   "test_quantize.py",        "test_asset_too_short_fails"),
    ("missing typography",       "guard",      "validation/semantic.py", "test_integrity.py",       "test_missing_typography_for_a_segment_fails"),
    ("invalid font",             "guard",      "validation/font.py",     "test_font.py",            "test_tajawal_cannot_render_quranic_marks"),
    ("missing typography image", "guard",      "qa/output.py",           "test_output_qa.py",       "test_dropped_frames_are_caught"),
    ("invalid output resolution","guard",      "qa/output.py",           "test_output_qa.py",       "test_wrong_resolution_is_caught"),
    ("invalid output FPS",       "structural", "models/project.py",      "test_contracts.py",       "test_rejects_fps_with_fractional_samples"),
    ("ffmpeg failure",           "guard",      "qa/output.py",           "test_output_qa.py",       "test_truncated_output_is_caught"),
]


def _defs(path):
    return {n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


@pytest.mark.parametrize("case,kind,module,tfile,tname",
                         S9, ids=[c[0].replace(" ", "_") for c in S9])
def test_every_s9_case_has_a_live_test(case, kind, module, tfile, tname):
    mod = ROOT / "ai_pipeline" / module
    assert mod.is_file(), f"«{case}»: الوحدة {module} مش موجودة"
    tf = HERE / tfile
    assert tf.is_file(), f"«{case}»: ملف الفحص {tfile} مش موجود"
    assert tname in _defs(tf), (
        f"«{case}» فقدت تغطيتها: ما لقيت `{tname}` بـ{tfile}. "
        f"لو الفحص انعاد تسميته، حدّث الخريطة **بقصد**.")


def test_the_map_covers_the_whole_of_s9():
    assert len(S9) == 20, "قائمة §9 فيها ٢٠ حالة — الخريطة لازم تغطّيهن كلهن"
    assert len({c[0] for c in S9}) == 20, "حالة مكرّرة بالخريطة"


def test_impossible_cases_really_are_impossible():
    """التصنيف `impossible` ادعاء — وهاد بيفحصه.

    الحقول الزمنية مش موجودة بعقد المقاطع، فحالات «start >= end» و
    «توقيت سالب» و«duration mismatch» ما إلها مكان تصير فيه.
    """
    from ai_pipeline.models.segments import SegmentsContract
    props = set(SegmentsContract.model_json_schema()["$defs"]["Segment"]["properties"])
    assert not (props & {"start", "end", "duration", "timestamp"})

"""المزوّدان المحليان — ولا شبكة، ولا مفتاح، ولا نموذج.

الغاية إن **سلوك الوكيل كله ينفحص قبل أول request حقيقي**. فالحالة
الغريبة اللي بتكسر المسار بتصير fixture ثابت، بدل حالة بتظهر مرة كل
ألف نداء وبتضيع منها اللقطة.

والفحوص هون بتثبت شغلتين عن المزوّدين نفسهن، مش عن الوكيل:
غياب الاستجابة **بيرمي** (المزوّد ما بيخترع)، والمخرَج المسجَّل
بيوصل **حرفيًا** (المزوّد ما بيصلّح).
"""
import ast
import json
import pathlib

import pytest

from ai_pipeline.agents.providers import scripted as SC
from ai_pipeline.agents.providers.base import Block, LLMRequest, LLMResponse, PromptRef
from ai_pipeline.agents.providers.recorded import RecordedClient, RecordedResponse
from ai_pipeline.agents.providers.scripted import ScriptedFailureClient
from ai_pipeline.agents.schemas import SegmentsProposal, TypographyProposal
from ai_pipeline.errors import ProviderError

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = pathlib.Path(__file__).parent / "fixtures" / "llm"


def req(agent="script", version="v1", schema=SegmentsProposal):
    return LLMRequest(
        prompt=PromptRef(agent, version, "a" * 64), system="sys",
        user_blocks=(Block("source", "نص"),), schema=schema,
        max_tokens=4096, effort="high", timeout_s=60.0)


# ══ RecordedClient ══════════════════════════════════════════════════
def test_a_recorded_case_comes_back_verbatim():
    r = RecordedClient(FIX, "ok_three_segments").complete(req())
    assert r.stop_reason == "end_turn"
    assert len(json.loads(r.text)["segments"]) == 3
    assert r.usage["cache_read_input_tokens"] == 640


def test_the_client_does_not_parse():
    """`parsed` بتضل None بقصد: القراءة والتحقّق شغل الـharness.

    مزوّد بيقرا بدل الـharness بيخلق مسارين — واحد بالاختبارات وواحد
    بالإنتاج — والفرق بينهن بيصير غير مفحوص.
    """
    assert RecordedClient(FIX, "ok_three_segments").complete(req()).parsed is None


def test_broken_output_is_returned_not_repaired():
    """المزوّد ناقل، مش مصلِّح."""
    r = RecordedClient(FIX, "bad_malformed").complete(req())
    with pytest.raises(json.JSONDecodeError):
        json.loads(r.text)


def test_the_same_case_is_byte_identical_across_calls():
    a = RecordedClient(FIX, "ok_three_segments").complete(req())
    b = RecordedClient(FIX, "ok_three_segments").complete(req())
    assert (a.text, a.stop_reason, a.usage) == (b.text, b.stop_reason, b.usage)


def test_a_missing_fixture_raises():
    """المزوّد اللي بيرجّع افتراضيًا بيخلّي الفحص يمرق وهو ما قاس شي."""
    with pytest.raises(ProviderError, match="fixture مفقود"):
        RecordedClient(FIX, "no_such_case").complete(req())


def test_a_missing_agent_key_raises():
    with pytest.raises(ProviderError, match="fixture مفقود"):
        RecordedClient(FIX, "ok_three_segments").complete(req(agent="nope"))


def test_the_key_includes_the_prompt_version():
    """`v2` مش `v1` — تثبيت الإصدار جزء من هوية الاستجابة."""
    with pytest.raises(ProviderError, match="script_v2"):
        RecordedClient(FIX, "ok_three_segments").complete(req(version="v2"))


def test_a_per_agent_mapping_selects_the_right_case():
    c = RecordedClient(FIX, {"script_v1": "ok_single_segment",
                             "typography_v1": "ok_two_segments"})
    assert len(json.loads(c.complete(req()).text)["segments"]) == 1
    t = c.complete(req("typography", "v1", TypographyProposal))
    assert len(json.loads(t.text)["segments"]) == 2


def test_an_unmapped_agent_raises():
    c = RecordedClient(FIX, {"script_v1": "ok_single_segment"})
    with pytest.raises(ProviderError, match="ما في حالة مسجَّلة"):
        c.complete(req("typography", "v1", TypographyProposal))


# ── التسلسل: لازم لفحص «الإصلاح محاولة واحدة» ───────────────────────
def test_a_sequence_advances_per_call():
    c = RecordedClient(FIX, ["bad_duplicate_ids", "ok_three_segments"])
    assert len(json.loads(c.complete(req()).text)["segments"]) == 2   # المكسور
    assert len(json.loads(c.complete(req()).text)["segments"]) == 3   # المصلَّح


def test_an_exhausted_sequence_raises():
    c = RecordedClient(FIX, ["ok_single_segment"])
    c.complete(req())
    with pytest.raises(ProviderError, match="نفد تسلسل"):
        c.complete(req())


def test_sequences_are_tracked_per_agent():
    c = RecordedClient(FIX, {"script_v1": ["ok_single_segment", "ok_three_segments"],
                             "typography_v1": ["ok_two_segments"]})
    assert len(json.loads(c.complete(req()).text)["segments"]) == 1
    c.complete(req("typography", "v1", TypographyProposal))
    assert len(json.loads(c.complete(req()).text)["segments"]) == 3


def test_calls_are_recorded_for_inspection():
    c = RecordedClient(FIX, ["ok_single_segment", "ok_three_segments"])
    c.complete(req()); c.complete(req())
    assert len(c.calls) == 2
    assert c.calls[0].prompt.version == "v1" and c.calls[0].effort == "high"


# ── ظرف الـfixture صارم ─────────────────────────────────────────────
def test_a_fixture_with_an_unknown_key_fails(tmp_path):
    d = tmp_path / "script_v1"; d.mkdir(parents=True)
    (d / "x.json").write_text(json.dumps({"text": "{}", "stop_resaon": "end_turn"}))
    with pytest.raises(ProviderError, match="ظرف fixture غير صالح"):
        RecordedClient(tmp_path, "x").complete(req())


def test_a_fixture_that_is_not_json_fails(tmp_path):
    d = tmp_path / "script_v1"; d.mkdir(parents=True)
    (d / "x.json").write_text("not json")
    with pytest.raises(ProviderError, match="JSON غير صالح|ظرف fixture"):
        RecordedClient(tmp_path, "x").complete(req())


def test_a_fixture_without_text_fails(tmp_path):
    d = tmp_path / "script_v1"; d.mkdir(parents=True)
    (d / "x.json").write_text(json.dumps({"stop_reason": "end_turn"}))
    with pytest.raises(ProviderError, match="ظرف fixture غير صالح"):
        RecordedClient(tmp_path, "x").complete(req())


# ── الـfixtures نفسها: كل واحدة بتحمل اللي اسمها بيوعد فيه ──────────
@pytest.mark.parametrize("path", sorted(FIX.rglob("*.json")),
                         ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_every_fixture_is_a_valid_envelope(path):
    RecordedResponse.model_validate_json(path.read_bytes())


@pytest.mark.parametrize("case,schema", [
    ("script_v1/ok_three_segments", SegmentsProposal),
    ("script_v1/ok_single_segment", SegmentsProposal),
    ("typography_v1/ok_two_segments", TypographyProposal),
])
def test_ok_fixtures_really_parse_as_their_schema(case, schema):
    """«ok» ادعاء — وهاد بيفحصه."""
    text = json.loads((FIX / f"{case}.json").read_text(encoding="utf-8"))["text"]
    schema.model_validate_json(text)


@pytest.mark.parametrize("case", [
    "script_v1/bad_extra_start_field", "script_v1/bad_duplicate_ids",
    "script_v1/bad_malformed", "script_v1/bad_prose_wrapper",
    "script_v1/bad_text_injection", "script_v1/bad_coverage_gap",
    "visual_v1/bad_hallucinated_asset_id", "visual_v1/bad_enum_value",
    "typography_v1/bad_font_path", "typography_v1/bad_enum_value",
    "typography_v1/bad_size_out_of_range",
])
def test_bad_fixtures_are_named_bad(case):
    """اسم الملف عقد كمان: كل `bad_*` لازم تكون فعلًا مكسورة.

    و`bad_duplicate_ids` و`bad_coverage_gap` بيمرقوا الـschema
    بقصد — كسرهن دلالي، وبيمسكه Phase 1/2 بعد التوسعة. فالفحص
    بيميّز الحالتين بدل ما يفترض إن كل «سيّئ» بيفشل بنفس الطبقة.
    """
    from pydantic import ValidationError
    text = json.loads((FIX / f"{case}.json").read_text(encoding="utf-8"))["text"]
    schema = {"script": SegmentsProposal, "typography": TypographyProposal}.get(
        case.split("_v1")[0].split("/")[0])
    if schema is None:
        from ai_pipeline.agents.schemas import AssetIntent as schema  # noqa: N813
    semantic_only = {"script_v1/bad_duplicate_ids", "script_v1/bad_coverage_gap"}
    try:
        schema.model_validate_json(text)
    except (ValidationError, ValueError):
        return
    assert case in semantic_only, f"{case}: مرقت الـschema وهي مش دلالية"


# ══ ScriptedFailureClient ═══════════════════════════════════════════
def test_a_provider_error_is_raised():
    c = ScriptedFailureClient([ProviderError("503 من الخدمة")])
    with pytest.raises(ProviderError, match="503"):
        c.complete(req())


def test_a_timeout_is_raised():
    c = ScriptedFailureClient([TimeoutError("مهلة")])
    with pytest.raises(TimeoutError):
        c.complete(req())


def test_a_refusal_returns_without_raising():
    """أخطر من الاستثناء: HTTP 200 بجسم فاضي.

    فقراءة `content` قبل فحص `stop_reason` بتخلّي الرفض يمرق كـ«جواب».
    """
    r = ScriptedFailureClient([SC.refusal("cyber")]).complete(req())
    assert r.stop_reason == "refusal" and r.text == ""
    assert r.stop_details["category"] == "cyber"


def test_a_truncated_response_looks_valid_until_you_read_it():
    r = ScriptedFailureClient([SC.truncated()]).complete(req())
    assert r.stop_reason == "max_tokens"
    assert r.text.startswith('{"segments"')          # بداية سليمة
    with pytest.raises(json.JSONDecodeError):
        json.loads(r.text)                            # وما بتكمل


def test_an_empty_response_returns_without_raising():
    r = ScriptedFailureClient([SC.empty()]).complete(req())
    assert r.text == "" and r.stop_reason == "end_turn"


def test_a_script_runs_in_order():
    c = ScriptedFailureClient([ProviderError("أولى"), SC.ok('{"segments": []}')])
    with pytest.raises(ProviderError, match="أولى"):
        c.complete(req())
    assert c.complete(req()).stop_reason == "end_turn"


def test_repeated_failure_is_expressible():
    """نفاد المحاولات: فشل، ثم فشل."""
    c = ScriptedFailureClient([ProviderError("1"), ProviderError("2")])
    for _ in range(2):
        with pytest.raises(ProviderError):
            c.complete(req())


def test_an_exhausted_script_raises():
    c = ScriptedFailureClient([SC.empty()])
    c.complete(req())
    with pytest.raises(ProviderError, match="نفد السيناريو"):
        c.complete(req())


def test_an_empty_script_is_rejected():
    with pytest.raises(ValueError, match="سيناريو فاضي"):
        ScriptedFailureClient([])


def test_scripted_calls_are_recorded():
    c = ScriptedFailureClient([SC.empty()])
    c.complete(req())
    assert len(c.calls) == 1 and c.calls[0].prompt.agent == "script"


# ══ حدود ═══════════════════════════════════════════════════════════
def test_both_clients_satisfy_the_protocol():
    from ai_pipeline.agents.providers.base import LLMClient
    for c in (RecordedClient(FIX, "ok_single_segment"),
              ScriptedFailureClient([SC.empty()])):
        assert isinstance(c.complete(req()), LLMResponse)
        assert hasattr(LLMClient, "complete")


@pytest.mark.parametrize("mod", ["recorded.py", "scripted.py"])
def test_the_local_providers_touch_no_network(mod):
    src = (ROOT / "ai_pipeline/agents/providers" / mod).read_text(encoding="utf-8")
    banned = {"anthropic", "requests", "httpx", "urllib", "socket", "http"}
    for node in ast.walk(ast.parse(src)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for n in names:
            assert n.split(".")[0] not in banned, f"{mod}: {n}"


def test_the_local_providers_are_still_the_test_path():
    """المزوّد الحقيقي انضاف بCommit 6، والمحليّان ضلّوا مصدر الاختبارات.

    الحارس هون على **العزل**: ولا اختبار بهالملف بيلمس
    `anthropic_client`، فالمسار المفحوص بيضل بلا شبكة.
    """
    have = {p.name for p in (ROOT / "ai_pipeline/agents/providers").glob("*.py")}
    assert have >= {"recorded.py", "scripted.py"}
    # الفحص على **الاستيرادات**، مش على نصّ الملف: البحث النصّي بيلاقي
    # الاسم بجملة التأكيد نفسها. حارس بيقرا حاله ما بيحرس شي.
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods = [node.module]
        for m in mods:
            assert "anthropic" not in m, f"هالطقم استورد {m} — العزل انكسر"

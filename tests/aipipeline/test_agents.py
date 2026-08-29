"""ربط الوكلاء الثلاثة بالـharness.

الحارس الأهم هون **بالغياب**: ولا وكيل بينادي المزوّد مباشرةً، ولا
بيقرا استجابة، ولا بيبني `PromptRef` بنفسه. الوكيل بيبني طلبًا
وبيسلّمه — وكل شي تاني ملك الـharness والسجلّ.
"""
import ast
import json
import pathlib

import pytest

from ai_pipeline.agents import script, typography, visual
from ai_pipeline.agents.expand import ThemeView
from ai_pipeline.agents.prompts import prompt_ref
from ai_pipeline.agents.providers import scripted as SC
from ai_pipeline.agents.providers.recorded import RecordedClient
from ai_pipeline.agents.providers.scripted import ScriptedFailureClient
from ai_pipeline.agents.runner import AgentHarness
from ai_pipeline.agents.schemas import (
    AssetIntent, SegmentsProposal, TypographyProposal,
)
from ai_pipeline.errors import AgentError
from ai_pipeline.models.segments import SegmentsContract
from ai_pipeline.models.typography import TypographyContract
from ai_pipeline.source import tokenize

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = pathlib.Path(__file__).parent / "fixtures" / "llm"
AGENTS = (script, visual, typography)
SRC = "وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ إِنَّ اللَّهَ بَالِغُ أَمْرِهِ"
TOKENS = tokenize(SRC)


@pytest.fixture
def theme():
    return ThemeView(theme_id="dark_gold_v1", font_role="body",
                     base_font_size=64, size_step_px=6, max_lines=2,
                     color_hex={"primary": "#F3E5AB", "muted": "#9A9384",
                                "accent": "#D8A657"})


@pytest.fixture
def segments():
    h = AgentHarness(RecordedClient(FIX, "ok_three_segments"))
    return script.run(RecordedClient(FIX, "ok_three_segments"), SRC, TOKENS,
                      harness=h)


def rec(*cases):
    return RecordedClient(FIX, list(cases))


# ══ الحارس بالغياب ══════════════════════════════════════════════════
@pytest.mark.parametrize("mod", AGENTS, ids=lambda m: m.AGENT)
def test_an_agent_never_calls_the_provider_directly(mod):
    """نداء مباشر بيتخطّى فحص `stop_reason` وسياسة الإصلاح والسجلّ."""
    src = (ROOT / "ai_pipeline/agents" / f"{mod.AGENT}.py").read_text("utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Attribute):
            assert node.attr != "complete", f"{mod.AGENT}: نداء مباشر للمزوّد"


@pytest.mark.parametrize("mod", AGENTS, ids=lambda m: m.AGENT)
def test_an_agent_never_builds_its_own_prompt_ref(mod):
    """البصمة بتيجي من السجلّ. وكيل بيبنيها بيقدر يخترع أي قيمة."""
    src = (ROOT / "ai_pipeline/agents" / f"{mod.AGENT}.py").read_text("utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "PromptRef", f"{mod.AGENT}: بنى PromptRef"
    assert "sha256=" not in src


@pytest.mark.parametrize("mod", AGENTS, ids=lambda m: m.AGENT)
def test_an_agent_never_parses_a_response(mod):
    """الفحص على **الاستعمال**، مش على نصّ الملف.

    البحث النصّي كان بيمسك ذِكر `stop_reason` بالتوثيق — وحارس بيمنع
    الكلام عن الشي بدل ما يمنع عمله ما بيحرس شي، وبيدفع الناس يشيلوا
    التوثيق عشان يمرقوا.
    """
    tree = ast.parse((ROOT / "ai_pipeline/agents" / f"{mod.AGENT}.py")
                     .read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"text", "stop_reason", "stop_details",
                                     "parsed", "content", "usage"}, (
                f"{mod.AGENT}: بيقرا `.{node.attr}` من الاستجابة")
        if isinstance(node, ast.Call):
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", ""))
            assert name not in {"model_validate_json", "model_validate",
                                "loads"}, f"{mod.AGENT}: بيفكّ ترميز — {name}"


@pytest.mark.parametrize("mod", AGENTS, ids=lambda m: m.AGENT)
def test_an_agent_never_imports_a_concrete_provider(mod):
    src = (ROOT / "ai_pipeline/agents" / f"{mod.AGENT}.py").read_text("utf-8")
    for node in ast.walk(ast.parse(src)):
        mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                else [node.module] if isinstance(node, ast.ImportFrom) and node.module
                else [])
        for m in mods:
            for bad in ("anthropic", "recorded", "scripted"):
                assert bad not in m, f"{mod.AGENT}: مربوط بمزوّد بعينه — {m}"


# ══ الثلاثية الصحيحة: prompt · schema · expand ══════════════════════
@pytest.mark.parametrize("mod,schema", [
    (script, SegmentsProposal), (visual, AssetIntent),
    (typography, TypographyProposal)], ids=lambda x: getattr(x, "AGENT", ""))
def test_each_agent_sends_its_own_schema_and_prompt(mod, schema, theme, segments):
    c = rec({"script": "ok_three_segments", "visual": "ok_three_intents",
             "typography": "ok_three_segments"}[mod.AGENT])
    if mod is script:
        mod.run(c, SRC, TOKENS)
    elif mod is visual:
        mod.run(c, segments)
    else:
        mod.run(c, segments, theme)
    req = c.calls[0]
    assert req.schema is schema
    assert req.prompt.agent == mod.AGENT and req.prompt.version == "v1"
    assert req.prompt.sha256 == prompt_ref(mod.AGENT, "v1").sha256
    assert req.system.startswith("You are")


def test_the_system_prompt_is_the_registered_file(theme, segments):
    from ai_pipeline.agents.prompts import prompt_text
    c = rec("ok_three_segments")
    script.run(c, SRC, TOKENS)
    assert c.calls[0].system == prompt_text("script", "v1")


# ══ الكتل: أقلّ امتياز ══════════════════════════════════════════════
def test_the_script_agent_sends_the_source_and_the_index_map():
    c = rec("ok_three_segments")
    script.run(c, SRC, TOKENS)
    tags = {b.tag: b.text for b in c.calls[0].user_blocks}
    assert set(tags) == {"source", "alignment"}
    assert tags["source"] == SRC
    assert tags["alignment"].startswith("0\tوَمَن")
    assert tags["alignment"].count("\n") == len(TOKENS) - 1


def test_the_visual_agent_never_sees_the_arabic_text(segments):
    """الوكيل البصري ما بيحتاج يشوف النص المقدّس ليختار لقطة."""
    c = rec("ok_three_intents")
    visual.run(c, segments)
    blob = "\n".join(b.text for b in c.calls[0].user_blocks)
    assert [b.tag for b in c.calls[0].user_blocks] == ["constraints"]
    for tok in TOKENS:
        assert tok not in blob, f"نصّ مصدري تسرّب للوكيل البصري: {tok}"


def test_the_typography_agent_gets_counts_not_text(segments, theme):
    c = rec("ok_three_segments")
    typography.run(c, segments, theme)
    body = c.calls[0].user_blocks[0].text
    assert "font_role: body" in body and "use this exact value" in body
    assert "word_count" in body
    for tok in TOKENS:
        assert tok not in body


# ══ المخرَجات ═══════════════════════════════════════════════════════
def test_the_script_agent_returns_a_phase_one_contract():
    c = SegmentsContract
    out = script.run(rec("ok_three_segments"), SRC, TOKENS)
    assert isinstance(out, c) and len(out.segments) == 3
    assert out.segments[0].text_arabic == " ".join(TOKENS[0:4])


def test_the_visual_agent_returns_a_validated_intent(segments):
    out = visual.run(rec("ok_three_intents"), segments)
    assert isinstance(out, AssetIntent)
    assert [i.segment_id for i in out.intents] == [1, 2, 3]
    assert out.intents[0].motion == "zoom_in"


def test_the_typography_agent_returns_a_phase_one_contract(segments, theme):
    out = typography.run(rec("ok_three_segments"), segments, theme)
    assert isinstance(out, TypographyContract)
    assert out.theme == "dark_gold_v1"
    assert out.overrides[2].font_size == 58        # 64 + (-1 × 6)
    assert out.overrides[3].text_color == "#D8A657"


def test_the_visual_agent_stops_short_of_a_phase_one_contract(segments):
    """مقصود: `Asset` بيوصف الأصل المختار، والوكيل ما بيملك هويته."""
    out = visual.run(rec("ok_three_intents"), segments)
    dumped = json.loads(out.model_dump_json())
    for owned in ("provider", "provider_ref", "file_path", "sha256",
                  "license", "probe", "in_point"):
        assert owned not in json.dumps(dumped["intents"][0])


# ══ الفشل بيمرق بالـharness ═════════════════════════════════════════
@pytest.mark.parametrize("mod", AGENTS, ids=lambda m: m.AGENT)
def test_a_refusal_fails_closed_for_every_agent(mod, segments, theme):
    c = ScriptedFailureClient([SC.refusal("policy")])
    args = {"script": (SRC, TOKENS), "visual": (segments,),
            "typography": (segments, theme)}[mod.AGENT]
    with pytest.raises(AgentError, match="refusal"):
        mod.run(c, *args)
    assert len(c.calls) == 1


def test_a_missing_segment_intent_is_a_semantic_error(segments):
    h = AgentHarness(c := rec("bad_missing_segment", "ok_three_intents"))
    visual.run(c, segments, harness=h)
    assert h.runs[0]["validation"] == "semantic_error"
    assert "مقاطع بلا نيّة" in h.runs[0]["error"]


def test_an_invented_segment_id_is_rejected(segments):
    h = AgentHarness(c := rec("bad_invented_segment", "ok_three_intents"))
    visual.run(c, segments, harness=h)
    assert "مش موجودة" in h.runs[0]["error"]


def test_a_divergent_font_role_fails_closed(segments, theme):
    """قرار (ج): الرفض الصريح بدل الإسقاط الصامت."""
    h = AgentHarness(c := rec("bad_wrong_font_role", "bad_wrong_font_role"))
    with pytest.raises(AgentError, match="ما بيحمل خطًّا لكل"):
        typography.run(c, segments, theme, harness=h)
    assert len(c.calls) == 2


def test_a_repair_works_through_the_agent(segments):
    h = AgentHarness(c := rec("bad_missing_segment", "ok_three_intents"))
    out = visual.run(c, segments, harness=h)
    assert len(out.intents) == 3 and len(c.calls) == 2
    assert [b.tag for b in c.calls[1].user_blocks] == ["constraints", "repair"]


@pytest.mark.parametrize("mod", AGENTS, ids=lambda m: m.AGENT)
def test_an_unregistered_version_fails_before_any_call(mod, segments, theme):
    from ai_pipeline.errors import ContractError
    c = rec("ok_three_segments")
    args = {"script": (SRC, TOKENS), "visual": (segments,),
            "typography": (segments, theme)}[mod.AGENT]
    with pytest.raises(ContractError, match="ما في prompt مسجَّل"):
        mod.run(c, *args, version="v99")
    assert c.calls == []


def test_quantize_is_never_called_by_any_agent(monkeypatch, segments, theme):
    import ai_pipeline.timeline.quantize as Q
    monkeypatch.setattr(Q, "quantize", lambda *a, **k: pytest.fail("quantize!"))
    script.run(rec("ok_three_segments"), SRC, TOKENS)
    visual.run(rec("ok_three_intents"), segments)
    typography.run(rec("ok_three_segments"), segments, theme)

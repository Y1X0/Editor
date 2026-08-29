"""E2E — السلسلة كاملة، بلا شبكة وبلا مفتاح وبلا ffmpeg.

    fixture ─► Script ─► SegmentsContract ─► Visual ─► AssetIntent
            ─► Typography ─► TypographyContract
            ─► (الطبقة الحتمية) quantize ─► Timeline

مش «ما طلع استثناء». الفحوص هون بتثبت **ملكية القرار**: النص من
المصدر، والتوقيت من المحاذاة، والحواجز الأربعة شغّالة على الوكلاء
الثلاثة مش على الـharness لحاله.

والطبقة الحتمية بتنشغّل هون **بعد** مرحلة الوكلاء بقصد: بلاها ما في
إثبات إن التوقيت بيجي من `alignment` — وهاد نص المطلوب.
"""
import json
import pathlib
import subprocess

import pytest

from ai_pipeline.agents import script, typography, visual
from ai_pipeline.agents.expand import ResolvedAsset, ThemeView, expand_asset_intents
from ai_pipeline.agents.prompts import prompt_ref
from ai_pipeline.agents.schemas import AssetIntent
from ai_pipeline.agents.providers import scripted as SC
from ai_pipeline.agents.providers.recorded import RecordedClient
from ai_pipeline.agents.providers.scripted import ScriptedFailureClient
from ai_pipeline.agents.runner import AgentHarness
from ai_pipeline.errors import AgentError
from ai_pipeline.models.alignment import Alignment, Word
from ai_pipeline.models.assets import Probe
from ai_pipeline.models.project import Output
from ai_pipeline.models.segments import SegmentsContract
from ai_pipeline.models.typography import TypographyContract
from ai_pipeline.source import slice_text, tokenize
from ai_pipeline.timeline.quantize import quantize

FIX = pathlib.Path(__file__).parent / "fixtures" / "llm"
SRC = "وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ إِنَّ اللَّهَ بَالِغُ أَمْرِهِ"
TOKENS = tokenize(SRC)
THEME = ThemeView(theme_id="dark_gold_v1", font_role="body", base_font_size=64,
                  size_step_px=6, max_lines=2,
                  color_hex={"primary": "#F3E5AB", "muted": "#9A9384",
                             "accent": "#D8A657"})


def alignment(start=0.82, step=0.55, span=0.48) -> Alignment:
    return Alignment(method="test", words=tuple(
        Word(i=i, text=w, start=round(start + i * step, 3),
             end=round(start + i * step + span, 3), conf=0.9)
        for i, w in enumerate(TOKENS)))


def resolved(segments: SegmentsContract) -> dict[int, ResolvedAsset]:
    """اللي الـResolver رح يسلّمه (Commit 9). مبنيّ بالإيد هون بقصد."""
    return {s.segment_id: ResolvedAsset(
        segment_id=s.segment_id, source_type="local", provider="fixture",
        provider_ref=f"f{s.segment_id}",
        file_path=pathlib.Path(f"a{s.segment_id}.mp4"),
        sha256=f"{s.segment_id:064d}", license="test",
        probe=Probe(width=3840, height=2160, fps=25.0, duration=30.0))
        for s in segments.segments}


def rec(**per_agent):
    return RecordedClient(FIX, per_agent)


# ── حرّاس التشغيل: ولا شبكة، ولا ffmpeg، ولا SDK ────────────────────
@pytest.fixture(autouse=True)
def no_side_channels(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    for name in ("run", "Popen", "check_output", "call"):
        monkeypatch.setattr(subprocess, name, lambda *a, **k: pytest.fail(
            f"عملية فرعية انشغّلت بالـdry run: subprocess.{name}"))
    real = __import__

    def guard(name, *a, **k):
        if name.split(".")[0] == "anthropic":
            pytest.fail("انستورد anthropic أثناء التشغيل")
        return real(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", guard)


@pytest.fixture
def no_quantize(monkeypatch):
    """spy بيفشّل لو **الوكلاء** لمسوا الطبقة الحتمية."""
    import ai_pipeline.timeline.quantize as Q
    calls = []
    monkeypatch.setattr(Q, "quantize", lambda *a, **k: (
        calls.append(a), pytest.fail("quantize انتنادت من طبقة الوكلاء"))[0])
    return calls


# ══════════════════════ المسار الكامل ══════════════════════════════
def run_agents(client, harness=None):
    h = harness or AgentHarness(client)
    seg = script.run(client, SRC, TOKENS, harness=h)
    intents = visual.run(client, seg, harness=h)
    typo = typography.run(client, seg, THEME, harness=h)
    return h, seg, intents, typo


def test_e2e_happy_path_produces_all_three_contracts(no_quantize):
    c = rec(script_v1="ok_three_segments", visual_v1="ok_three_intents",
            typography_v1="ok_three_segments")
    h, seg, intents, typo = run_agents(c)

    assert isinstance(seg, SegmentsContract) and len(seg.segments) == 3
    assert [i.segment_id for i in intents.intents] == [1, 2, 3]
    assert isinstance(typo, TypographyContract) and typo.theme == "dark_gold_v1"
    assert len(c.calls) == 3 and len(h.runs) == 3
    assert [r["validation"] for r in h.runs] == ["ok", "ok", "ok"]


def test_the_chain_is_actually_chained(no_quantize):
    """مخرَج كل وكيل هو مدخل اللي بعده — مش تشغيلًا موازيًا."""
    c = rec(script_v1="ok_three_segments", visual_v1="ok_three_intents",
            typography_v1="ok_three_segments")
    _, seg, intents, typo = run_agents(c)
    ids = [s.segment_id for s in seg.segments]
    assert [i.segment_id for i in intents.intents] == ids
    assert [t.segment_id for t in typo.segments] == ids
    # الوكيل البصري شاف نيّات المقاطع اللي طلعت من الأول، مش الـfixture
    sent = c.calls[1].user_blocks[0].text
    for s in seg.segments:
        assert s.visual_mood_prompt in sent


# ── ٣ · الـprovenance: fixture مربوط بـagent+version+case ───────────
def test_each_call_carries_its_registered_prompt_identity(no_quantize):
    c = rec(script_v1="ok_three_segments", visual_v1="ok_three_intents",
            typography_v1="ok_three_segments")
    h, *_ = run_agents(c)
    for rec_, agent in zip(h.runs, ("script", "visual", "typography")):
        assert rec_["agent"] == agent
        assert rec_["prompt_version"] == "v1"
        assert rec_["prompt_sha256"] == prompt_ref(agent, "v1").sha256
        assert rec_["provider"] == "RecordedClient"


def test_a_fixture_is_bound_to_the_prompt_version(no_quantize):
    """`script_v2` ما بياخد fixture `script_v1` — الإصدار جزء من الهوية."""
    from ai_pipeline.errors import ContractError
    c = rec(script_v1="ok_three_segments")
    with pytest.raises(ContractError, match="ما في prompt مسجَّل"):
        script.run(c, SRC, TOKENS, version="v2")


# ── ٤ · النص من المصدر، مش من الـLLM ───────────────────────────────
def test_the_final_arabic_text_is_sliced_from_the_source(no_quantize):
    c = rec(script_v1="ok_three_segments")
    seg = script.run(c, SRC, TOKENS)
    for s in seg.segments:
        assert s.text_arabic == slice_text(TOKENS, s.word_start, s.word_end)
    assert "".join(s.text_arabic for s in seg.segments).replace(" ", "") == \
        SRC.replace(" ", "")


def test_the_fixture_cannot_supply_the_text(no_quantize):
    """`bad_text_injection` بتحاول تمرّر `text_arabic` — بتفشل بالـschema."""
    payload = json.loads((FIX / "script_v1/bad_text_injection.json")
                         .read_text("utf-8"))["text"]
    assert "نص مستبدَل" in payload, "الـfixture ما بتحاول الحقن أصلًا"
    h = AgentHarness(c := RecordedClient(
        FIX, {"script_v1": ["bad_text_injection", "bad_text_injection"]}))
    with pytest.raises(AgentError, match="بعد إصلاح واحد"):
        script.run(c, SRC, TOKENS, harness=h)
    assert [r["validation"] for r in h.runs] == ["schema_error"] * 2


def test_no_fixture_string_reaches_the_arabic_text(no_quantize):
    c = rec(script_v1="ok_three_segments")
    seg = script.run(c, SRC, TOKENS)
    blob = " ".join(s.text_arabic for s in seg.segments)
    for s in seg.segments:                    # النيّات البصرية إنجليزية
        assert s.visual_mood_prompt not in blob


# ── ٥ · التوقيت من المحاذاة، مش من الـLLM ──────────────────────────
def build_timeline(seg: SegmentsContract, al: Alignment):
    """الطبقة الحتمية: عقود الوكلاء + المحاذاة ──► `Timeline`.

    الأصول مبنيّة بالإيد لأن الـResolver لسا ما انبنى (Commit 9)؛ وهاد
    بالضبط الشكل اللي رح يسلّمه.
    """
    intents = AssetIntent.model_validate_json(json.dumps({"intents": [
        {"segment_id": s.segment_id, "query": "q", "shot_type": "wide",
         "palette": "charcoal"} for s in seg.segments]}))
    assets = expand_asset_intents(intents, resolved(seg), THEME)
    return quantize(Output(), seg, al, assets,
                    audio_duration=max(w.end for w in al.words) + 0.5)


def test_timestamps_come_from_the_alignment_not_the_model():
    c = rec(script_v1="ok_three_segments")
    seg = script.run(c, SRC, TOKENS)
    al = alignment()
    tl = build_timeline(seg, al)
    for span, s in zip(tl.text_spans, seg.segments):
        assert span.f_start == round(al.words[s.word_start].start * 30)


def test_shifting_the_alignment_shifts_the_timeline_with_the_same_fixture():
    """نفس مخرَج النموذج + محاذاة مختلفة = timeline مختلف.

    فالزمن **ما بيجي من الـfixture** — لو كان بيجي منها ما كان يتغيّر.
    """
    c = rec(script_v1="ok_three_segments")
    seg = script.run(c, SRC, TOKENS)
    a = build_timeline(seg, alignment(start=0.82))
    b = build_timeline(seg, alignment(start=2.00))
    assert a.text_spans[0].f_start != b.text_spans[0].f_start
    assert b.text_spans[0].f_start == round(2.00 * 30)


def test_the_same_inputs_give_a_byte_identical_timeline():
    c1 = rec(script_v1="ok_three_segments")
    c2 = rec(script_v1="ok_three_segments")
    a = build_timeline(script.run(c1, SRC, TOKENS), alignment())
    b = build_timeline(script.run(c2, SRC, TOKENS), alignment())
    assert a.model_dump_json() == b.model_dump_json()


def test_the_contracts_carry_no_timestamp_at_all(no_quantize):
    c = rec(script_v1="ok_three_segments", visual_v1="ok_three_intents",
            typography_v1="ok_three_segments")
    _, seg, intents, typo = run_agents(c)
    banned = {"start", "end", "duration", "timestamp"}

    def keys(obj):
        if isinstance(obj, dict):
            return set(obj) | {k for v in obj.values() for k in keys(v)}
        if isinstance(obj, list):
            return {k for v in obj for k in keys(v)}
        return set()

    for contract in (seg, intents, typo):
        found = keys(json.loads(contract.model_dump_json())) & banned
        assert not found, f"{type(contract).__name__} فيه حقل زمني: {found}"


# ══ ٧ · الحواجز الأربعة، على الوكلاء الثلاثة ═══════════════════════
@pytest.mark.parametrize("agent", ["script", "visual", "typography"])
def test_e2e_refusal_fails_closed_for_every_agent(agent, no_quantize):
    seg = script.run(rec(script_v1="ok_three_segments"), SRC, TOKENS)
    h = AgentHarness(c := ScriptedFailureClient([SC.refusal("policy")]))
    call = {"script": lambda: script.run(c, SRC, TOKENS, harness=h),
            "visual": lambda: visual.run(c, seg, harness=h),
            "typography": lambda: typography.run(c, seg, THEME, harness=h)}[agent]
    with pytest.raises(AgentError, match="بلا إعادة محاولة"):
        call()
    assert len(c.calls) == 1, "الرفض ما بيتعاد"
    # **التصنيف، مش نصّ الرسالة.** لو مرق الرفض لمسار «سبب توقّف غير
    # معروف» بتضل الرسالة تحتوي كلمة `refusal` والفحص بيمرق وهو ما قاس
    # شي — مقيسة: الطفرة على `NO_RETRY_STOP` مرقت بالصيغة الأولى.
    assert h.runs[0]["validation"] == "stop_refusal"
    assert "policy" in h.runs[0]["error"], "تصنيف الرفض ضاع من السجلّ"


def test_e2e_malformed_then_repair_then_success(no_quantize):
    h = AgentHarness(c := RecordedClient(
        FIX, {"script_v1": ["bad_malformed", "ok_three_segments"]}))
    seg = script.run(c, SRC, TOKENS, harness=h)
    assert len(seg.segments) == 3 and len(c.calls) == 2
    assert [r["validation"] for r in h.runs] == ["schema_error", "ok"]
    assert [b.tag for b in c.calls[1].user_blocks] == \
        ["source", "alignment", "repair"]


def test_e2e_malformed_twice_fails_closed(no_quantize):
    h = AgentHarness(c := RecordedClient(
        FIX, {"script_v1": ["bad_malformed", "bad_malformed"]}))
    with pytest.raises(AgentError, match="بعد إصلاح واحد"):
        script.run(c, SRC, TOKENS, harness=h)
    assert len(c.calls) == 2, "ولا محاولة ثالثة"


def test_e2e_semantic_failure_then_repair_then_success(no_quantize):
    """`bad_coverage_gap` بتمرق الـschema وبتفشل بـ`check_coverage`."""
    h = AgentHarness(c := RecordedClient(
        FIX, {"script_v1": ["bad_coverage_gap", "ok_three_segments"]}))
    seg = script.run(c, SRC, TOKENS, harness=h)
    assert len(seg.segments) == 3
    assert [r["validation"] for r in h.runs] == ["semantic_error", "ok"]


def test_e2e_semantic_failure_twice_fails_closed(no_quantize):
    h = AgentHarness(c := RecordedClient(
        FIX, {"script_v1": ["bad_coverage_gap", "bad_duplicate_ids"]}))
    with pytest.raises(AgentError):
        script.run(c, SRC, TOKENS, harness=h)
    assert [r["validation"] for r in h.runs] == ["semantic_error"] * 2


def test_e2e_visual_semantic_repair_across_the_chain(no_quantize):
    seg = script.run(rec(script_v1="ok_three_segments"), SRC, TOKENS)
    h = AgentHarness(c := RecordedClient(
        FIX, {"visual_v1": ["bad_missing_segment", "ok_three_intents"]}))
    out = visual.run(c, seg, harness=h)
    assert len(out.intents) == 3
    assert h.runs[0]["validation"] == "semantic_error"


def test_e2e_schema_violation_fails(no_quantize):
    h = AgentHarness(c := RecordedClient(
        FIX, {"visual_v1": ["bad_enum_value", "bad_enum_value"]}))
    seg = script.run(rec(script_v1="ok_three_segments"), SRC, TOKENS)
    with pytest.raises(AgentError):
        visual.run(c, seg, harness=h)
    assert all(r["validation"] == "schema_error" for r in h.runs)


def test_e2e_failure_never_falls_back(no_quantize, tmp_path, monkeypatch):
    """فشل الوكيل بينهي الأمر: ولا عقد بينكتب، ولا مقسِّم قاعدي بينشغّل."""
    monkeypatch.chdir(tmp_path)
    h = AgentHarness(c := RecordedClient(
        FIX, {"script_v1": ["bad_malformed", "bad_malformed"]}))
    with pytest.raises(AgentError):
        script.run(c, SRC, TOKENS, harness=h)
    assert list(tmp_path.rglob("*")) == [], "انكتب شي رغم الفشل"


# ══ ٦ · ولا لمسة للطبقة الحتمية أثناء الوكلاء ══════════════════════
def test_the_agent_stage_never_touches_quantize_or_ffmpeg(no_quantize):
    c = rec(script_v1="ok_three_segments", visual_v1="ok_three_intents",
            typography_v1="ok_three_segments")
    run_agents(c)
    assert no_quantize == []


def test_the_deterministic_layer_runs_only_after_the_agents():
    """وبتشتغل فعلًا — بلا هيك «ما انتنادت» ادعاء بلا معنى."""
    seg = script.run(rec(script_v1="ok_three_segments"), SRC, TOKENS)
    tl = build_timeline(seg, alignment())
    assert tl.total_frames > 0
    assert sum(s.n_frames for s in tl.visual_spans) == tl.total_frames

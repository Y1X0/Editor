"""الـseam: Proposal ──► عقد Phase 1.

هون بينثبت إن الوكيل ما بيقدر يوصل للرندر بشي ما بيملكه: النص من
المصدر، والتوقيت مش موجود أصلًا، وهوية الأصل من الـResolver، والخط
واللون من الـtheme.
"""
import ast
import json
import pathlib

import pytest
from pydantic import ValidationError

from ai_pipeline.agents import expand as EX
from ai_pipeline.agents.expand import (
    ResolvedAsset, ThemeView, expand_asset_intents,
    expand_segments_proposal, expand_typography_proposal,
)
from ai_pipeline.agents.schemas import (
    AssetIntent, SegmentsProposal, TypographyProposal,
)
from ai_pipeline.errors import AgentError, ContractError, TextIntegrityError
from ai_pipeline.models.assets import Probe
from ai_pipeline.source import slice_text, tokenize

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = "وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ إِنَّ اللَّهَ بَالِغُ أَمْرِهِ"
#          0      1        2      3       4      5       6    7        8      9


@pytest.fixture
def toks():
    return tokenize(SCRIPT)


@pytest.fixture
def theme():
    return ThemeView(
        theme_id="dark_gold_v1", font_role="body", base_font_size=64,
        size_step_px=6, max_lines=2, fit="cover",
        color_hex={"primary": "#F3E5AB", "muted": "#9A9384", "accent": "#D8A657"})


def _prop(*spans):
    return SegmentsProposal.model_validate_json(json.dumps({"segments": [
        {"segment_id": i, "word_start": a, "word_end": b,
         "visual_mood_prompt": f"mood {i}"}
        for i, (a, b) in enumerate(spans, 1)]}))


def _res(sid, dur=30.0):
    return ResolvedAsset(
        segment_id=sid, source_type="local", provider="fixture",
        provider_ref=f"f{sid}", file_path=pathlib.Path(f"a{sid}.mp4"),
        sha256="a" * 64, license="test",
        probe=Probe(width=3840, height=2160, fps=25.0, duration=dur))


def _intent(*sids, motion="none"):
    return AssetIntent.model_validate_json(json.dumps({"intents": [
        {"segment_id": s, "query": "rain", "shot_type": "wide",
         "palette": "charcoal", "motion": motion} for s in sids]}))


def _typo(*items):
    return TypographyProposal.model_validate_json(
        json.dumps({"segments": list(items)}))


# ══ A · المصدر هو صاحب النص ═════════════════════════════════════════
def test_text_comes_from_the_source_slice(toks):
    c = expand_segments_proposal(_prop((0, 4), (4, 10)), toks)
    assert c.segments[0].text_arabic == slice_text(toks, 0, 4)
    assert c.segments[1].text_arabic == slice_text(toks, 4, 10)
    assert c.segments[0].text_arabic == "وَمَن يَتَوَكَّلْ عَلَى اللَّهِ"


def test_the_proposal_has_no_text_field_to_override_with(toks):
    """مصدر النص وحيد لأن الاقتراح **ما فيه** حقل نصّي أصلًا."""
    props = set(SegmentsProposal.model_json_schema()["$defs"]
                ["SegmentProposal"]["properties"])
    assert not (props & {"text", "text_arabic", "content"})
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        SegmentsProposal.model_validate_json(json.dumps({"segments": [
            {"segment_id": 1, "word_start": 0, "word_end": 4,
             "visual_mood_prompt": "m", "text_arabic": "نص مزوَّر"}]}))


def test_tashkeel_survives_the_expansion_byte_for_byte(toks):
    c = expand_segments_proposal(_prop((0, 10)), toks)
    assert c.segments[0].text_arabic == " ".join(toks)
    import unicodedata
    assert sum(1 for ch in c.segments[0].text_arabic
               if unicodedata.category(ch) == "Mn") >= 15


def test_visual_mood_prompt_passes_through(toks):
    c = expand_segments_proposal(_prop((0, 5), (5, 10)), toks)
    assert [s.visual_mood_prompt for s in c.segments] == ["mood 1", "mood 2"]


# ══ B · التوقيت ما بيجي من الوكيل ═══════════════════════════════════
def test_expansion_output_carries_no_timestamps(toks):
    """`Segment` تبع Phase 1 بلا حقول زمنية — فما في مكان تتسرّب منه."""
    c = expand_segments_proposal(_prop((0, 10)), toks)
    dumped = json.loads(c.model_dump_json())
    for seg in dumped["segments"]:
        assert not (set(seg) & {"start", "end", "duration", "timestamp"})


@pytest.mark.parametrize("key", ["start", "end", "duration"])
def test_a_proposal_carrying_a_timestamp_never_reaches_expand(key):
    """الفشل بيصير عند **القراءة**، قبل ما `expand` تشوف الكائن."""
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        SegmentsProposal.model_validate_json(json.dumps({"segments": [
            {"segment_id": 1, "word_start": 0, "word_end": 4,
             "visual_mood_prompt": "m", key: 1.23}]}))


def test_expand_module_never_touches_alignment_or_time():
    """التوسعة ما بتقرا توقيتًا أصلًا — الزمن مسؤولية `quantize`."""
    src = (ROOT / "ai_pipeline/agents/expand.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "alignment" not in node.module, "التوسعة ما إلها شغل بالتوقيت"


# ══ C · ما في quantize ══════════════════════════════════════════════
def test_quantize_is_not_imported_by_expand():
    src = (ROOT / "ai_pipeline/agents/expand.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        assert not any("quantize" in n or n.endswith("timeline") for n in names), \
            "expand بتستورد الـtimeline — الحدّ انكسر"


def test_quantize_is_never_called_during_expansion(monkeypatch, toks, theme):
    """spy حقيقي: أي نداء بيفجّر."""
    import ai_pipeline.timeline.quantize as Q
    calls = []

    def boom(*a, **k):
        calls.append(a)
        raise AssertionError("quantize انتنادت من التوسعة")

    monkeypatch.setattr(Q, "quantize", boom)
    expand_segments_proposal(_prop((0, 10)), toks)
    expand_asset_intents(_intent(1), {1: _res(1)}, theme)
    expand_typography_proposal(_typo({"segment_id": 1}), theme)
    assert calls == []


# ══ D · الحتمية ═════════════════════════════════════════════════════
def test_segments_expansion_is_byte_identical_across_runs(toks):
    a = expand_segments_proposal(_prop((0, 4), (4, 10)), toks)
    b = expand_segments_proposal(_prop((0, 4), (4, 10)), toks)
    assert a.model_dump_json() == b.model_dump_json()
    assert a == b


def test_asset_and_typography_expansion_are_deterministic(theme):
    i, r = _intent(1, 2), {1: _res(1), 2: _res(2)}
    assert (expand_asset_intents(i, r, theme).model_dump_json()
            == expand_asset_intents(i, r, theme).model_dump_json())
    t = _typo({"segment_id": 1, "size_step": -1},
              {"segment_id": 2, "color_role": "accent"})
    assert (expand_typography_proposal(t, theme).model_dump_json()
            == expand_typography_proposal(t, theme).model_dump_json())


def test_expansion_is_pure_no_io_no_clock_no_random():
    """قراءة قرص أو ساعة أو عشوائية بتكسر الحتمية بلا ما تفشل فحصًا."""
    src = (ROOT / "ai_pipeline/agents/expand.py").read_text(encoding="utf-8")
    banned = {"random", "time", "datetime", "uuid", "os", "subprocess",
              "requests", "httpx", "open"}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in banned, a.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in banned, node.module
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "input"}, node.func.id


# ══ E · الحدود ══════════════════════════════════════════════════════
def test_first_token_only(toks):
    assert expand_segments_proposal(
        _prop((0, 1), (1, 10)), toks).segments[0].text_arabic == toks[0]


def test_last_token_only(toks):
    c = expand_segments_proposal(_prop((0, 9), (9, 10)), toks)
    assert c.segments[1].text_arabic == toks[-1]


def test_whole_script_in_one_segment(toks):
    assert expand_segments_proposal(
        _prop((0, 10)), toks).segments[0].text_arabic == " ".join(toks)


def test_index_past_the_end_fails(toks):
    with pytest.raises(AgentError, match="خارج نص"):
        expand_segments_proposal(_prop((0, 11)), toks)


@pytest.mark.parametrize("span", [(5, 3), (4, 4), (9, 1)])
def test_reversed_or_empty_range_fails_before_slicing(toks, span):
    """`slice_text` بتنفّذ قبل `Segment`، فالرمز لازم يجي من التوسعة."""
    with pytest.raises(AgentError, match="مدى فاضي أو معكوس"):
        expand_segments_proposal(_prop(span), toks)


def test_word_end_zero_is_rejected_by_the_schema_itself():
    """`word_end` عندها `ge=1` — فالصفر بيفشل قبل التوسعة، وهاد أبكر."""
    with pytest.raises(ValidationError, match="greater_than_equal"):
        _prop((0, 0))


def test_duplicate_ids_are_caught_by_the_phase_one_contract(toks):
    """ما انكتب مدقّق جديد — `SegmentsContract` بتمسكها."""
    p = SegmentsProposal.model_validate_json(json.dumps({"segments": [
        {"segment_id": 1, "word_start": 0, "word_end": 5, "visual_mood_prompt": "a"},
        {"segment_id": 1, "word_start": 5, "word_end": 10, "visual_mood_prompt": "b"}]}))
    with pytest.raises(ValidationError, match="مكرّرة"):
        expand_segments_proposal(p, toks)


def test_overlapping_spans_are_caught_by_the_phase_one_contract(toks):
    p = SegmentsProposal.model_validate_json(json.dumps({"segments": [
        {"segment_id": 1, "word_start": 0, "word_end": 6, "visual_mood_prompt": "a"},
        {"segment_id": 2, "word_start": 5, "word_end": 10, "visual_mood_prompt": "b"}]}))
    with pytest.raises(ValidationError, match="تداخل"):
        expand_segments_proposal(p, toks)


def test_incomplete_coverage_is_caught(toks):
    """ولا كلمة بتنحذف بالسكوت — `check_coverage` تبع Phase 2."""
    with pytest.raises(TextIntegrityError, match="ما بتظهر"):
        expand_segments_proposal(_prop((0, 4)), toks)


def test_a_gap_between_segments_is_caught(toks):
    with pytest.raises(TextIntegrityError, match="ما بتظهر"):
        expand_segments_proposal(_prop((0, 3), (5, 10)), toks)


def test_the_integrity_check_runs_on_the_built_contract(toks, monkeypatch):
    """إثبات إن `check_text_integrity` تبع Phase 1 بتنتنادى فعلًا."""
    seen = []
    real = EX.check_text_integrity
    monkeypatch.setattr(EX, "check_text_integrity",
                        lambda c, t: (seen.append(len(c.segments)), real(c, t))[1])
    expand_segments_proposal(_prop((0, 5), (5, 10)), toks)
    assert seen == [2]


# ══ الأصول ══════════════════════════════════════════════════════════
def test_resolver_facts_are_copied_not_invented(theme):
    r = _res(1)
    a = expand_asset_intents(_intent(1), {1: r}, theme).assets[0]
    assert (a.provider, a.provider_ref, a.sha256, a.license) == (
        r.provider, r.provider_ref, r.sha256, r.license)
    assert a.file_path == r.file_path and a.probe == r.probe


def test_only_motion_crosses_from_the_intent(theme):
    a = expand_asset_intents(_intent(1, motion="zoom_in"), {1: _res(1)}, theme)
    assert a.assets[0].motion == "zoom_in"
    assert a.assets[0].fit == theme.fit          # من الـtheme، مش الاقتراح


def test_search_guidance_has_no_home_in_the_contract(theme):
    """`query`/`shot_type`/`palette` مدخلات بحث، مش حقول عقد."""
    dumped = json.loads(expand_asset_intents(
        _intent(1), {1: _res(1)}, theme).model_dump_json())
    for key in ("query", "must_include", "must_avoid", "shot_type", "palette"):
        assert key not in dumped["assets"][0]


def test_an_intent_without_a_resolved_asset_fails(theme):
    with pytest.raises(AgentError, match="نيّات بلا أصل محلول"):
        expand_asset_intents(_intent(1, 2), {1: _res(1)}, theme)


def test_a_resolved_asset_without_an_intent_fails(theme):
    with pytest.raises(AgentError, match="أصول محلولة بلا نيّة"):
        expand_asset_intents(_intent(1), {1: _res(1), 2: _res(2)}, theme)


def test_a_mismatched_resolved_key_fails(theme):
    with pytest.raises(AgentError, match="بيحمل segment_id"):
        expand_asset_intents(_intent(1), {1: _res(2)}, theme)


def test_expand_never_fabricates_asset_identity():
    """ولا قيمة هوية أصل مكتوبة حرفيًا بـ`expand.py`."""
    src = (ROOT / "ai_pipeline/agents/expand.py").read_text(encoding="utf-8")
    for bad in ("pexels", "artgrid", "http://", "https://", ".mp4", "sha256("):
        assert bad not in src, f"هوية أصل مخترَعة: {bad}"


# ══ الـtypography ═══════════════════════════════════════════════════
def test_size_step_resolves_through_the_theme(theme):
    t = _typo({"segment_id": 1, "size_step": 0},
              {"segment_id": 2, "size_step": -2},
              {"segment_id": 3, "size_step": 2})
    o = expand_typography_proposal(t, theme).overrides
    assert (o[1].font_size, o[2].font_size, o[3].font_size) == (64, 52, 76)


def test_color_role_resolves_to_theme_hex(theme):
    t = _typo({"segment_id": 1, "color_role": "accent"})
    assert expand_typography_proposal(t, theme).overrides[1].text_color == "#D8A657"


def test_animation_passes_through(theme):
    t = _typo({"segment_id": 1, "animation": "fade_in_up"})
    assert expand_typography_proposal(t, theme).segments[0].animation == "fade_in_up"


def test_theme_id_lands_on_the_contract(theme):
    assert expand_typography_proposal(
        _typo({"segment_id": 1}), theme).theme == "dark_gold_v1"


def test_a_divergent_font_role_fails_loudly(theme):
    """عقد Phase 1 ما بيحمل خطًّا لكل مقطع — فالتمرير كان بيضيّع القرار."""
    with pytest.raises(AgentError, match="ما بيحمل خطًّا لكل"):
        expand_typography_proposal(
            _typo({"segment_id": 1, "font_role": "quranic"}), theme)


def test_a_size_outside_the_contract_bounds_fails():
    tiny = ThemeView(theme_id="t", font_role="body", base_font_size=10,
                     size_step_px=6, max_lines=2, color_hex={"primary": "#FFFFFF"})
    with pytest.raises(AgentError, match="برّا حدود العقد"):
        expand_typography_proposal(_typo({"segment_id": 1, "size_step": -2}), tiny)


def test_a_role_the_theme_does_not_define_fails():
    th = ThemeView(theme_id="t", font_role="body", base_font_size=64,
                   size_step_px=6, max_lines=2, color_hex={"primary": "#FFFFFF"})
    with pytest.raises(AgentError, match="ما بيعرّف لونًا للدور"):
        expand_typography_proposal(_typo({"segment_id": 1, "color_role": "accent"}),
                                   th)


def test_no_font_path_or_hex_is_written_in_expand():
    """الخط واللون بيجوا من الـtheme — ولا واحد مكتوب بالكود."""
    src = (ROOT / "ai_pipeline/agents/expand.py").read_text(encoding="utf-8")
    assert ".ttf" not in src and "fonts/" not in src
    import re
    assert not re.search(r'"#[0-9A-Fa-f]{6}"', src), "لون hex مكتوب بالكود"
    assert "reshaper" not in src and "shaping_engine" not in src

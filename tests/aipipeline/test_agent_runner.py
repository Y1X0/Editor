"""`AgentHarness` — الحواجز الأربعة، وسياسة الفشل المقفلة.

أهم فحص بهالملف `test_content_is_never_touched_on_refusal`: بيمرّر
استجابة قراءة `text` منها **بتفجّر**، فبيثبت إن الـharness ما لمس
المحتوى — مش إنه تجاهله بعد ما قراه.
"""
import ast
import json
import pathlib
from functools import partial

import pytest

from ai_pipeline.agents import runner as R
from ai_pipeline.agents.expand import expand_segments_proposal
from ai_pipeline.agents.providers import scripted as SC
from ai_pipeline.agents.providers.base import Block, LLMRequest, LLMResponse, PromptRef
from ai_pipeline.agents.providers.recorded import RecordedClient
from ai_pipeline.agents.providers.scripted import ScriptedFailureClient
from ai_pipeline.agents.runner import (
    MAX_ATTEMPTS, AgentHarness, AgentSpec, jsonl_sink,
)
from ai_pipeline.agents.schemas import SegmentsProposal, TypographyProposal
from ai_pipeline.errors import AgentError, ProviderError
from ai_pipeline.models.segments import SegmentsContract
from ai_pipeline.source import tokenize

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = pathlib.Path(__file__).parent / "fixtures" / "llm"
SCRIPT = "وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ إِنَّ اللَّهَ بَالِغُ أَمْرِهِ"
TOKENS = tokenize(SCRIPT)


@pytest.fixture
def spec():
    return AgentSpec(name="script", schema=SegmentsProposal,
                     expand=partial(expand_segments_proposal, tokens=TOKENS))


def req(agent="script", version="v1", schema=SegmentsProposal):
    return LLMRequest(
        prompt=PromptRef(agent, version, "b" * 64), system="sys",
        user_blocks=(Block("source", SCRIPT),), schema=schema,
        max_tokens=4096, effort="high", timeout_s=60.0)


def rec(*cases):
    return RecordedClient(FIX, list(cases))


def harness(client, **kw):
    kw.setdefault("clock", iter(range(1000)).__next__)
    kw.setdefault("now", lambda: "2026-01-01T00:00:00.000+00:00")
    return AgentHarness(client, **kw)


# ══ ١ · النجاح ══════════════════════════════════════════════════════
def test_a_good_response_becomes_a_phase_one_contract(spec):
    h = harness(rec("ok_three_segments"))
    c = h.run(spec, req())
    assert isinstance(c, SegmentsContract) and len(c.segments) == 3
    assert c.segments[0].text_arabic == " ".join(TOKENS[0:4])
    assert len(h.runs) == 1 and h.runs[0]["validation"] == "ok"


def test_success_takes_exactly_one_call(spec):
    c = rec("ok_single_segment")
    harness(c).run(spec, req())
    assert len(c.calls) == 1


# ══ ٢-٦ · الإصلاح: مرة وحدة بالضبط ══════════════════════════════════
def test_malformed_json_is_repaired_once_then_passes(spec):
    c = rec("bad_malformed", "ok_three_segments")
    h = harness(c)
    assert len(h.run(spec, req()).segments) == 3
    assert len(c.calls) == 2
    assert [r["validation"] for r in h.runs] == ["schema_error", "ok"]


def test_a_schema_error_is_repaired_once_then_passes(spec):
    c = rec("bad_extra_start_field", "ok_three_segments")
    h = harness(c)
    h.run(spec, req())
    assert [r["validation"] for r in h.runs] == ["schema_error", "ok"]


def test_a_semantic_error_is_repaired_once_then_passes(spec):
    """`bad_coverage_gap` بتمرق الـschema وبيمسكها `check_coverage`."""
    c = rec("bad_coverage_gap", "ok_three_segments")
    h = harness(c)
    h.run(spec, req())
    assert [r["validation"] for r in h.runs] == ["semantic_error", "ok"]


def test_duplicate_ids_are_caught_as_semantic_by_phase_one(spec):
    c = rec("bad_duplicate_ids", "ok_three_segments")
    h = harness(c)
    h.run(spec, req())
    assert h.runs[0]["validation"] == "semantic_error"


def test_the_repair_attempt_carries_the_validation_error(spec):
    c = rec("bad_malformed", "ok_three_segments")
    harness(c).run(spec, req())
    tags = [b.tag for b in c.calls[1].user_blocks]
    assert tags == ["source", "repair"], "محاولة الإصلاح بلا كتلة إصلاح"
    assert "التحقّق" in c.calls[1].user_blocks[-1].text
    assert [b.tag for b in c.calls[0].user_blocks] == ["source"]


def test_a_second_failure_fails_closed(spec):
    c = rec("bad_malformed", "bad_duplicate_ids")
    h = harness(c)
    with pytest.raises(AgentError, match="بعد إصلاح واحد"):
        h.run(spec, req())
    assert len(c.calls) == 2
    assert len(h.runs) == 2


# ══ ٧ · ولا محاولة ثالثة ════════════════════════════════════════════
def test_never_more_than_two_calls_however_it_fails(spec):
    """`RecordedClient` بيرمي عند نفاد التسلسل — فمحاولة ثالثة بتبيّن
    كـ«نفد تسلسل» بدل ما تمرق بصمت."""
    c = rec("bad_malformed", "bad_malformed")
    with pytest.raises(AgentError):
        harness(c).run(spec, req())
    assert len(c.calls) == MAX_ATTEMPTS == 2


def test_the_attempt_cap_is_two():
    assert MAX_ATTEMPTS == 2, "سقف المحاولات جزء من العقد المقفل"


def test_there_is_no_unbounded_retry_loop():
    """ولا `while` بالـrunner — الحلقة الوحيدة `for` على مدى محدود."""
    src = (ROOT / "ai_pipeline/agents/runner.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.While)], \
        "حلقة `while` بالـharness — الإصلاح صار غير محدود"
    fors = [n for n in ast.walk(tree) if isinstance(n, ast.For)]
    assert len(fors) == 1, "أكتر من حلقة بالـharness"
    # الخاصية المفحوصة هي **الحدّ**، مش شكل التعبير: الحلقة لازم تكون
    # مقيّدة بـ`MAX_ATTEMPTS` مباشرةً أو عبر مدى مبنيّ منه.
    ranges = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "range"]
    assert ranges, "ما في مدى محدود"
    assert any("MAX_ATTEMPTS" in ast.dump(r) for r in ranges), \
        "المدى مش مبنيًّا على MAX_ATTEMPTS — السقف صار رقمًا حرًّا"


# ══ ٨-٩ · 🚨 الحاجز ٢ ═══════════════════════════════════════════════
class Landmine:
    """بتبيّن كـ`LLMResponse`، بس قراءة `text` **بتفجّر**.

    هيك الفحص بيثبت إن الـharness **ما لمس** المحتوى — مش إنه قراه
    وتجاهله. لو انعكس ترتيب `stop_reason` والقراءة، هالفحص بينفجر.
    """

    stop_reason = "refusal"
    stop_details = {"type": "refusal", "category": "policy"}
    model = "landmine"
    request_id = "req_x"
    usage: dict = {}
    parsed = None

    @property
    def text(self):
        raise AssertionError(
            "الـharness قرا `content` قبل ما يفحص `stop_reason` — الحاجز ٢ انكسر")


class _OneShot:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def complete(self, req):
        self.calls.append(req)
        return self.resp


def test_content_is_never_touched_on_refusal(spec):
    c = _OneShot(Landmine())
    with pytest.raises(AgentError, match="refusal"):
        harness(c).run(spec, req())
    assert len(c.calls) == 1, "الرفض ما بيتعاد"


def test_a_refusal_fails_immediately_with_its_category(spec):
    c = ScriptedFailureClient([SC.refusal("cyber")])
    h = harness(c)
    with pytest.raises(AgentError, match="بلا إعادة محاولة"):
        h.run(spec, req())
    assert len(c.calls) == 1
    assert h.runs[0]["validation"] == "stop_refusal"
    assert "cyber" in h.runs[0]["error"]


def test_max_tokens_fails_immediately_and_partial_json_is_unused(spec):
    c = ScriptedFailureClient([SC.truncated()])
    h = harness(c)
    with pytest.raises(AgentError, match="max_tokens"):
        h.run(spec, req())
    assert len(c.calls) == 1, "المخرَج المقطوع ما بينصلَّح — هو مقطوع مش ناقص"
    assert h.runs[0]["validation"] == "stop_max_tokens"


def test_an_unknown_stop_reason_fails(spec):
    weird = LLMResponse(text='{"segments": []}', stop_reason="pause_turn",
                        model="x")
    c = _OneShot(weird)
    with pytest.raises(AgentError, match="سبب توقّف غير معروف"):
        harness(c).run(spec, req())


# ══ ١٠ · استجابة فاضية ══════════════════════════════════════════════
def test_an_empty_response_fails_without_repair(spec):
    c = ScriptedFailureClient([SC.empty()])
    h = harness(c)
    with pytest.raises(AgentError, match="استجابة فاضية"):
        h.run(spec, req())
    assert len(c.calls) == 1, "ما في خطأ تحقّق نرجّعه، فما في شي نصلّحه"
    assert h.runs[0]["validation"] == "empty"


def test_whitespace_only_counts_as_empty(spec):
    c = _OneShot(LLMResponse(text="   \n\t ", stop_reason="end_turn", model="x"))
    with pytest.raises(AgentError, match="استجابة فاضية"):
        harness(c).run(spec, req())


# ══ ١١-١٢ · فشل النقل ═══════════════════════════════════════════════
def test_a_transient_failure_is_retried_once_then_succeeds(spec):
    ok = json.loads((FIX / "script_v1/ok_single_segment.json")
                    .read_text(encoding="utf-8"))["text"]
    c = ScriptedFailureClient([ProviderError("503"), SC.ok(ok)])
    h = harness(c)
    assert len(h.run(spec, req()).segments) == 1
    assert len(c.calls) == 2
    assert [r["validation"] for r in h.runs] == ["provider_error", "ok"]


@pytest.mark.parametrize("exc", [ProviderError("503"), TimeoutError("مهلة"),
                                 ConnectionError("انقطاع")])
def test_repeated_transport_failure_exhausts_and_raises(spec, exc):
    c = ScriptedFailureClient([exc, exc])
    h = harness(c)
    with pytest.raises(ProviderError, match="نفدت المحاولات"):
        h.run(spec, req())
    assert len(c.calls) == MAX_ATTEMPTS
    assert all(r["validation"] == "provider_error" for r in h.runs)


def test_a_transport_failure_then_a_schema_error_still_stops_at_two(spec):
    """الميزانية **مشتركة**: نداءان مهما كان مزيج الأسباب."""
    c = ScriptedFailureClient([ProviderError("503"), SC.ok("not json")])
    with pytest.raises(AgentError):
        harness(c).run(spec, req())
    assert len(c.calls) == 2


# ══ ١٣-١٤ · الحاجز ٤ وحدود المسار ═══════════════════════════════════
def test_the_runner_knows_nothing_about_a_rule_segmenter():
    src = (ROOT / "ai_pipeline/agents/runner.py").read_text(encoding="utf-8")
    low = src.lower()
    for word in ("rule_segmenter", "rulesegmenter", "fallback", "segmenter"):
        assert word not in low, f"احتياطي صامت بالـharness: {word}"


def test_failure_returns_nothing_it_only_raises(spec):
    """لو حدا حطّ `except AgentError: rule_segmenter(...)` بيرجع عقدًا،
    وهالفحص بيفشل لأنه بينتظر رمية."""
    c = ScriptedFailureClient([SC.refusal(), SC.refusal()])
    with pytest.raises(AgentError):
        harness(c).run(spec, req())


def test_quantize_is_never_called(monkeypatch, spec):
    import ai_pipeline.timeline.quantize as Q
    monkeypatch.setattr(Q, "quantize", lambda *a, **k: pytest.fail(
        "quantize انتنادت من الـharness"))
    harness(rec("ok_three_segments")).run(spec, req())


def test_the_runner_does_not_import_the_timeline_or_a_provider():
    src = (ROOT / "ai_pipeline/agents/runner.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for n in names:
            assert "quantize" not in n and "timeline" not in n, n
            assert "anthropic" not in n and "recorded" not in n, n


# ══ ١٥ · ولا عقد بينكتب عند الفشل ═══════════════════════════════════
def test_nothing_is_written_anywhere_on_failure(tmp_path, spec, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))
    c = ScriptedFailureClient([SC.refusal()])
    with pytest.raises(AgentError):
        harness(c).run(spec, req())
    assert set(tmp_path.rglob("*")) == before


def test_the_harness_never_writes_by_itself(tmp_path, spec, monkeypatch):
    """حتى بالنجاح: الكتابة شغل المستدعي، مش الـharness."""
    monkeypatch.chdir(tmp_path)
    harness(rec("ok_three_segments")).run(spec, req())
    assert list(tmp_path.rglob("*")) == []


# ══ ١٦ · السجلّ ═════════════════════════════════════════════════════
REQUIRED = {"ts", "agent", "prompt_version", "prompt_sha256", "provider",
            "model", "request_id", "effort", "attempt", "stop_reason",
            "usage", "validation", "error_code", "contract_version",
            "duration_ms"}


def test_every_attempt_produces_one_record(spec):
    c = rec("bad_malformed", "ok_three_segments")
    h = harness(c)
    h.run(spec, req())
    assert len(h.runs) == len(c.calls) == 2
    assert [r["attempt"] for r in h.runs] == [1, 2]


def test_a_record_carries_every_required_field(spec):
    h = harness(rec("ok_three_segments"))
    h.run(spec, req())
    assert REQUIRED <= set(h.runs[0])
    r = h.runs[0]
    assert r["agent"] == "script" and r["prompt_version"] == "v1"
    assert r["prompt_sha256"] == "b" * 64 and r["effort"] == "high"
    assert r["contract_version"] == "1" and r["provider"] == "RecordedClient"


def test_failures_carry_the_error_code(spec):
    c = ScriptedFailureClient([SC.refusal(), SC.refusal()])
    h = harness(c)
    with pytest.raises(AgentError):
        h.run(spec, req())
    assert h.runs[0]["error_code"] == "AGENT_ERROR"


def test_the_log_carries_no_prompt_or_response_text(spec):
    """السجلّ بيقول شو صار، مش شو انقال — فما بيسرّب سرًّا ولا مصدرًا."""
    h = harness(rec("ok_three_segments"))
    h.run(spec, req())
    blob = json.dumps(h.runs, ensure_ascii=False)
    assert SCRIPT not in blob and "sys" not in json.dumps(h.runs)
    assert "visual_mood_prompt" not in blob
    for key in ("system", "text", "user_blocks", "api_key", "token"):
        assert key not in h.runs[0]


def test_the_log_carries_no_environment_or_secret(spec, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SECRET-should-never-appear")
    h = harness(rec("ok_three_segments"))
    h.run(spec, req())
    assert "SECRET" not in json.dumps(h.runs)
    assert "sk-ant" not in json.dumps(h.runs)


def test_an_injected_sink_receives_the_same_records(spec):
    got = []
    h = harness(rec("bad_malformed", "ok_three_segments"), sink=got.append)
    h.run(spec, req())
    assert got == h.runs


def test_the_jsonl_sink_appends_one_line_per_attempt(tmp_path, spec):
    p = tmp_path / "logs" / "agent_runs.jsonl"
    h = harness(rec("bad_malformed", "ok_three_segments"), sink=jsonl_sink(p))
    h.run(spec, req())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["validation"] == "ok"


def test_logging_does_not_change_the_outcome(spec):
    a = harness(rec("ok_three_segments")).run(spec, req())
    b = harness(rec("ok_three_segments"), sink=lambda r: None).run(spec, req())
    assert a.model_dump_json() == b.model_dump_json()


def test_a_failing_sink_is_not_swallowed(spec):
    """لو المصرّف انكسر، بينكشف — سجلّ ضايع بصمت أسوأ من فشل."""
    def boom(rec):
        raise RuntimeError("القرص ممتلئ")
    with pytest.raises(RuntimeError, match="القرص ممتلئ"):
        harness(rec("ok_three_segments"), sink=boom).run(spec, req())


# ══ حدود عامة ═══════════════════════════════════════════════════════
def test_a_mismatched_schema_is_rejected_before_any_call(spec):
    c = rec("ok_three_segments")
    with pytest.raises(AgentError, match="بيتوقّع"):
        harness(c).run(spec, req(schema=TypographyProposal))
    assert c.calls == [], "انتنادى المزوّد رغم عدم تطابق الـschema"


def test_the_harness_is_agent_agnostic():
    """ولا اسم وكيل بعينه بالـharness."""
    src = (ROOT / "ai_pipeline/agents/runner.py").read_text(encoding="utf-8")
    for n in ("SegmentsProposal", "AssetIntent", "TypographyProposal",
              "expand_segments", "expand_asset", "expand_typography"):
        assert n not in src, f"الـharness بيعرف {n}"

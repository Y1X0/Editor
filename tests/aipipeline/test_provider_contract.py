"""عقد المزوّد + سلامة تصنيف الأخطاء.

بهالمرحلة ما في ولا تطبيق مزوّد — فالمفحوص هو **شكل العقد** واللي
انحذف منه بقرار. وفحص الأخطاء هون لأن رموزها جزء من العقد مع
المستخدم، تمامًا زي حقول الطلب.
"""
import ast
import dataclasses
import inspect
import pathlib

import pytest

from ai_pipeline import errors as E
from ai_pipeline.agents.providers import base as B
from ai_pipeline.agents.schemas import SegmentsProposal

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _fields(cls):
    return {f.name for f in dataclasses.fields(cls)}


# ── شكل الطلب والاستجابة ─────────────────────────────────────────────
def test_request_carries_exactly_the_locked_fields():
    assert _fields(B.LLMRequest) == {
        "prompt", "system", "user_blocks", "schema",
        "max_tokens", "effort", "timeout_s"}


@pytest.mark.parametrize("banned", [
    "temperature", "top_p", "top_k", "budget_tokens", "prefill",
    "assistant_prefill", "thinking_budget", "seed"])
def test_request_cannot_carry_a_rejected_parameter(banned):
    """مقيس على `claude-opus-5`: التلاتة الأولى بترجّع 400.

    ووجود `temperature` بالعقد بيوهم إن الحتمية بتجي من المُعايِن —
    وهي بتجي من **تثبيت العقد**، لأن الرندر ما بينادي LLM أصلًا.
    """
    assert banned not in _fields(B.LLMRequest)


def test_effort_vocabulary_is_the_locked_one():
    from typing import get_args
    assert set(get_args(B.Effort)) == {"low", "medium", "high", "xhigh", "max"}


def test_response_carries_the_failure_signals():
    f = _fields(B.LLMResponse)
    assert {"stop_reason", "stop_details"} <= f, "بلاهن refusal بتمرق كجواب"
    assert {"request_id", "usage", "model"} <= f, "لازم لإعادة الإنتاج"


def test_request_and_response_are_frozen():
    r = B.LLMRequest(prompt=B.PromptRef("script", "v1", "a" * 64), system="s",
                     user_blocks=(B.Block("source", "نص"),),
                     schema=SegmentsProposal, max_tokens=4096,
                     effort="high", timeout_s=60.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.max_tokens = 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        B.PromptRef("script", "v1", "a" * 64).version = "v2"


def test_prompt_ref_pins_agent_version_and_sha():
    assert _fields(B.PromptRef) == {"agent", "version", "sha256"}


def test_source_is_a_distinct_block_tag():
    """النص غير الموثوق بيوصل موسومًا، فالتهريب مسؤولية معروفة المكان."""
    from typing import get_args
    assert "source" in get_args(B.BlockTag)


def test_client_is_a_protocol_with_one_method():
    assert "complete" in B.LLMClient.__dict__
    sig = inspect.signature(B.LLMClient.complete)
    assert list(sig.parameters) == ["self", "req"]


# ── ولا تطبيق مزوّد بهالمرحلة ────────────────────────────────────────
def test_the_provider_surface_is_exactly_what_we_declared():
    """الترتيب مقصود: العقود، ثم المزوّدان المحليّان، والـLLM آخرًا.

    الحارس بيتحدّث **بقصد** مع كل مزوّد جديد. وهو اللي مسك إضافة
    `recorded.py`/`scripted.py` بCommit 3 — يعني شغّال.
    """
    want = {"__init__.py", "base.py", "recorded.py", "scripted.py",
            "anthropic_client.py"}
    have = {p.name for p in (ROOT / "ai_pipeline/agents/providers").glob("*.py")}
    assert have == want, f"فرق غير معلَن: {have ^ want}"


def test_the_package_imports_without_the_anthropic_sdk():
    """`anthropic` تبعية اختيارية. استيرادها على مستوى موديول بيكسر
    استيراد الحزمة كلها على بيئة بلا SDK — ومعه الطقم كله.

    المسموح **وحيد**: جوّا دالة بـ`anthropic_client.py`.
    """
    allowed = ROOT / "ai_pipeline/agents/providers/anthropic_client.py"
    for f in (ROOT / "ai_pipeline").rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        top = list(tree.body)
        nested = [n for n in ast.walk(tree) if n not in top]
        for node, level in [(n, "module") for n in top] + \
                           [(n, "nested") for n in nested]:
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if not any(n.split(".")[0] == "anthropic" for n in names):
                continue
            assert level == "nested" and f == allowed, (
                f"{f.relative_to(ROOT)}: استيراد anthropic على مستوى "
                f"{level} — المسموح جوّا دالة بـanthropic_client.py فقط")


# ── errors.py: append-only ───────────────────────────────────────────
#: التسعة تبع Phase 1/2 — الاسم والرمز والوراثة. تغيير أي واحد كسر عقد.
FROZEN = {
    "NurError":           ("ERROR",                 "Exception"),
    "ContractError":      ("CONTRACT_ERROR",        "NurError"),
    "TextIntegrityError": ("TEXT_INTEGRITY_ERROR",  "NurError"),
    "AlignmentError":     ("ALIGNMENT_ERROR",       "NurError"),
    "AssetError":         ("ASSET_ERROR",           "NurError"),
    "TimelineError":      ("TIMELINE_ERROR",        "NurError"),
    "TypographyError":    ("TYPOGRAPHY_ERROR",      "NurError"),
    "FfmpegError":        ("FFMPEG_ERROR",          "NurError"),
    "QaError":            ("QA_ERROR",              "NurError"),
}
#: الإضافتان الوحيدتان المسموحتان بـPhase 3، وفق المواصفة §9.
ADDED = {"AgentError": ("AGENT_ERROR", "NurError"),
         "ProviderError": ("PROVIDER_ERROR", "NurError")}


@pytest.mark.parametrize("name", sorted(FROZEN))
def test_phase_one_errors_are_unchanged(name):
    code, parent = FROZEN[name]
    cls = getattr(E, name)
    assert cls.code == code, f"{name}: الرمز اتغيّر"
    assert cls.__bases__[0].__name__ == parent, f"{name}: الوراثة اتغيّرت"


def test_phase_one_error_semantics_are_unchanged():
    """الرمز بينطبع بين قوسين مربّعين — الشكل جزء من العقد."""
    assert str(E.TextIntegrityError("x")) == "[TEXT_INTEGRITY_ERROR] x"
    assert isinstance(E.QaError("x"), E.NurError)


@pytest.mark.parametrize("name", sorted(ADDED))
def test_the_two_new_errors_are_added_correctly(name):
    code, parent = ADDED[name]
    cls = getattr(E, name)
    assert cls.code == code and cls.__bases__[0].__name__ == parent


def test_errors_module_is_append_only():
    """ولا صنف زيادة عن التسعة + الاثنتين.

    الملف `append-only` مش `immutable`: مسموح **يزيد**، وممنوع يتغيّر أو
    يتوسّع بلا قصد. أي صنف جديد لازم ينضاف لهالجدول بقرار.
    """
    src = (ROOT / "ai_pipeline" / "errors.py").read_text(encoding="utf-8")
    defined = {n.name for n in ast.parse(src).body if isinstance(n, ast.ClassDef)}
    assert defined == set(FROZEN) | set(ADDED), (
        f"زيادة غير معلَنة: {sorted(defined - set(FROZEN) - set(ADDED))} · "
        f"ناقص: {sorted((set(FROZEN) | set(ADDED)) - defined)}")


def test_every_error_code_is_unique():
    codes = [getattr(E, n).code for n in set(FROZEN) | set(ADDED)]
    assert len(set(codes)) == len(codes), "رمزان متطابقان = تشخيص ملتبس"


def test_agent_and_provider_errors_are_distinct():
    """«ما وصلنا لجواب» غير «وصل جواب وما عبَر» — التشخيص بيفرق."""
    assert not issubclass(E.AgentError, E.ProviderError)
    assert not issubclass(E.ProviderError, E.AgentError)


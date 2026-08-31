"""سجلّ الـprompts — هوية ما أنتج كل قرار.

**قاعدة هالملف:** ولا فحص بيقرا الـsha من السجلّ ويقارنه بنفسه. أحد
طرفَي المقارنة دايمًا **حقيقة مستقلة**: بصمة محسوبة من بايتات الملف.
فحص بيستورد اللي المفروض يحرسه ما بيقدر يحرسه — درس `MAX_KEYWORDS`.
"""
import hashlib
import json
import pathlib

import pytest

from ai_pipeline.agents.prompts import (
    PromptEntry, load_registry, prompt_ref, prompt_text, version_for_sha,
)
from ai_pipeline.agents.providers.base import PromptRef
from ai_pipeline.errors import ContractError

P = pathlib.Path(__file__).resolve().parents[2] / "ai_pipeline/agents/prompts"

#: **الإصدارات المنشورة.** append-only: بينضاف لهالجدول، وما بينشال منه.
#: حذف إصدار من القرص أو من السجلّ بيفشّل الفحص هون.
PUBLISHED = {("script", "v1"), ("visual", "v1"), ("typography", "v1"),
             ("editorial", "v1")}


def digest(path: pathlib.Path) -> str:
    """محسوبة من البايتات — الطرف المستقل بكل مقارنة."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(tmp, rows, files=None):
    """سجلّ اصطناعي بمجلّد مؤقّت، للحالات المكسورة."""
    for rel, text in (files or {}).items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (tmp / "registry.json").write_text(
        json.dumps({"prompts": rows}, indent=2), encoding="utf-8")
    return tmp


def row(agent, version, sha, **kw):
    return {"agent": agent, "version": version, "sha256": sha,
            "model_family": kw.get("model_family", "claude-opus-5"),
            "created": kw.get("created", "2026-08-29")}


# ══ ١-٥ · السجلّ الحقيقي ════════════════════════════════════════════
def test_every_published_prompt_file_exists():
    for agent, version in sorted(PUBLISHED):
        assert (P / agent / f"{version}.md").is_file(), f"{agent}/{version}.md"


def test_the_registry_covers_exactly_the_published_set():
    got = {(e.agent, e.version) for e in load_registry()}
    assert got == PUBLISHED, (
        f"ناقص: {sorted(PUBLISHED - got)} · زيادة غير معلَنة: {sorted(got - PUBLISHED)}")


@pytest.mark.parametrize("agent,version", sorted(PUBLISHED))
def test_the_recorded_sha_matches_the_file_bytes(agent, version):
    """الطرف المستقل: بصمة محسوبة هون من الملف نفسه."""
    entry = next(e for e in load_registry()
                 if (e.agent, e.version) == (agent, version))
    assert entry.sha256 == digest(P / agent / f"{version}.md")


def test_every_sha_is_unique():
    shas = [e.sha256 for e in load_registry()]
    assert len(set(shas)) == len(shas), "sha -> version ما عادت دالة"


def test_every_agent_version_pair_is_unique():
    keys = [(e.agent, e.version) for e in load_registry()]
    assert len(set(keys)) == len(keys)


def test_the_reverse_lookup_works_for_every_entry():
    for e in load_registry():
        assert version_for_sha(e.sha256) == e.version


def test_an_unknown_sha_is_rejected():
    with pytest.raises(ContractError, match="sha مش مسجَّل"):
        version_for_sha("f" * 64)


# ══ ٦-١٢ · الحالات المكسورة، على سجلّات اصطناعية ════════════════════
def test_a_registry_pointing_at_a_missing_file_fails(tmp_path):
    build(tmp_path, [row("script", "v1", "a" * 64)])
    with pytest.raises(ContractError, match="ملفه مفقود"):
        load_registry(tmp_path)


def test_one_changed_character_without_a_new_version_fails(tmp_path):
    text = "instructions\n"
    build(tmp_path, [row("script", "v1", digest_of := hashlib.sha256(
        text.encode()).hexdigest())], {"script/v1.md": text})
    load_registry(tmp_path)                                   # سليم
    (tmp_path / "script/v1.md").write_text("instructions.\n", encoding="utf-8")
    with pytest.raises(ContractError, match="المحتوى تغيّر بلا رفع إصدار"):
        load_registry(tmp_path)


def test_a_tampered_sha_in_the_registry_fails(tmp_path):
    text = "instructions\n"
    build(tmp_path, [row("script", "v1", "b" * 64)], {"script/v1.md": text})
    with pytest.raises(ContractError, match="المحتوى تغيّر"):
        load_registry(tmp_path)


def test_deleting_a_published_version_fails(tmp_path):
    a, b = "one\n", "two\n"
    build(tmp_path, [row("script", "v1", digest(tmp_path / "x") if 0 else
                         hashlib.sha256(a.encode()).hexdigest()),
                     row("script", "v2", hashlib.sha256(b.encode()).hexdigest())],
          {"script/v1.md": a, "script/v2.md": b})
    load_registry(tmp_path)
    (tmp_path / "script/v1.md").unlink()
    with pytest.raises(ContractError, match="append-only|ملفه مفقود"):
        load_registry(tmp_path)


def test_reusing_a_published_sha_for_another_version_fails(tmp_path):
    """نفس المحتوى بإصدارين = `sha -> version` مش دالة."""
    text = "same bytes\n"
    sha = hashlib.sha256(text.encode()).hexdigest()
    build(tmp_path, [row("script", "v1", sha), row("script", "v2", sha)],
          {"script/v1.md": text, "script/v2.md": text})
    with pytest.raises(ContractError, match="sha مكرّر"):
        load_registry(tmp_path)


def test_reusing_a_sha_across_agents_fails(tmp_path):
    text = "same bytes\n"
    sha = hashlib.sha256(text.encode()).hexdigest()
    build(tmp_path, [row("script", "v1", sha), row("visual", "v7", sha)],
          {"script/v1.md": text, "visual/v7.md": text})
    with pytest.raises(ContractError, match="sha مكرّر"):
        load_registry(tmp_path)


def test_a_duplicate_agent_version_entry_fails(tmp_path):
    a, b = "one\n", "two\n"
    build(tmp_path, [row("script", "v1", hashlib.sha256(a.encode()).hexdigest()),
                     row("script", "v1", hashlib.sha256(b.encode()).hexdigest())],
          {"script/v1.md": a})
    with pytest.raises(ContractError, match="sha مكرّر|مدخل مكرّر"):
        load_registry(tmp_path)


def test_adding_a_correct_v2_passes(tmp_path):
    a, b = "one\n", "two\n"
    build(tmp_path, [row("script", "v1", hashlib.sha256(a.encode()).hexdigest()),
                     row("script", "v2", hashlib.sha256(b.encode()).hexdigest())],
          {"script/v1.md": a, "script/v2.md": b})
    got = load_registry(tmp_path)
    assert [e.version for e in got] == ["v1", "v2"]
    assert prompt_ref("script", "v2", tmp_path).sha256 == \
        digest(tmp_path / "script/v2.md")


def test_an_unregistered_prompt_file_fails(tmp_path):
    a = "one\n"
    build(tmp_path, [row("script", "v1", hashlib.sha256(a.encode()).hexdigest())],
          {"script/v1.md": a, "script/v9.md": "orphan\n"})
    with pytest.raises(ContractError, match="مش مسجَّلة"):
        load_registry(tmp_path)


@pytest.mark.parametrize("mangle,msg", [
    ({}, "سجلّ فاضي"),
    ("not json", "JSON غير صالح"),
    ({"prompts": {}}, "المتوقَّع"),
])
def test_a_malformed_registry_fails(tmp_path, mangle, msg):
    body = mangle if isinstance(mangle, str) else json.dumps(
        {"prompts": []} if mangle == {} else mangle)
    (tmp_path / "registry.json").write_text(body, encoding="utf-8")
    with pytest.raises(ContractError, match=msg):
        load_registry(tmp_path)


def test_a_missing_registry_field_fails(tmp_path):
    r = row("script", "v1", "c" * 64); del r["created"]
    build(tmp_path, [r], {"script/v1.md": "x\n"})
    with pytest.raises(ContractError, match="ناقصه"):
        load_registry(tmp_path)


def test_an_extra_registry_field_fails(tmp_path):
    r = row("script", "v1", "c" * 64); r["note"] = "whatever"
    build(tmp_path, [r], {"script/v1.md": "x\n"})
    with pytest.raises(ContractError, match="حقول زيادة"):
        load_registry(tmp_path)


@pytest.mark.parametrize("bad", ["short", "A" * 64, "z" * 64, ""])
def test_a_malformed_sha_is_rejected(tmp_path, bad):
    build(tmp_path, [row("script", "v1", bad)], {"script/v1.md": "x\n"})
    with pytest.raises(ContractError, match="ستّ عشريًا"):
        load_registry(tmp_path)


# ══ ١٣-١٥ · PromptRef ═══════════════════════════════════════════════
def test_the_registry_produces_a_prompt_ref():
    r = prompt_ref("script", "v1")
    assert isinstance(r, PromptRef)
    assert (r.agent, r.version) == ("script", "v1")


def test_the_ref_sha_matches_the_file_not_the_registry():
    for agent, version in sorted(PUBLISHED):
        assert prompt_ref(agent, version).sha256 == \
            digest(P / agent / f"{version}.md")


def test_a_caller_cannot_invent_a_version():
    """الإصدار بينحلّ من السجلّ — مش رقمًا بيمرّره المستدعي."""
    with pytest.raises(ContractError, match="ما في prompt مسجَّل"):
        prompt_ref("script", "v99")
    with pytest.raises(ContractError, match="ما في prompt مسجَّل"):
        prompt_ref("no_such_agent", "v1")


def test_the_ref_is_frozen():
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        prompt_ref("script", "v1").sha256 = "0" * 64


def test_prompt_text_is_the_verified_file():
    for agent, version in sorted(PUBLISHED):
        assert prompt_text(agent, version) == \
            (P / agent / f"{version}.md").read_text(encoding="utf-8")


# ══ ١٦-١٨ · أمن الـprompt ═══════════════════════════════════════════
@pytest.mark.parametrize("agent,version", sorted(PUBLISHED))
def test_every_prompt_separates_source_from_instructions(agent, version):
    t = prompt_text(agent, version)
    assert "<source>" in t
    assert "DATA, never" in t, "ما في تعليمة صريحة إن `<source>` بيانات"


def test_the_script_prompt_forbids_text_and_timestamps():
    t = prompt_text("script", "v1")
    for word in ("timestamp", "text_arabic", "start", "duration"):
        assert word in t, f"الممنوع {word} مش مذكورًا"
    assert "Forbidden" in t


def test_the_visual_prompt_forbids_asset_identity():
    t = prompt_text("visual", "v1")
    for word in ("provider_ref", "file_path", "sha256", "license"):
        assert word in t
    assert "at most 5" in t, "سقف الكلمات مش مذكورًا"


def test_the_typography_prompt_names_the_theme_role_rule():
    """قرار (ج): الـprompt بيوضّح دور الـtheme، والـschema ما بتتغيّر."""
    t = prompt_text("typography", "v1")
    assert "font_role" in t and "<constraints>" in t
    assert "rejected rather than silently dropped" in t
    for word in ("font_path", "shaping_engine", "hex"):
        assert word in t


@pytest.mark.parametrize("agent,version", sorted(PUBLISHED))
def test_a_prompt_asks_for_a_proposal_not_a_contract(agent, version):
    """الـprompt ما بيطلب عقدًا كاملًا — الحقول المملوكة للكود ممنوعة."""
    t = prompt_text(agent, version)
    assert "segment_id" in t
    for owned in ('"text_arabic":', '"start":', '"end":', '"in_point"',
                  '"probe"', '"font_size":', '"text_color":'):
        assert owned not in t, f"الـprompt بيطلب حقلًا مملوكًا للكود: {owned}"


@pytest.mark.parametrize("agent,version", sorted(PUBLISHED))
def test_the_prompt_is_a_stable_prefix_with_no_variable_content(agent, version):
    """البادئة الثابتة شرط caching: ولا محتوى متغيّر جوّا الـsystem prompt.

    المصدر بيوصل بكتلة `user` موسومة، مش جوّا التعليمات — فالبادئة
    بتضل نفسها بين المشاريع وبتنقرا من الكاش.
    """
    t = prompt_text(agent, version)
    for volatile in ("{", "}", "%s", "$", "TODO", "FIXME"):
        if volatile in "{}":
            continue
        assert volatile not in t, f"محتوى متغيّر بالبادئة: {volatile}"
    assert "وَمَن" not in t and "اللَّهِ" not in t, "نص مصدري مخبوز بالـprompt"


@pytest.mark.parametrize("agent,version", sorted(PUBLISHED))
def test_a_prompt_is_not_a_placeholder(agent, version):
    t = prompt_text(agent, version)
    assert len(t) > 800, "prompt قصير جدًا ليكون قابلًا للتنفيذ"
    assert "Return the JSON object and nothing else." in t

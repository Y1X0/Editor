"""Agent 2 — نيّة الأصل البصري.

⚠️ **هالوكيل ما بيوصل لعقد Phase 1 — وهاد صحيح مش نقص.**

`Asset` تبع Phase 1 بيوصف الأصل **المختار**: `provider` · `provider_ref`
· `file_path` · `sha256` · `license` · `probe` · `in_point`. والوكيل ما
بيملك ولا وحدة منهن، وما إله حقل يكتبها فيه. الترتيب الحقيقي:

    AssetIntent (الوكيل) ──► Resolver (بيبحث ويحمّل ويتحقّق)
                        ──► ResolvedAsset ──► expand_asset_intents
                        ──► AssetsContract (Phase 1)

فمخرَج هالوكيل `AssetIntent` مُتحقَّق منها، والـResolver (مرحلة لاحقة)
هو اللي بيكمّل. `expand_asset_intents` جاهزة من Commit 2 وبتشتغل بعده.

واللي بينفحص هون هو التطابق مع المقاطع: نيّة لكل مقطع، بنفس المعرّفات.
معرّف مخترَع أو ناقص بيفشل كخطأ دلالي، والـharness بيعطيه إصلاحًا
واحدًا.
"""
from __future__ import annotations

from ..errors import AgentError
from ..models.segments import SegmentsContract
from .prompts import prompt_ref, prompt_text
from .providers.base import Block, LLMClient, LLMRequest
from .runner import AgentHarness, AgentSpec
from .schemas import AssetIntent

AGENT = "visual"
MAX_TOKENS = 8192
EFFORT = "high"
TIMEOUT_S = 120.0


def constraints_block(segments: SegmentsContract) -> str:
    """`segment_id<TAB>visual_mood_prompt`.

    **ولا نصّ عربي هون.** الوكيل البصري ما بيحتاج يشوف النص المقدّس
    ليختار لقطة — والأقلّ امتيازًا أقلّ سطح حقن.
    """
    return "\n".join(f"{s.segment_id}\t{s.visual_mood_prompt}"
                     for s in segments.segments)


def check_intents_match(intent: AssetIntent,
                        segments: SegmentsContract) -> AssetIntent:
    """نيّة لكل مقطع، بنفس المعرّفات. بترجّع الـintent كما هي.

    التحقّق هون مش نسخة من مدقّق Phase 1: ما في عقد Phase 1 يوصف
    «نيّة»، فما في مدقّق جاهز إلها. و`expand_asset_intents` بتعيد نفس
    الفحص بعد الحلّ — وهاد مقصود: الطبقتان بتفحصوا نفس الشي بمرحلتين
    مختلفتين من عمر البيانات.
    """
    want = {s.segment_id for s in segments.segments}
    have = [i.segment_id for i in intent.intents]
    if missing := sorted(want - set(have)):
        raise AgentError(f"مقاطع بلا نيّة بصرية: {missing}")
    if extra := sorted(set(have) - want):
        raise AgentError(f"نيّات لمقاطع مش موجودة: {extra}")
    if len(have) != len(set(have)):
        dup = sorted({i for i in have if have.count(i) > 1})
        raise AgentError(f"أكتر من نيّة لنفس المقطع: {dup}")
    return intent


def run(client: LLMClient, segments: SegmentsContract, *,
        version: str = "v1", harness: AgentHarness | None = None,
        effort: str = EFFORT) -> AssetIntent:
    h = harness or AgentHarness(client)
    req = LLMRequest(
        prompt=prompt_ref(AGENT, version),
        system=prompt_text(AGENT, version),
        user_blocks=(Block("constraints", constraints_block(segments)),),
        schema=AssetIntent,
        max_tokens=MAX_TOKENS, effort=effort, timeout_s=TIMEOUT_S,
    )
    spec = AgentSpec(name=AGENT, schema=AssetIntent,
                     expand=lambda p: check_intents_match(p, segments))
    return h.run(spec, req)

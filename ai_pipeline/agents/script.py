"""Agent 1 — التقسيم والإيقاع.

بيربط: prompt `script/v1` + `SegmentsProposal` + `expand_segments_proposal`.

**ما بينادي المزوّد.** بيبني `LLMRequest` وبيسلّمها للـharness، واللي
بيملك دورة الحياة كلها: فحص `stop_reason`، القراءة، التحقّق، الإصلاح
مرة وحدة، والفشل المقفول. وكيل بينادي `client.complete()` مباشرةً بيصير
مسار تاني بلا حواجز — وعليه حارس `ast`.

و`PromptRef` بيجي **من السجلّ**، مش مبنيًّا هون: البصمة هي الرابط
الوحيد بين عقد قديم والـprompt اللي أنتجه.
"""
from __future__ import annotations

from functools import partial

from ..models.segments import SegmentsContract
from .expand import expand_segments_proposal
from .prompts import prompt_ref, prompt_text
from .providers.base import Block, LLMClient, LLMRequest
from .runner import AgentHarness, AgentSpec
from .schemas import SegmentsProposal

AGENT = "script"
MAX_TOKENS = 8192
EFFORT = "high"
TIMEOUT_S = 120.0


def alignment_block(tokens: tuple[str, ...]) -> str:
    """`index<TAB>word` لكل كلمة. **الفهرس هو الطريقة الوحيدة للإشارة
    للنص** — فالوكيل بيقسم بلا ما يقدر يعيد كتابته."""
    return "\n".join(f"{i}\t{w}" for i, w in enumerate(tokens))


def run(client: LLMClient, script_text: str, tokens: tuple[str, ...], *,
        version: str = "v1", harness: AgentHarness | None = None,
        effort: str = EFFORT) -> SegmentsContract:
    h = harness or AgentHarness(client)
    req = LLMRequest(
        prompt=prompt_ref(AGENT, version),
        system=prompt_text(AGENT, version),
        user_blocks=(Block("source", script_text),
                     Block("alignment", alignment_block(tokens))),
        schema=SegmentsProposal,
        max_tokens=MAX_TOKENS, effort=effort, timeout_s=TIMEOUT_S,
    )
    spec = AgentSpec(name=AGENT, schema=SegmentsProposal,
                     expand=partial(expand_segments_proposal, tokens=tokens))
    return h.run(spec, req)

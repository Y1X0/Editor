"""Agent 3 — قرارات عرض النص، بمفردات مغلقة.

بيربط: prompt `typography/v1` + `TypographyProposal` +
`expand_typography_proposal`. وبيوصل لعقد Phase 1 كامل، لأن الـtheme
بيملك كل القيم اللي العقد بيحتاجها.

**قرار (ج) بينتنفّذ هون:** `<constraints>` بتقول للوكيل دور الخط اللي
الـtheme بيرسمه، والتوسعة بترفض أي دور مخالف بدل ما تسقطه بصمت. عقد
Phase 1 ما بيحمل خطًّا لكل مقطع، فالتمرير كان بيضيّع القرار.
"""
from __future__ import annotations

from ..models.segments import SegmentsContract
from ..models.typography import TypographyContract
from .expand import ThemeView, expand_typography_proposal
from .prompts import prompt_ref, prompt_text
from .providers.base import Block, LLMClient, LLMRequest
from .runner import AgentHarness, AgentSpec
from .schemas import TypographyProposal

AGENT = "typography"
MAX_TOKENS = 4096
EFFORT = "high"
TIMEOUT_S = 90.0


def constraints_block(segments: SegmentsContract, theme: ThemeView) -> str:
    """الـtheme + المقاطع + **عدد كلمات** كل مقطع.

    عدد الكلمات مش النص: بيكفّي ليقرّر `size_step`، وما بيمرّر حرفًا من
    المصدر لطبقة ما بتحتاجه.
    """
    lines = [
        f"theme: {theme.theme_id}",
        f"font_role: {theme.font_role}   (use this exact value)",
        f"base_font_size: {theme.base_font_size}",
        f"size_step_px: {theme.size_step_px}",
        f"color_roles: {', '.join(sorted(theme.color_hex))}",
        "",
        "segment_id\tword_count",
    ]
    lines += [f"{s.segment_id}\t{s.word_end - s.word_start}"
              for s in segments.segments]
    return "\n".join(lines)


def run(client: LLMClient, segments: SegmentsContract, theme: ThemeView, *,
        version: str = "v1", harness: AgentHarness | None = None,
        effort: str = EFFORT) -> TypographyContract:
    h = harness or AgentHarness(client)
    req = LLMRequest(
        prompt=prompt_ref(AGENT, version),
        system=prompt_text(AGENT, version),
        user_blocks=(Block("constraints", constraints_block(segments, theme)),),
        schema=TypographyProposal,
        max_tokens=MAX_TOKENS, effort=effort, timeout_s=TIMEOUT_S,
    )
    spec = AgentSpec(name=AGENT, schema=TypographyProposal,
                     expand=lambda p: expand_typography_proposal(p, theme))
    return h.run(spec, req)

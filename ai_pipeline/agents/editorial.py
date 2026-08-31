"""Agent 4 — النيّة التحريرية. **بيقول كيف ينقصّ، لا إيمتى.**

بيربط: prompt `editorial/v1` + `EditPlan` + `check_plan_covers`.

## ليش الـProposal هو `EditPlan` نفسه، بلا DTO وسيط

التلات وكلاء اللي قبله عندهن `XProposal` بينتوسّع لعقد Phase 1، لأن
العقد بيحمل قيمًا الوكيل ممنوع يكتبها (نصّ، مسار، بكسل، hex).
و`EditPlan` **ما بيحمل ولا وحدة منهن**: كل حقوله مفردات مغلقة أو
معرّفات، و`FORBIDDEN_FIELD_NAMES` بتفشل البناء لو انضاف حقل زمني أو
مسار. فطبقة وسيطة هون بتنسخ الحقول حقلًا حقلًا وبتصير **تعريفًا
ثانيًا** بيفترق بصمت — نفس الخطأ اللي `runner.py` موثّق فيه عن مسار
القراءة المزدوج.

يعني الحدّ محفوظ بمكان تاني: **`compile_plan` هي التوسعة.** هي اللي
بتحوّل الوزن النسبي لإطارات، وهي وحدها بتمرق على `quantize`.

## والموسّع هون تغطية، لا زمن

`check_plan_covers` بتفشل بالاتجاهين: مقطع بلا beat، وbeat بيشير
لمقطع مش موجود. هاد **قبل** أي حساب زمني — فخطة ناقصة بتفشل وهي خطة،
مش بتطلع timeline ناقصًا.
"""
from __future__ import annotations

from functools import partial

from ..edit.compiler import check_plan_covers
from ..edit.plan import EditPlan
from ..models.segments import SegmentsContract
from .prompts import prompt_ref, prompt_text
from .providers.base import Block, LLMClient, LLMRequest
from .runner import AgentHarness, AgentSpec

AGENT = "editorial"
MAX_TOKENS = 8192
EFFORT = "high"
TIMEOUT_S = 120.0


def constraints_block(segments: SegmentsContract) -> str:
    """`segment_id<TAB>word_count<TAB>visual_mood_prompt` لكل مقطع.

    **عدد الكلمات لا الكلمات.** `word_index` بالإبراز نسبي للمقطع،
    فالعدد بيكفّي ليشير لكلمة — وتمرير النصّ كان بيعطي الوكيل مادةً
    يقدر يعيد كتابتها، وهاد بالضبط اللي المشروع مقفّله.
    """
    lines = ["segment_id\tword_count\tvisual_mood_prompt"]
    lines += [f"{s.segment_id}\t{s.word_end - s.word_start}\t{s.visual_mood_prompt}"
              for s in segments.segments]
    return "\n".join(lines)


def _expand(plan: EditPlan, segments: SegmentsContract) -> EditPlan:
    check_plan_covers(plan, segments)
    return plan


def run(client: LLMClient, segments: SegmentsContract, *,
        version: str = "v1", harness: AgentHarness | None = None,
        effort: str = EFFORT) -> EditPlan:
    h = harness or AgentHarness(client)
    req = LLMRequest(
        prompt=prompt_ref(AGENT, version),
        system=prompt_text(AGENT, version),
        user_blocks=(Block("constraints", constraints_block(segments)),),
        schema=EditPlan,
        max_tokens=MAX_TOKENS, effort=effort, timeout_s=TIMEOUT_S,
    )
    spec = AgentSpec(name=AGENT, schema=EditPlan,
                     expand=partial(_expand, segments=segments))
    return h.run(spec, req)

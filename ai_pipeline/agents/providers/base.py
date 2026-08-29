"""عقد المزوّد — **بلا أي تطبيق**.

الترتيب مقصود: العقود أولًا، والـLLM آخرًا. لما تبني المزوّد بالآخر،
بيصير **تطبيقًا خلف واجهة**؛ ولو بنيته أولًا، بتلاقي شكل الـSDK تسرّب
لكل مكان وصار هو المعمارية.

ثلاث معاملات **ما إلهن مكان هون بقرار**، وهاد مقيس على `claude-opus-5`
مش احتياطًا:

  temperature      مرفوضة بـ400 — فما في «temperature=0».
                   **الحتمية بتجي من تثبيت العقد، لا من المُعايِن.**
  budget_tokens    مرفوض بـ400 — العمق بـ`effort`.
  prefill          مرفوض بـ400 — فحيلة «ابدأ الرد بـ{» ممنوعة،
                   والاعتماد على structured outputs إلزامي.

وعليها فحص بيقرا الحقول: `test_provider_contract.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel

Effort = Literal["low", "medium", "high", "xhigh", "max"]

#: أوسمة الكتل. `source` هي **الوحيدة** اللي بتحمل نصًّا غير موثوق،
#: والوسم بيخلّي التهريب مسؤولية معروفة المكان بدل ما تنتشر.
BlockTag = Literal["source", "alignment", "constraints", "repair"]


@dataclass(frozen=True)
class Block:
    """كتلة محتوى موسومة برسالة الـuser."""

    tag: BlockTag
    text: str


@dataclass(frozen=True)
class PromptRef:
    """إشارة لإصدار prompt منشور.

    `sha256` هو **الرابط الوحيد** بين عقد قديم والـprompt اللي أنتجه
    (`llm_prompt_version` مش موجود بالعقد بقرار مقفل). فبيلزمه شرطان
    بالـregistry: كل sha فريد، والإصدارات append-only — حذف إصدار
    منشور بيخلي عقودًا قديمة تشير لـsha ما إله مصدر.
    """

    agent: str
    version: str
    sha256: str


@dataclass(frozen=True)
class LLMRequest:
    prompt: PromptRef
    system: str
    user_blocks: tuple[Block, ...]
    schema: type[BaseModel]
    max_tokens: int
    effort: Effort
    timeout_s: float


@dataclass(frozen=True)
class LLMResponse:
    """الاستجابة الخام. **`parsed` ما بتنقرا قبل فحص `stop_reason`.**

    `refusal` بترجع HTTP 200 بجسم فاضي وبلا استثناء، و`max_tokens`
    بترجع JSON مقطوعًا بيبيّن سليمًا لحد ما تحاول تقراه. فقراءة
    `content` قبل الفحص بتخلّي الحالتين تمرقا كـ«جواب».
    """

    text: str
    stop_reason: str
    model: str
    parsed: BaseModel | None = None
    stop_details: dict | None = None
    request_id: str | None = None
    usage: dict = field(default_factory=dict)


class LLMClient(Protocol):
    """المزوّد. تطبيقاته الثلاثة بتيجي بcommits لاحقة:

    `RecordedClient` (fixtures، بلا شبكة) · `ScriptedFailureClient`
    (ضوابط سالبة) · `AnthropicClient` (آخر واحد، والاستيراد جوّا الدالة).
    """

    def complete(self, req: LLMRequest) -> LLMResponse: ...

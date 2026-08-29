"""مزوّد بيفشل على الطلب — للضوابط السالبة.

كل فشل بالمواصفة إله سلوك محدَّد، والفرق بينهن مش تجميليًا:

    ProviderError    ما وصلنا لجواب      (5xx · انقطاع · حدّ)
    TimeoutError     ما وصلنا بالوقت
    refusal          وصل جواب فاضي بـHTTP 200 — **بلا استثناء**
    max_tokens       وصل جواب **مقطوع** بيبيّن سليمًا
    استجابة فاضية    وصل نصّ فاضي

التلاتة الأخيرة أخطر من الأولين، لأنهن بينجحوا على مستوى النقل
وبيفشلوا على مستوى المعنى — فما بيرموا، ولازم `stop_reason` يمسكهن.
"""
from __future__ import annotations

from collections.abc import Sequence

from ...errors import ProviderError
from .base import LLMRequest, LLMResponse

#: عنصر السيناريو: استثناء بينرمى، أو استجابة بترجع.
Step = BaseException | LLMResponse


def refusal(category: str = "policy") -> LLMResponse:
    """رفض: HTTP 200، جسم فاضي، **ولا استثناء**."""
    return LLMResponse(
        text="", stop_reason="refusal", model="scripted",
        stop_details={"type": "refusal", "category": category,
                      "explanation": "scripted refusal"})


def truncated(text: str = '{"segments": [{"segment_id": 1, "word_st') -> LLMResponse:
    """مقطوع عند `max_tokens` — JSON ناقص بيبيّن بداية سليمة."""
    return LLMResponse(text=text, stop_reason="max_tokens", model="scripted")


def empty() -> LLMResponse:
    return LLMResponse(text="", stop_reason="end_turn", model="scripted")


def ok(text: str) -> LLMResponse:
    return LLMResponse(text=text, stop_reason="end_turn", model="scripted")


class ScriptedFailureClient:
    """بينفّذ سيناريو خطوة بخطوة. نفاد السيناريو **بيرمي**.

    السيناريو تسلسل عشان نقدر نفحص «فشل ثم نجاح» (سياسة الإصلاح) و
    «فشل ثم فشل» (نفاد المحاولات) بنفس الأداة.
    """

    def __init__(self, script: Sequence[Step]) -> None:
        if not script:
            raise ValueError("سيناريو فاضي — المزوّد ما بيخترع استجابة")
        self.script = tuple(script)
        self.calls: list[LLMRequest] = []

    def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls.append(req)
        i = len(self.calls) - 1
        if i >= len(self.script):
            raise ProviderError(
                f"نفد السيناريو عند النداء {i + 1} (المسجَّل "
                f"{len(self.script)}) — نداء زيادة عن المتوقَّع")
        step = self.script[i]
        if isinstance(step, BaseException):
            raise step
        return step

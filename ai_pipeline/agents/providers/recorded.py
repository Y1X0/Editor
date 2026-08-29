"""مزوّد بيعيد تشغيل استجابات مسجَّلة — **بلا شبكة وبلا مفتاح**.

هاد مصدر الاختبارات الطبيعية بالمشروع. الهدف مش «تسريع الطقم»، الهدف
إن سلوك الوكيل كله ينبني وينفحص **قبل** ما يندفع ولا request واحد
لمزوّد حقيقي: الاستجابة الغريبة اللي بتكسر المسار بتصير fixture ثابت
بدل حالة بتظهر مرة كل ألف نداء.

**ما بيفكّ ترميز شي.** `parsed` بتضل `None` دايمًا: القراءة والتحقّق
شغل الـharness، ومزوّد بيقرا بدل الـharness بيخلق مسارين — واحد
بالاختبارات وواحد بالإنتاج — وبيصير الفرق بينهن غير مفحوص. المزوّد
بينقل نصًّا، وبس.

الملفات ظروف (envelopes) بصيغة JSON دايمًا، حتى لما المحتوى المسجَّل
نفسه مش JSON: `text` بتحمل اللي «قاله» النموذج حرفيًا. صيغة وحدة
ومحمّل واحد.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Mapping

from pydantic import Field, ValidationError

from ...errors import ProviderError
from ...models.base import StrictModel
from .base import LLMRequest, LLMResponse


class RecordedResponse(StrictModel):
    """شكل ملف الـfixture. صارم بقصد: مفتاح مكتوب غلط بيفشل بدل ما
    ياخد افتراضيًا صامتًا ويخلّي الفحص يقيس غير اللي كاتبه."""

    text: str
    stop_reason: str = "end_turn"
    model: str = "recorded"
    request_id: str | None = "req_recorded"
    stop_details: dict | None = None
    usage: dict = Field(default_factory=dict)


class RecordedClient:
    """بيرجّع الـfixture المطابق لـ`(agent, prompt_version, case)`.

    `cases` بتقبل اسم حالة واحدة، أو **تسلسلًا** بيتقدّم مع كل نداء —
    والتسلسل ضروري لفحص «الإصلاح محاولة واحدة»: أول نداء بيرجّع
    مخرَجًا مكسورًا والثاني سليمًا.

    غياب fixture أو نفاد التسلسل **بيرمي**. المزوّد اللي بيرجّع
    افتراضيًا عند المفتاح المفقود بيخلّي الفحص يمرق وهو ما قاس شي.
    """

    def __init__(
        self,
        root: str | Path,
        cases: str | Sequence[str] | Mapping[str, str | Sequence[str]],
    ) -> None:
        self.root = Path(root)
        self._cases = cases
        self._cursor: dict[str, int] = {}
        self.calls: list[LLMRequest] = []

    # ── المفاتيح ─────────────────────────────────────────────────────
    @staticmethod
    def _key(req: LLMRequest) -> str:
        return f"{req.prompt.agent}_{req.prompt.version}"

    def _case_for(self, key: str) -> str:
        c = self._cases
        if isinstance(c, Mapping):
            if key not in c:
                raise ProviderError(
                    f"ما في حالة مسجَّلة للمفتاح {key!r} — "
                    f"المتوفّر: {sorted(c)}")
            c = c[key]
        if isinstance(c, str):
            return c
        i = self._cursor.get(key, 0)
        if i >= len(c):
            raise ProviderError(
                f"نفد تسلسل الحالات لـ{key!r} عند النداء {i + 1} "
                f"(المسجَّل {len(c)}) — المزوّد ما بيخترع استجابة")
        self._cursor[key] = i + 1
        return c[i]

    # ── التحميل ──────────────────────────────────────────────────────
    def _load(self, key: str, case: str) -> RecordedResponse:
        p = self.root / key / f"{case}.json"
        if not p.is_file():
            raise ProviderError(f"fixture مفقود: {p}")
        try:
            return RecordedResponse.model_validate_json(p.read_bytes())
        except ValidationError as e:
            first = e.errors()[0]
            loc = ".".join(str(x) for x in first["loc"]) or "(الجذر)"
            raise ProviderError(
                f"{p}: ظرف fixture غير صالح عند `{loc}`: {first['msg']}"
            ) from e
        except ValueError as e:
            raise ProviderError(f"{p}: JSON غير صالح — {e}") from e

    # ── الواجهة ──────────────────────────────────────────────────────
    def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls.append(req)
        key = self._key(req)
        rec = self._load(key, self._case_for(key))
        return LLMResponse(
            text=rec.text,
            stop_reason=rec.stop_reason,
            model=rec.model,
            parsed=None,              # ← القراءة شغل الـharness، مش المزوّد
            stop_details=rec.stop_details,
            request_id=rec.request_id,
            usage=dict(rec.usage),
        )

"""`AgentHarness` — دورة حياة المحاولة، وحدّ الفشل المقفل.

هون بيلتقي المزوّد بالعقود. المزوّد **بينقل** نصًّا؛ والـharness هو
اللي بيقرا، وبيتحقّق، وبيوسّع، وبيقرّر يفشل. فما في مسار قراءة تاني
بمكان تاني بيفترق عن هاد.

╔═══════════════════════════════════════════════════════════════════╗
║  الحواجز الأربعة المقفلة — تعديل أي واحد بيلزمه فتح المواصفة      ║
╠═══════════════════════════════════════════════════════════════════╣
║ ١· `extra="forbid"` على كل Proposal            (Commit 1)         ║
║ ٢· `stop_reason` بينفحص **قبل أي قراءة** لـ`text`                 ║
║ ٣· الإصلاح محاولة واحدة بالضبط — سقف نداءين                       ║
║ ٤· فشل الوكيل **ما بيشغّل** المقسِّم القاعدي — بيفشل مقفولًا      ║
╚═══════════════════════════════════════════════════════════════════╝

**الحاجز ٢ بالذات:** `refusal` بترجع HTTP 200 بجسم فاضي، و`max_tokens`
بترجع JSON مقطوعًا بيبيّن بداية سليمة. الاتنان ما بيرموا. فقراءة
`text` قبل الفحص بتخلّيهن يمرقوا كـ«جواب» — ولهيك الفحص أول شي
بالحلقة، وولا سطر قبله بيلمس المحتوى.

**والحاجز ٤ بالغياب:** ما في هون ولا كلمة عن مقسِّم قاعدي ولا احتياطي.
`run()` إما بترجّع عقدًا صالحًا أو **بترمي**. الهبوط الصامت أخطر من
الفشل: بتفتكر إنك مشغّل مسار AI وأنت لأ.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from ..errors import NurError, ProviderError
from ..errors import AgentError
from .providers.base import Block, LLMClient, LLMRequest, LLMResponse

#: سقف النداءات **لكل تشغيلة وكيل**، مهما كان مزيج الأسباب.
#: محاولة + إصلاح واحد. ولا ثالثة — لا للنقل ولا للتحقّق.
MAX_ATTEMPTS = 2

#: إصدار العقود المسجَّل بالسجلّ. مش بالعقد نفسه: `Provenance` ما إلها
#: `llm_prompt_version` بقرار مقفل، والربط بيصير sha -> version عبر
#: `registry.json`.
CONTRACT_VERSION = "1"

#: الحالة الوحيدة اللي بيُسمح بعدها بقراءة المحتوى.
ALLOWED_STOP = frozenset({"end_turn"})

#: سبب توقّف بيفشل **فورًا وبلا إعادة محاولة**.
#: `refusal` على نصّ ديني إشارة لازم يشوفها إنسان، مش شي نلفّ حوله
#: بصياغة أنعم. و`max_tokens` مخرَج مقطوع، مش مخرَجًا ناقصًا.
NO_RETRY_STOP = frozenset({"refusal", "max_tokens"})

#: مصرّف السجلّ. `None` = بالذاكرة فقط، فالفحوص ما بتلمس القرص.
Sink = Callable[[dict], None]


def jsonl_sink(path: str | Path) -> Sink:
    """بيلحق سطرًا لكل محاولة بـ`agent_runs.jsonl`. مصنع، مش إطار."""
    import json

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def write(record: dict) -> None:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return write


@dataclass(frozen=True)
class AgentSpec:
    """وكيل = اسم + schema + موسّع. الـharness ما بيعرف أي وكيل بعينه.

    `expand` بتاخد الـProposal وبترجّع عقد Phase 1 — والمستدعي بيربط
    مدخلاتها (الكلمات، الـtheme، الأصول المحلولة) بـ`partial`. هيك
    الـharness ما بيلمس شي من محتوى الوكلاء.
    """

    name: str
    schema: type[BaseModel]
    expand: Callable[[BaseModel], Any]


class AgentHarness:
    def __init__(self, client: LLMClient, *, sink: Sink | None = None,
                 clock: Callable[[], float] = time.perf_counter,
                 now: Callable[[], str] | None = None) -> None:
        self.client = client
        self.sink = sink
        self._clock = clock
        self._now = now or (lambda: datetime.now(timezone.utc)
                            .isoformat(timespec="milliseconds"))
        #: كل المحاولات، بالترتيب — بالذاكرة دايمًا حتى بلا sink.
        self.runs: list[dict] = []

    # ── السجلّ ───────────────────────────────────────────────────────
    def _log(self, req: LLMRequest, attempt: int, t0: float, *,
             stop_reason: str | None = None, resp: LLMResponse | None = None,
             validation: str = "ok", error: BaseException | None = None) -> None:
        """**بيانات وصفية فقط.**

        ولا `system`، ولا نصّ الـprompt، ولا محتوى الاستجابة، ولا أي
        متغيّر بيئة. السجلّ بيقول شو صار، مش شو انقال — فما بيقدر
        يسرّب سرًّا ولا نصًّا مصدريًا.
        """
        rec = {
            "ts": self._now(),
            "agent": req.prompt.agent,
            "prompt_version": req.prompt.version,
            "prompt_sha256": req.prompt.sha256,
            "provider": type(self.client).__name__,
            "model": resp.model if resp else None,
            "request_id": resp.request_id if resp else None,
            "effort": req.effort,
            "attempt": attempt,
            "stop_reason": stop_reason,
            "usage": dict(resp.usage) if resp else {},
            "validation": validation,
            "error_code": getattr(error, "code", None) if error else None,
            "error": str(error)[:300] if error else None,
            "contract_version": CONTRACT_VERSION,
            "duration_ms": round((self._clock() - t0) * 1000, 3),
        }
        self.runs.append(rec)
        if self.sink is not None:
            self.sink(rec)

    # ── الإصلاح: مرة وحدة ────────────────────────────────────────────
    @staticmethod
    def _with_repair(req: LLMRequest, err: BaseException) -> LLMRequest:
        note = (
            "مخرَجك السابق ما عبَر التحقّق. صلّحه وأعد إرساله كاملًا، "
            "بنفس الـschema وبلا أي حقل زيادة.\n"
            f"الخطأ:\n{str(err)[:1500]}"
        )
        return replace(req, user_blocks=(*req.user_blocks, Block("repair", note)))

    # ── التشغيل ──────────────────────────────────────────────────────
    def run(self, spec: AgentSpec, req: LLMRequest) -> Any:
        """بترجّع عقد Phase 1، أو **بترمي**. ما في نتيجة ثالثة."""
        if req.schema is not spec.schema:
            raise AgentError(
                f"الطلب بيحمل schema {req.schema.__name__} والوكيل "
                f"{spec.name} بيتوقّع {spec.schema.__name__}")

        # **رافعة واحدة للسقف.** كان `final` بينحسب من `MAX_ATTEMPTS`
        # بشكل مستقل عن حدّ الحلقة، فالسقف كان محروسًا بلَفتين — وطفرة
        # على واحدة منهن كانت بتمرق لأن التانية بتمسك. الاشتقاق من
        # `attempts` بيخلّي أي توسيع للحلقة يوسّع النهاية معه، فينكشف.
        attempts = range(1, MAX_ATTEMPTS + 1)
        last: BaseException | None = None
        for attempt in attempts:
            t0 = self._clock()
            final = attempt == attempts.stop - 1

            # ① النقل
            try:
                resp = self.client.complete(req)
            except (ProviderError, TimeoutError, ConnectionError) as e:
                self._log(req, attempt, t0, validation="provider_error", error=e)
                last = e
                if final:
                    raise ProviderError(
                        f"وكيل {spec.name}: نفدت المحاولات ({MAX_ATTEMPTS}) "
                        f"على فشل نقل — آخرها: {e}") from e
                continue

            # ② 🚨 الحاجز ٢ — قبل أي لمسة للمحتوى.
            #    ولا تنقل هالكتلة تحت ولا سطر: `refusal` و`max_tokens`
            #    بيرجعوا بنجاح على مستوى النقل، وقراءة `text` قبلهن
            #    بتخلّيهن يمرقوا كجواب.
            stop = resp.stop_reason
            if stop in NO_RETRY_STOP:
                cat = (resp.stop_details or {}).get("category")
                err = AgentError(
                    f"وكيل {spec.name}: توقّف بـ{stop!r}"
                    + (f" (تصنيف {cat!r})" if cat else "")
                    + " — بلا إعادة محاولة، وبلا استعمال أي محتوى جزئي.")
                self._log(req, attempt, t0, stop_reason=stop, resp=resp,
                          validation=f"stop_{stop}", error=err)
                raise err
            if stop not in ALLOWED_STOP:
                err = AgentError(
                    f"وكيل {spec.name}: سبب توقّف غير معروف {stop!r} — "
                    f"المسموح {sorted(ALLOWED_STOP)}")
                self._log(req, attempt, t0, stop_reason=stop, resp=resp,
                          validation="stop_unknown", error=err)
                raise err

            # ③ الآن فقط بينقرا المحتوى
            if not resp.text.strip():
                err = AgentError(
                    f"وكيل {spec.name}: استجابة فاضية بـ{stop!r} — ما في "
                    f"خطأ تحقّق نرجّعه، فما في شي نصلّحه.")
                self._log(req, attempt, t0, stop_reason=stop, resp=resp,
                          validation="empty", error=err)
                raise err

            # ④ القراءة + التحقّق + التوسعة (ومعها مدقّقات Phase 1/2)
            # التصنيف **بمكان الفشل، لا بنوع الاستثناء**: عقود Phase 1
            # بترمي `ValidationError` كمان، فمعرّف مكرّر أو تداخل — وهي
            # أخطاء دلالية مرقت الـschema — كانت بتنسجّل `schema_error`
            # وبتضلّل التشخيص.
            try:
                proposal = spec.schema.model_validate_json(resp.text)
            except (ValidationError, ValueError) as e:
                kind, err = "schema_error", e
            else:
                kind, err = None, None
                try:
                    result = spec.expand(proposal)
                except (ValidationError, ValueError, NurError) as e:
                    kind, err = "semantic_error", e

            if kind is not None:
                e = err
                self._log(req, attempt, t0, stop_reason=stop, resp=resp,
                          validation=kind, error=e)
                last = e
                if final:
                    raise AgentError(
                        f"وكيل {spec.name}: فشل التحقّق بعد إصلاح واحد "
                        f"({MAX_ATTEMPTS} محاولات) — {e}") from e
                req = self._with_repair(req, e)      # ← الإصلاح، مرة وحدة
                continue

            self._log(req, attempt, t0, stop_reason=stop, resp=resp)
            return result

        raise AgentError(f"وكيل {spec.name}: انتهت الحلقة بلا نتيجة")  # لا يُبلغ

"""مزوّد Anthropic — **الوحيد اللي بيلمس الشبكة، وآخر واحد انبنى**.

الترتيب مقصود: انبنت العقود، ثم التوسعة، ثم المزوّدان المحليان، ثم
الـharness وسياسة الفشل، ثم سجلّ الـprompts — وكلها مفحوصة بلا ولا
request. فهالملف **تطبيق خلف واجهة**، مش قلب المعمارية. شيله وبيضل
المسار كله مفحوصًا.

مسؤوليته ضيقة: يترجم `LLMRequest` لنداء، ويترجم الرد لـ`LLMResponse`.
**ما بيقرّر شي.** الرفض والقطع بيوصلوا كما هن، والـharness هو اللي
بيفشل مقفولًا.

ثلاثة معاملات ما إلهن مكان، مقيس على `claude-opus-5`:
  `temperature` · `budget_tokens` · assistant prefill — التلاتة بترجّع
  **400**. والحتمية أصلًا بتجي من تثبيت العقد، لأن الرندر ما بينادي
  LLM؛ فما في شي نخسره بغيابهن.

**ولا retry هون.** الـSDK بيعيد المحاولة على 429/5xx/408/الاتصال
(افتراضي ٢)، والـharness بيعطي محاولة خارجية وحدة. طبقة تالتة بتضرب
سقف المحاولتين اللي بالمواصفة.
"""
from __future__ import annotations

import os
from typing import Any

from ...errors import ProviderError
from .base import Block, LLMRequest, LLMResponse

#: المعرّف الكامل كما هو. **ولا لاحقة تاريخ.**
DEFAULT_MODEL = "claude-opus-5"

#: متغيّرات البيئة اللي ممكن تحمل سرًّا. بتنقرا **لغرض التنقية فقط**،
#: وقيمها ما بتنطبع ولا بتنسجّل ولا بتنحط برسالة خطأ.
_SECRET_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def _scrub(text: str) -> str:
    """بيشيل أي قيمة سرّية من نصّ قبل ما يطلع برسالة خطأ.

    رسالة استثناء بتمرق للسجلّات وللشاشة ولتقارير الأخطاء. مفتاح مسرَّب
    هناك بيضل مسرَّبًا حتى بعد ما تنسى إنك طبعته.
    """
    for name in _SECRET_ENV:
        val = os.environ.get(name)
        if val and len(val) >= 8 and val in text:
            text = text.replace(val, "***")
    return text


def _render(blocks: tuple[Block, ...]) -> str:
    """كتل موسومة -> نصّ رسالة الـuser.

    الوسم بيخلّي الـsource **محدَّدًا**، وأي وسم إغلاق مطابق جوّا
    المحتوى بينهرَّب: نصّ فيه `</source>` كان بيقدر يقفل الكتلة ويكتب
    اللي بعدها كأنه تعليمات.
    """
    out = []
    for b in blocks:
        body = b.text.replace(f"</{b.tag}>", f"<\\/{b.tag}>")
        out.append(f"<{b.tag}>\n{body}\n</{b.tag}>")
    return "\n\n".join(out)


def _schema_of(model: type) -> dict:
    s = model.model_json_schema()
    if s.get("additionalProperties") is not False:
        raise ProviderError(
            f"{model.__name__}: الـschema ما بتمنع الحقول الزيادة — "
            f"`extra=\"forbid\"` شرط للمخرَج المقيَّد")
    return s


def _details(resp: Any) -> dict | None:
    d = getattr(resp, "stop_details", None)
    if d is None:
        return None
    if isinstance(d, dict):
        return dict(d)
    return {k: getattr(d, k, None) for k in ("type", "category", "explanation")}


def _usage(resp: Any) -> dict:
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    if isinstance(u, dict):
        return dict(u)
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens",
            "cache_creation_input_tokens")
    return {k: v for k in keys if (v := getattr(u, k, None)) is not None}


class AnthropicClient:
    """`LLMClient` فوق `anthropic`. الاستيراد **داخل الدالة** بقصد:
    الحزمة بتنستورد وبتنفحص بلا الـSDK مثبَّتًا (`anthropic` تحت
    `[ai]` الاختيارية)، فالطقم بيشتغل بلا شبكة وبلا مفتاح."""

    def __init__(self, *, model: str = DEFAULT_MODEL,
                 sdk_factory: Any | None = None) -> None:
        self.model = model
        self._factory = sdk_factory

    def _sdk(self) -> Any:
        if self._factory is not None:
            return self._factory()
        try:
            import anthropic          # ← داخل الدالة. ما تنقله لفوق.
        except ModuleNotFoundError as e:
            raise ProviderError(
                "حزمة `anthropic` مش مثبَّتة. هي تبعية اختيارية: "
                "`pip install -e '.[ai]'`") from e
        # **ولا `api_key` هون.** الـSDK بيحلّها بالترتيب
        # ANTHROPIC_API_KEY -> ANTHROPIC_AUTH_TOKEN -> ملف الحساب.
        # تمريرها صراحةً بيكسر الترتيب وبيغري بتثبيتها بالكود.
        # و`max_retries` تبع الـSDK كما هو — ولا طبقة إعادة فوقه.
        return anthropic.Anthropic()

    def complete(self, req: LLMRequest) -> LLMResponse:
        sdk = self._sdk()
        kwargs = dict(
            model=self.model,
            max_tokens=req.max_tokens,
            # بادئة ثابتة قابلة للـcaching: التعليمات بس، ولا محتوى
            # متغيّر. المتغيّر كله بكتل الـuser.
            system=[{"type": "text", "text": req.system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _render(req.user_blocks)}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": req.effort,
                "format": {"type": "json_schema", "schema": _schema_of(req.schema)},
            },
        )
        try:
            resp = sdk.with_options(timeout=req.timeout_s).messages.create(**kwargs)
        except Exception as e:                      # noqa: BLE001 — بينلفّ ويُرمى
            raise ProviderError(
                _scrub(f"{type(e).__name__}: {e}")) from None

        # 🚨 `stop_reason` **قبل** أي لمسة للمحتوى. الترتيب مفحوص.
        stop = getattr(resp, "stop_reason", None)
        if stop is None:
            raise ProviderError("الرد بلا `stop_reason` — ما بينقدر ينتصنّف")
        details, usage = _details(resp), _usage(resp)
        model = getattr(resp, "model", self.model)
        rid = getattr(resp, "_request_id", None)

        text = ""
        for block in (getattr(resp, "content", None) or ()):
            if getattr(block, "type", None) == "text":
                text = block.text
                break

        return LLMResponse(
            text=text,
            stop_reason=stop,
            model=model,
            parsed=None,     # ← القراءة شغل الـharness. مسار واحد، مش اتنين.
            stop_details=details,
            request_id=rid,
            usage=usage,
        )

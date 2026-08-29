"""ما **يُسمح** للوكيل أن يقوله — ولا حرف أكثر.

هالملف هو الحدّ الأمني الأول بالمسار، وقوّته مش بشو بيرفض، بشو **ما
بيقدر يعبّر عنه**. كل حقل ناقص هون مقصود:

| ناقص عمدًا | لأن مالكه |
|---|---|
| `start` · `end` · `duration` | `alignment.json` ثم `quantize()` |
| `text_arabic` | النص المصدر — §19، ولا حرف بيتغيّر |
| `file_path` · `sha256` · `license` · `probe` | الـResolver |
| `provider_ref` وأي معرّف أصل | الـResolver — فالهلوسة ما إلها مكان |
| `font_path` · ألوان hex · `shaping_engine` | الـtheme، بمفردات مغلقة |

`extra="forbid"` بترجع من `StrictModel` تبع Phase 1 — **مصدر واحد
لسياسة الصرامة**، مش نسخة تانية بتفترق عنها بصمت. فمحاولة حقن حقل
(`"start": 0.0`، `"provider_ref": "px_8562341"`) بتفشل عند القراءة،
قبل ما توصل لأي مدقّق دلالي.

القراءة دايمًا بـ`model_validate_json`: بالوضع الصارم، مصفوفة JSON
بتصير tuple، و`"1"` مكان `1` بينرفض — والـLLM بيرجّع نصوصًا مكان أرقام.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..models.base import StrictModel

# ── مفردات مغلقة ─────────────────────────────────────────────────────
# أي قيمة برّا هالقوائم بتفشل بالـschema. التوسيع قرار يتعدّل هون،
# مش شي بيقترحه النموذج وقت التشغيل.
ShotType = Literal["wide", "medium", "macro", "aerial", "abstract"]
Palette = Literal["charcoal", "deep_blue", "warm_gold", "monochrome"]
Motion = Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"]
Animation = Literal["none", "fade", "fade_in_scale", "fade_in_up"]
FontRole = Literal["quranic", "body", "emphasis"]
ColorRole = Literal["primary", "muted", "accent"]

MAX_KEYWORDS = 5          # سقف must_include / must_avoid
SIZE_STEP_RANGE = 2       # size_step ∈ [-2, +2] حول حجم الـtheme


# ── Agent 1 — Script / Pacing ────────────────────────────────────────
class SegmentProposal(StrictModel):
    """مدى فهارس كلمات + نيّة بصرية. **ولا توقيت ولا نص.**

    الوكيل بيقرّر **وين** يقسم (قرار WHAT)، والكود بيحسب **إيمتى**
    (حساب HOW) من `alignment.json`. المدى نصف مفتوح `[word_start, word_end)`
    زي عقد Phase 1 بالضبط.
    """

    segment_id: int = Field(ge=1)
    word_start: int = Field(ge=0)
    word_end: int = Field(ge=1)
    visual_mood_prompt: str = Field(min_length=1, max_length=1000)


class SegmentsProposal(StrictModel):
    segments: tuple[SegmentProposal, ...] = Field(min_length=1)


# ── Agent 2 — Visual Asset Director ──────────────────────────────────
class AssetIntentItem(StrictModel):
    """**نيّة بحث، لا هوية أصل.**

    ولا حقل هون بيسمّي ملفًا ولا مزوّدًا ولا معرّفًا. الـResolver لحاله
    بيملأ `provider` · `provider_ref` · `file_path` · `sha256` ·
    `license` · `probe` · `in_point`.
    """

    segment_id: int = Field(ge=1)
    query: str = Field(min_length=1, max_length=300)
    must_include: tuple[str, ...] = Field(default=(), max_length=MAX_KEYWORDS)
    must_avoid: tuple[str, ...] = Field(default=(), max_length=MAX_KEYWORDS)
    shot_type: ShotType
    palette: Palette
    motion: Motion = "none"


class AssetIntent(StrictModel):
    intents: tuple[AssetIntentItem, ...] = Field(min_length=1)


# ── Agent 3 — Typography Director ────────────────────────────────────
class TypographySegmentProposal(StrictModel):
    """**أدوار، لا قيم.**

    `font_role` بيتحوّل لمسار عبر الـtheme، و`color_role` للون،
    و`size_step` لإزاحة عن حجم الـtheme. فمسار خط اعتباطي أو لون hex
    ما إلهن حقل — والقيمة الناتجة بتضل ضمن ما الـtheme بيسمح فيه.
    """

    segment_id: int = Field(ge=1)
    animation: Animation = "fade_in_scale"
    font_role: FontRole = "body"
    size_step: int = Field(0, ge=-SIZE_STEP_RANGE, le=SIZE_STEP_RANGE)
    color_role: ColorRole = "primary"


class TypographyProposal(StrictModel):
    segments: tuple[TypographySegmentProposal, ...] = Field(min_length=1)


#: كل ما يقرأه الـharness من نموذج. أي DTO جديد لازم ينضاف هون **بقصد**
#: — والفحوص بتمشي على هالقائمة، فالإضافة الصامتة بتضيع من التغطية.
PROPOSALS = (SegmentsProposal, AssetIntent, TypographyProposal)

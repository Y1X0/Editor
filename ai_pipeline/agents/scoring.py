"""ترجيح مرشّحي الأصل — **ثمانية حدود مستقلة، كل واحد بيتقاس لحاله**.

## ليش الانفصال هو التصميم كله

الترجيح القديم كان تعبيرًا واحدًا:

    4 × تقاطع الكلمات  +  3 × نفس shot_type  +  2 × نفس palette

اللي بيخلّي إعادته صعبة مش وزنه — هو إنه **ما بينقاس**. اختيار غلط
بيعطي رقمًا واحدًا، وما في طريقة تعرف أي جزء منه غلط. فلما بدك تعدّل
وزنًا، بتعدّله بالحدس وبتشغّل الطقم وبيضل أخضر لأن ولا فحص بيسأل عن
**حدّ** بعينه.

فالحدود هون **دوال نقية منفصلة**، كل وحدة بمدى معلَن `[0, 1]` (أو
`[-1, 0]` للعقوبات)، وكل وحدة عليها فحصها ومطفراتها. الجمع بالآخر
سطر واحد بيقرا `WEIGHTS`.

## ⚠️ وهاي **درجة اختيار**، لا حكمًا على المونتاج

المشروع بيمنع «الدرجة الإبداعية المجمّعة» (`visual_score = 82`) —
وعليها حارس AST بـ`ai_pipeline/edit/`. والمنع بمكانه: «٨٢» ما بتقول
للمحرّر شو يصلّح، والمخالفة بتقول.

هالملف **برّا ذاك الحدّ بقصد**، والفرق مش لفظيًّا:

  · الناقد بيحكم على **مخرَج موجود** — والحكم لازم يكون دليلًا
    قابلًا للتصليح، فبيطلع مخالفات.
  · الترجيح بيرتّب **مرشّحين لخانة وحدة** — والترتيب بيلزمه ترتيب
    كلّي، يعني رقم. ما في بديل: لازم تختار ملفًا واحدًا.

فالرقم هون **ما بينطلع للمستخدم ولا بينحفظ بعقد ولا بينذكر بتقرير**.
بيعيش داخل `choose` وبيموت عندها. وعليه حارس.

## والترحيل شرط لا نيّة

كتالوج بلا `analysis` لازم يعطي **نفس ترتيب اليوم بالضبط**. فكل حدّ
بيعتمد على التحليل بيرجّع `0.0` عند غيابه — لا قيمة مخترَعة ولا
افتراض متوسّط. وعليه فحص بيقارن الترتيبين على كتالوج حقيقي.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from .schemas import AssetIntentItem

if TYPE_CHECKING:                       # `resolver` بيستورد من هون
    from .resolver import CatalogEntry  # فالاستيراد الحقيقي بيعمل دورة

#: أوزان الحدود. **مكانها هون وحده** — حدّ بوزن مبعثر بالكود بيصير
#: غير قابل للتعديل بثقة.
WEIGHTS = {
    "semantic_match":     4.0,
    "shot_scale_fit":     3.0,
    "motion_affordance":  2.0,
    "composition_fit":    1.5,
    "duration_fit":       1.5,
    "continuity_bonus":   2.5,
    "repetition_penalty": 3.0,
    "recency_penalty":    1.0,
}

#: `ShotType` تبع النيّة ──► `ShotScale` تبع التحليل. الاتنان مفردتان
#: مغلقتان مختلفتان بقصد: النيّة بتوصف **الطلب**، والتحليل **اللقطة**.
SCALE_OF_SHOT = {
    "wide": "wide", "medium": "medium", "macro": "macro",
    "aerial": "extreme_wide", "abstract": None,
}

#: ترتيب المقاسات — المسافة بينهن هي العقوبة.
SCALE_ORDER = ("extreme_wide", "wide", "medium", "close", "macro")

#: حركة الكاميرا المطلوبة ──► مستوى الحركة اللي بيلائمها بالأصل.
#: **زوم على لقطة أصلًا سريعة بيعمل فوضى** — فالملاءمة عكسية.
MOTION_WANTS_CALM = {"zoom_in", "zoom_out", "pan_left", "pan_right"}


def _tokens(text: str) -> set[str]:
    return {t for t in "".join(
        c.lower() if c.isalnum() else " " for c in text).split() if t}


# ── ١ · دلالي ────────────────────────────────────────────────────────
def semantic_match(entry: "CatalogEntry", want: AssetIntentItem) -> float:
    """تقاطع كلمات النيّة مع كلمات الصفّ **و**وسومه الدلالية.

    مطبَّع على طول النيّة لا على عدد الكلمات المطابِقة: أصل بعشرين
    كلمة مفتاحية كان بيغلب أصلًا بكلمتين دقيقتين لمجرّد إنه أطول.
    """
    q = _tokens(want.query)
    if not q:
        return 0.0
    kw = {k.lower() for k in entry.keywords}
    if entry.analysis is not None:
        kw |= {t.lower() for t in entry.analysis.semantic_tags}
    return len(q & kw) / len(q)


# ── ٢ · مقاس اللقطة ──────────────────────────────────────────────────
def shot_scale_fit(entry: "CatalogEntry", want: AssetIntentItem) -> float:
    """قرب مقاس اللقطة الفعلي من المطلوب، على سلّم `SCALE_ORDER`.

    `abstract` ما إلها مقاس — بترجّع `0.0`، مش لأنها سيّئة بل لأن
    السؤال ما بينطبق. والغياب نفس الشي: **الترحيل بيلزمه صفرًا**.
    """
    want_scale = SCALE_OF_SHOT.get(want.shot_type)
    have = entry.analysis.shot_scale if entry.analysis else None
    if want_scale is None or have is None:
        return 0.0
    d = abs(SCALE_ORDER.index(want_scale) - SCALE_ORDER.index(have))
    return max(0.0, 1.0 - d / (len(SCALE_ORDER) - 1))


# ── ٣ · قابلية الحركة ────────────────────────────────────────────────
def motion_affordance(entry: "CatalogEntry", want: AssetIntentItem) -> float:
    """هل الأصل بيحتمل الحركة المطلوبة فوقه؟

    **زوم على لقطة أصلًا سريعة بيعمل فوضى**، ولقطة ساكنة بتحتمله كله.
    فلما النيّة بتطلب حركة، الملاءمة **عكسية** مع حركة الأصل. ولما
    ما بتطلب (`none`)، أي مستوى مقبول والحدّ بيسكت.
    """
    a = entry.analysis
    if a is None or a.action is None:
        return 0.0
    if want.motion not in MOTION_WANTS_CALM:
        return 0.0
    return {"static": 1.0, "slow": 0.7, "moderate": 0.3, "fast": 0.0}[a.action]


# ── ٤ · التأطير ──────────────────────────────────────────────────────
def composition_fit(entry: "CatalogEntry") -> float:
    """هل بالصورة مطرح للكابشن بلا ما يغطّي الموضوع؟

    الكابشن بينرسم بالشريط السفلي (`captions.y_ratio`)، فأصل موضوعه
    بالأسفل بيتحجب. **مستقلّ عن النيّة بقصد** — هاد حقيقة عن الأصل
    والتخطيط، لا عن اللقطة المطلوبة.
    """
    a = entry.analysis
    if a is None or a.safe_caption_area is None:
        return 0.0
    return {"bottom": 1.0, "none": 0.3, "top": 0.0}[a.safe_caption_area]


# ── ٥ · المدة ────────────────────────────────────────────────────────
def duration_fit(entry: "CatalogEntry", required_s: float) -> float:
    """أطول من المطلوب = مرونة بالـ`in_point`. لكن **بتشبع**.

    ملف ٦٠ ثانية مش أحسن من ملف ٢٠ لمقطع ٣ ثواني — الاتنان بيعطوا
    نفس الحرية. بلا الإشباع، الترجيح بيصير «اختار الأطول دايمًا».
    """
    if required_s <= 0:
        return 0.0
    ratio = entry.probe.duration / required_s
    if ratio < 1.0:
        return 0.0                       # الحاجز ٦ بيرفضه أصلًا
    return min(1.0, (ratio - 1.0) / 2.0)  # بيشبع عند ٣× المطلوب


# ── ٦ · الاستمرارية ──────────────────────────────────────────────────
def continuity_bonus(entry: "CatalogEntry", previous_ref: str | None) -> float:
    """نفس أصل اللقطة اللي قبلها — **لما تكون مطلوبة**.

    المستدعي بيمرّر `previous_ref` فقط لما الخطة بتطلب `continue`.
    فالحدّ ما بيقرّر متى الاستمرارية مرغوبة — بيقرّر إن هالمرشّح
    بيحقّقها.
    """
    if previous_ref is None:
        return 0.0
    return 1.0 if entry.provider_ref == previous_ref else 0.0


# ── ٧ · التكرار ──────────────────────────────────────────────────────
def repetition_penalty(entry: "CatalogEntry", used: Sequence[str]) -> float:
    """`-count² / 9`، مشبَّعة عند ١. التربيع من `edit/repetition.py`.

    **التربيع بقصد**: الاستعمال التاني مقبول، والرابع مش أربع مرات
    أسوأ — هو أسوأ بكتير. والقسمة على ٩ بتخلّي ٣ استعمالات = العقوبة
    الكاملة.
    """
    n = sum(1 for r in used if r == entry.provider_ref)
    if n == 0:
        return 0.0
    return -min(1.0, n ** 2 / 9.0)


# ── ٨ · القُرب ───────────────────────────────────────────────────────
def recency_penalty(entry: "CatalogEntry", used: Sequence[str]) -> float:
    """`-1 ÷ المسافة لآخر استعمال`. أصل رجع بعد بُعد أخفّ من أصل قريب.

    **منفصل عن `repetition_penalty` بقصد**، مع إنهما كانا حدًّا واحدًا
    بـ`edit/repetition.py`. الفصل لأنهما بيقيسا شيئين مختلفين: العدد
    بيقول «مستهلَك»، والمسافة بتقول «الجمهور لسا فاكره». أصل مستعمَل
    مرتين ببداية فيديو طويل مقبول؛ ومستعمَل مرة قبل لقطة وحدة لأ.
    """
    idx = [i for i, r in enumerate(used) if r == entry.provider_ref]
    if not idx:
        return 0.0
    return -1.0 / max(1, len(used) - idx[-1])


#: الحدود الثمانية بالترتيب — **مصدر واحد**، والفحوص بتمشي عليه.
TERMS = ("semantic_match", "shot_scale_fit", "motion_affordance",
         "composition_fit", "duration_fit", "continuity_bonus",
         "repetition_penalty", "recency_penalty")


def terms(entry: "CatalogEntry", want: AssetIntentItem, *,
          required_s: float = 0.0, previous_ref: str | None = None,
          used: Sequence[str] = ()) -> dict[str, float]:
    """كل حدّ بقيمته، **بلا جمع**.

    هاي الواجهة اللي بتخلّي «ليش انتخب هالأصل» سؤالًا إله جواب: بترجّع
    التفصيل، والجمع بيصير بمكان تاني. وقت التشخيص بتطبع القاموس
    وبتشوف أي حدّ رجّح الغلط.
    """
    return {
        "semantic_match":     semantic_match(entry, want),
        "shot_scale_fit":     shot_scale_fit(entry, want),
        "motion_affordance":  motion_affordance(entry, want),
        "composition_fit":    composition_fit(entry),
        "duration_fit":       duration_fit(entry, required_s),
        "continuity_bonus":   continuity_bonus(entry, previous_ref),
        "repetition_penalty": repetition_penalty(entry, used),
        "recency_penalty":    recency_penalty(entry, used),
    }


def combine(t: dict[str, float]) -> float:
    """`Σ wᵢ × termᵢ` — سطر واحد، وكل وزن من `WEIGHTS`."""
    return sum(WEIGHTS[k] * v for k, v in t.items())

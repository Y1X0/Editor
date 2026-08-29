"""Proposal ──► عقد Phase 1. **دوال نقية، وهون بيقع الحدّ.**

هالملف هو المكان اللي بيتحوّل فيه اقتراح نموذج لعقد بينبني عليه رندر.
وقوّته إنه **بيضيف اللي الوكيل ممنوع يقوله، من مصادره الصحيحة**:

    النص      ← `source.slice_text` على المصدر  (مش من الـProposal)
    التوقيت   ← ما بينتحدّد هون أصلًا — `Segment` بلا حقول زمنية
    هوية الأصل ← الـResolver، بتوصل **جاهزة** كمدخل
    الخط/اللون ← الـtheme

ولا نداء شبكة، ولا قراءة قرص، ولا ساعة، ولا عشوائية: نفس المدخلات
بتعطي نفس المخرَج بايت-بايت.

**ولا مدقّق جديد هون.** كل تحقّق بينتنادى من Phase 1/2 كما هو —
`SegmentsContract` للبنية، و`check_text_integrity` للسلامة،
و`check_coverage` للتغطية. إعادة كتابتهن هون بتعمل تعريفًا تانيًا
بيفترق بصمت.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..errors import AgentError
from ..models.assets import Asset, AssetsContract, Fit, Probe, SourceType
from ..models.segments import Segment, SegmentsContract
from ..models.typography import (
    StyleOverride, TypographyContract, TypographySegment,
)
from ..source import slice_text
from ..validation.semantic import check_coverage, check_text_integrity
from .schemas import (
    AssetIntent, ColorRole, FontRole, SegmentsProposal, TypographyProposal,
)


# ── إسقاط الـtheme اللي التوسعة بتحتاجه ──────────────────────────────
@dataclass(frozen=True)
class ThemeView:
    """القدر اللي التوسعة بتلزمها من الـtheme — لا أكثر.

    مؤقّتة هون بقصد: محمّل `themes/*.json` بيجي بمرحلة لاحقة وبيطلّع
    نفس الشكل. تعريفها الآن بملف تاني بيخلق واجهة قبل ما يكون إلها
    مستهلك تاني.
    """

    theme_id: str
    font_role: FontRole           # الدور الوحيد اللي هالـtheme بيرسمه
    base_font_size: int
    size_step_px: int
    color_hex: Mapping[ColorRole, str]
    max_lines: int
    fit: Fit = "cover"


@dataclass(frozen=True)
class ResolvedAsset:
    """حقائق الأصل كما سلّمها الـResolver. **التوسعة ما بتخترع ولا وحدة.**"""

    segment_id: int
    source_type: SourceType
    provider: str
    provider_ref: str
    file_path: Path
    sha256: str
    license: str
    probe: Probe
    in_point: float = 0.0
    attribution: str | None = None


def _ids(items, key="segment_id") -> list[int]:
    return [getattr(i, key) for i in items]


# ── Agent 1 ──────────────────────────────────────────────────────────
def expand_segments_proposal(
    proposal: SegmentsProposal, tokens: tuple[str, ...]
) -> SegmentsContract:
    """`SegmentsProposal` + كلمات المصدر ──► `SegmentsContract`.

    الفهارس بتيجي من الاقتراح؛ **النص بيتقصّ من المصدر**. فحتى لو
    الاقتراح جاي من نموذج مخترَق بالكامل، أسوأ ما بيقدر يعمله هو تقسيم
    رديء — مش تغيير حرف.

    `visual_mood_prompt` بينتقل كما هو: إله مكان مطابق بعقد Phase 1.

    الفحص بعد البناء: `check_text_integrity` (§19) و`check_coverage`
    (ولا كلمة بتنحذف بالسكوت). الاتنان من Phase 1/2، ما انتنسخوا هون.
    """
    n = len(tokens)
    segments = []
    for p in proposal.segments:
        # المدى المعكوس/الفاضي بيفشل عند `Segment` تبع Phase 1 كمان، بس
        # `slice_text` بتنفّذ قبلها وبترمي `ValueError` غير مصنَّف. الفحص
        # هون بيعطي رمزًا واضحًا، مش مدقّقًا جديدًا.
        if p.word_end <= p.word_start:
            raise AgentError(
                f"مقطع {p.segment_id}: مدى فاضي أو معكوس "
                f"[{p.word_start}, {p.word_end})")
        if p.word_end > n:
            raise AgentError(
                f"مقطع {p.segment_id}: مدى [{p.word_start}, {p.word_end}) "
                f"خارج نص من {n} كلمة")
        segments.append(Segment(
            segment_id=p.segment_id,
            word_start=p.word_start,
            word_end=p.word_end,
            # ⚠️ المصدر الوحيد للنص. لا تستبدلها بأي شي من `p`.
            text_arabic=slice_text(tokens, p.word_start, p.word_end),
            visual_mood_prompt=p.visual_mood_prompt,
        ))

    contract = SegmentsContract(segments=tuple(segments))   # بنية Phase 1
    check_text_integrity(contract, tokens)                  # §19
    check_coverage(contract, tokens)                        # ولا كلمة تضيع
    return contract


# ── Agent 2 ──────────────────────────────────────────────────────────
def expand_asset_intents(
    intent: AssetIntent,
    resolved: Mapping[int, ResolvedAsset],
    theme: ThemeView,
) -> AssetsContract:
    """`AssetIntent` + حقائق الـResolver ──► `AssetsContract`.

    **ولا resolver مصغّر هون.** الثمانية اللي بيملكها الـResolver
    (`provider` · `provider_ref` · `file_path` · `sha256` · `license` ·
    `probe` · `in_point` · `source_type`) بتوصل **جاهزة** بـ`resolved`،
    والتوسعة بتركّب بس.

    اللي بيمرق من الاقتراح للعقد **حقل واحد**: `motion`. الباقي
    (`query` · `must_include` · `must_avoid` · `shot_type` · `palette`)
    **مدخلات بحث للـResolver، مش حقول عقد** — وما إلهن مكان بـ
    `Asset` تبع Phase 1، وهاد صحيح مش نقص: العقد بيوصف الأصل المختار،
    مش كيف اخترناه.
    """
    want = set(_ids(intent.intents))
    have = set(resolved)
    if missing := sorted(want - have):
        raise AgentError(f"نيّات بلا أصل محلول: {missing}")
    if extra := sorted(have - want):
        raise AgentError(f"أصول محلولة بلا نيّة: {extra}")

    assets = []
    for it in intent.intents:
        r = resolved[it.segment_id]
        if r.segment_id != it.segment_id:
            raise AgentError(
                f"الأصل المحلول تحت المفتاح {it.segment_id} بيحمل "
                f"segment_id={r.segment_id}")
        assets.append(Asset(
            segment_id=it.segment_id,
            source_type=r.source_type, provider=r.provider,
            provider_ref=r.provider_ref, file_path=r.file_path,
            sha256=r.sha256, license=r.license, attribution=r.attribution,
            probe=r.probe, in_point=r.in_point,
            fit=theme.fit,          # الـtheme
            motion=it.motion,       # الاقتراح — الحقل الوحيد اللي بيمرق
        ))
    return AssetsContract(assets=tuple(assets))


# ── Agent 3 ──────────────────────────────────────────────────────────
def expand_typography_proposal(
    proposal: TypographyProposal, theme: ThemeView
) -> TypographyContract:
    """`TypographyProposal` + الـtheme ──► `TypographyContract`.

    التحويل حتمي بالكامل:

        size_step  ──► base_font_size + step × size_step_px
        color_role ──► theme.color_hex[role]        (hex من الـtheme)
        animation  ──► بيمرق كما هو (نفس المفردات المغلقة)

    ⚠️ **`font_role` ما إله مكان بعقد Phase 1.** `StyleOverride` فيها
    `font_size` و`text_color` و`max_lines` بس، وما في حقل خط لكل مقطع.
    فبدل ما نبلع القرار بصمت، بنرفض أي دور بيخالف دور الـtheme —
    إسقاط قرار الوكيل بلا أثر أسوأ من رفضه. شوف تقرير Commit 2.
    """
    lo, hi = 8, 400        # حدود `StyleOverride.font_size` تبع Phase 1
    segments, overrides = [], {}
    for p in proposal.segments:
        if p.font_role != theme.font_role:
            raise AgentError(
                f"مقطع {p.segment_id}: الوكيل اقترح font_role="
                f"{p.font_role!r} والـtheme {theme.theme_id!r} بيرسم "
                f"{theme.font_role!r}. عقد Phase 1 ما بيحمل خطًّا لكل "
                f"مقطع، فتمريره كان بيضيّع القرار بصمت.")

        size = theme.base_font_size + p.size_step * theme.size_step_px
        if not lo <= size <= hi:
            raise AgentError(
                f"مقطع {p.segment_id}: size_step={p.size_step:+d} بيعطي "
                f"حجمًا {size} برّا حدود العقد [{lo}, {hi}]")
        color = theme.color_hex.get(p.color_role)
        if color is None:
            raise AgentError(
                f"مقطع {p.segment_id}: الـtheme {theme.theme_id!r} ما "
                f"بيعرّف لونًا للدور {p.color_role!r}")

        segments.append(TypographySegment(
            segment_id=p.segment_id, animation=p.animation))
        overrides[p.segment_id] = StyleOverride(
            font_size=size, text_color=color, max_lines=theme.max_lines)

    return TypographyContract(
        theme=theme.theme_id, segments=tuple(segments), overrides=overrides)

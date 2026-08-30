"""من نيّة بحث لأصل مُتحقَّق منه. **كود حتمي، ولا نداء نموذج.**

الوكيل قال «slow motion rain on dark window». الـResolver هو اللي بيقول
**أي ملف**، وبأي بصمة، وبأي رخصة، ومن أي ثانية يبلّش. هالفصل هو الفرق
بين نظام بيتحقّق من أصوله ونظام بيصدّق ما بيقوله نموذج.

    AssetIntent ──► Catalog ──► فحص ──► ResolvedAsset ──► AssetsContract
                    (موثوق)     (٦ حواجز)

**الحواجز الستّة، وكلها fail closed:**

  ١· الاحتواء   المسار لازم يكون **جوّا** جذر الكتالوج. كتالوج مكسور
                بيقدر يمرّر أي ملف بالنظام لسلسلة الرندر.
  ٢· الوجود     الملف موجود وغير فاضٍ.
  ٣· البصمة     sha256(بايتات الملف) == المسجَّل. الاعتماد على الرقم
                المسجَّل لحاله بيخلّي ملفًا تبدّل يمرق ببصمته القديمة.
  ٤· الرخصة     موجودة وغير فاضية. «نكمّل ونشوف» بمحتوى بينتنشر مش خيارًا.
  ٥· الـprobe   أبعاد ومعدل ومدة صالحة.
  ٦· المدة      كافية للمطلوب. ولا تمديد صامت ولا قصّ صامت.

**المدة المطلوبة بتوصل كمُدخَل، ما بتنحسب هون.** السلطة عليها
`quantize`: نافذة المقطع البصرية بتمتد من القطع اللي قبله للقطع اللي
بعده، وهي **أطول** من نافذة نصّه. إعادة حسابها هون بتعمل تعريفًا تانيًا
بيفترق بصمت — والفحص بيعيد نفسه عند `quantize` على أي حال، بمرحلة تانية
من عمر البيانات.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

from pydantic import Field, ValidationError

from ..errors import AssetError, ContractError
from ..models.assets import AssetsContract, Probe, SourceType
from ..models.base import SHA256, StrictModel
from .expand import ResolvedAsset, ThemeView, expand_asset_intents
from .schemas import AssetIntent, AssetIntentItem, Palette, ShotType

#: هامش أمان فوق المدة المطلوبة، بالثواني. مش تجميلًا: `probe.duration`
#: مقرَّبة لجزء المئة، وحدّ المقطع بينحسب بالإطارات — فأصل بالضبط على
#: المقاس بيقدر ينقص إطارًا واحدًا عند التكميم.
DURATION_MARGIN_S = 0.10


class CatalogEntry(StrictModel):
    """صفّ بالكتالوج الموثوق.

    الكتالوج **محلي وحتمي** بهالمرحلة بقصد: خلط «كيف نختار أصلًا» مع
    «كيف نتصل بخدمة خارجية» بيخلّي فشل الاختيار وفشل الشبكة نفس العرَض.
    مزوّد حقيقي بيجي لاحقًا خلف نفس هالصفّ.
    """

    provider: str = Field(min_length=1)
    provider_ref: str = Field(min_length=1)
    path: str = Field(min_length=1)
    license: str = Field(min_length=1)
    sha256: SHA256
    probe: Probe
    keywords: tuple[str, ...] = ()
    shot_type: ShotType = "abstract"
    palette: Palette = "monochrome"
    attribution: str | None = None
    source_type: SourceType = "local"


class Catalog(StrictModel):
    entries: tuple[CatalogEntry, ...] = Field(min_length=1)


def load_catalog(path: str | Path) -> tuple[Catalog, Path]:
    """بيرجّع `(الكتالوج, جذره)`. الجذر مجلّد الملف، وكل مسار لازم يقع
    جوّاه."""
    p = Path(path)
    if not p.is_file():
        raise ContractError(f"كتالوج الأصول مفقود: {p}")
    try:
        return Catalog.model_validate_json(p.read_bytes()), p.parent.resolve()
    except ValidationError as e:
        first = e.errors()[0]
        loc = ".".join(str(x) for x in first["loc"]) or "(الجذر)"
        raise ContractError(
            f"{p}: كتالوج غير صالح عند `{loc}`: {first['msg']}") from e
    except ValueError as e:
        raise ContractError(f"{p}: JSON غير صالح — {e}") from e


# ── الاختيار: حتمي بالكامل ───────────────────────────────────────────
def _tokens(text: str) -> set[str]:
    return {t for t in "".join(
        c.lower() if c.isalnum() else " " for c in text).split() if t}


def score(entry: CatalogEntry, want: AssetIntentItem) -> int | None:
    """درجة المطابقة، أو `None` لو الصفّ مستبعَد.

    الاستبعاد قاطع: كلمة من `must_avoid` بتشيل الصفّ مهما كانت درجته —
    «تجنّب الوجوه» مش تفضيلًا بيتغلّب عليه تطابق نصّي.
    """
    kw = {k.lower() for k in entry.keywords}
    if kw & {a.lower() for a in want.must_avoid}:
        return None
    need = {m.lower() for m in want.must_include}
    if not need <= kw:
        return None
    overlap = _tokens(want.query) & kw
    # **دليل موضوعي مطلوب.** بلا هالشرط، أصل كلماته «desert, road» كان
    # بيطابق نيّة «rain» لمجرّد إن `shot_type` و`palette` بيتطابقوا —
    # يعني الـresolver بيرجّع أصلًا عشوائيًا بصمت وبيبيّن ناجحًا.
    # الأسلوب بيرجّح بين المرشّحين، وما بيصنع مرشّحًا.
    if not overlap and not need:
        return None
    pts = 4 * len(overlap)
    pts += 3 * (entry.shot_type == want.shot_type)
    pts += 2 * (entry.palette == want.palette)
    return pts


def choose(catalog: Catalog, want: AssetIntentItem) -> CatalogEntry:
    """أعلى درجة، وعند التعادل **أصغر `provider_ref` أبجديًا**.

    فكّ التعادل بالاسم مش بالترتيب داخل الملف: ترتيب الكتالوج بيتغيّر
    مع أي إضافة، والنتيجة كانت بتتغيّر معه بلا سبب.
    """
    ranked = [(s, e) for e in catalog.entries
              if (s := score(e, want)) is not None]
    if not ranked:
        raise AssetError(
            f"مقطع {want.segment_id}: ولا أصل بالكتالوج بيطابق "
            f"{want.query!r} (shot={want.shot_type}, palette={want.palette}, "
            f"لازم={list(want.must_include)}, ممنوع={list(want.must_avoid)})")
    best = max(s for s, _ in ranked)
    return min((e for s, e in ranked if s == best), key=lambda e: e.provider_ref)


# ── التحقّق: ستّ حواجز ───────────────────────────────────────────────
def verify(entry: CatalogEntry, root: Path, required_s: float,
           segment_id: int) -> Path:
    p = (root / entry.path).resolve()

    if not p.is_relative_to(root):                                   # 1
        raise AssetError(
            f"مقطع {segment_id}: مسار الأصل {entry.path!r} بيطلع برّا جذر "
            f"الكتالوج {root} — كتالوج مكسور بيقدر يمرّر أي ملف بالنظام")
    if not p.is_file():                                              # 2
        raise AssetError(f"مقطع {segment_id}: ملف الأصل مفقود — {p}")
    if p.stat().st_size == 0:
        raise AssetError(f"مقطع {segment_id}: ملف الأصل فاضي — {p}")
    actual = hashlib.sha256(p.read_bytes()).hexdigest()              # 3
    if actual != entry.sha256:
        raise AssetError(
            f"مقطع {segment_id}: بصمة الأصل ما بتطابق الكتالوج — الملف "
            f"تبدّل بعد التسجيل. المسجَّل {entry.sha256} والفعلي {actual} "
            f"({p})")
    if not entry.license.strip():                                    # 4
        raise AssetError(
            f"مقطع {segment_id}: الأصل {entry.provider_ref} بلا رخصة موثَّقة")
    if entry.probe.duration <= 0 or entry.probe.fps <= 0:            # 5
        raise AssetError(f"مقطع {segment_id}: probe غير صالح — {entry.probe}")
    need = required_s + DURATION_MARGIN_S                            # 6
    if entry.probe.duration < need:
        raise AssetError(
            f"مقطع {segment_id}: الأصل {entry.probe.duration:.3f}s والمطلوب "
            f"{required_s:.3f}s (+{DURATION_MARGIN_S}s هامش) — ولا تمديد "
            f"صامت ولا قصّ صامت")
    return p


def in_point_for(entry: CatalogEntry, required_s: float,
                 after: float | None = None) -> float:
    """نافذة بالأصل. **حساب من بيانات الأصل، مش قرار مخفي.**

    `after` = نهاية النافذة اللي أخذها المقطع السابق **من نفس الأصل**.
    لما تنمرَّر، النافذة بتكمّل من هناك بدل ما تتوسّط من جديد — فالقطع
    بين المقطعين بيصير **غير مرئي**: نفس اللقطة بتكمّل.

    وليش هاد مهمّ: قاعدة القطع بـ`quantize` بتقطع عند **كل** بداية نصّ،
    فالخلفية بتتبدّل مع كل جملة والإحساس بيصير مضطربًا. مقيس على فيديو
    مرجعي حقيقي: لقطة وحدة حملت **تلات جمل**، والقطع صار عند حدّ المعنى
    لا حدّ الجملة. الاستمرارية هون بتعطي نفس الأثر **بلا ما تلمس
    `quantize`** — القطع بيضل بالـtimeline، والعين ما بتشوفه.

    وبترجع للتوسيط لو الباقي ما بيكفّي، بدل ما تتجاوز نهاية الأصل.
    """
    if after is not None and after + required_s <= entry.probe.duration:
        return round(after, 3)
    return round(max(0.0, (entry.probe.duration - required_s) / 2), 3)


# ── الواجهة ──────────────────────────────────────────────────────────
def resolve_assets(intent: AssetIntent, required: Mapping[int, float],
                   catalog: Catalog, root: Path) -> dict[int, ResolvedAsset]:
    """`AssetIntent` + كتالوج ──► أصول مُتحقَّق منها."""
    out: dict[int, ResolvedAsset] = {}
    #: آخر أصل انختار وأين انتهت نافذته — للاستمرارية عبر مقاطع
    #: متتالية بنفس الأصل. **متتالية فقط**: أصل بيرجع بعد أصل غيره
    #: بيبلّش من جديد، لأن العين شافت قطعًا بينهما على أي حال.
    prev_ref: str | None = None
    prev_end: float = 0.0
    for want in intent.intents:
        if want.segment_id not in required:
            raise AssetError(
                f"مقطع {want.segment_id}: ما في مدة مطلوبة — "
                f"الـresolver ما بيخمّنها")
        need = required[want.segment_id]
        if need <= 0:
            raise AssetError(f"مقطع {want.segment_id}: مدة مطلوبة {need}")
        e = choose(catalog, want)
        p = verify(e, root, need, want.segment_id)
        after = prev_end if e.provider_ref == prev_ref else None
        start = in_point_for(e, need, after)
        out[want.segment_id] = ResolvedAsset(
            segment_id=want.segment_id, source_type=e.source_type,
            provider=e.provider, provider_ref=e.provider_ref, file_path=p,
            sha256=e.sha256, license=e.license, attribution=e.attribution,
            probe=e.probe, in_point=start)
        prev_ref, prev_end = e.provider_ref, start + need
    return out


def resolve(intent: AssetIntent, required: Mapping[int, float],
            catalog: Catalog, root: Path, theme: ThemeView) -> AssetsContract:
    """السلسلة كاملة: نيّة ──► أصول مُتحقَّقة ──► عقد Phase 1."""
    return expand_asset_intents(
        intent, resolve_assets(intent, required, catalog, root), theme)

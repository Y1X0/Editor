"""الحدود الثمانية — **كل واحد لحاله، وكل واحد بطفرته**.

الترجيح القديم كان تعبيرًا واحدًا: `4×تقاطع + 3×shot_type + 2×palette`.
اللي بيخلّيه صعب التعديل مش وزنه — هو إنه **ما بينقاس**: اختيار غلط
بيعطي رقمًا واحدًا وما في طريقة تعرف أي جزء غلط.

فهون كل حدّ بيتقاس لحاله، وبطرفين: قيمة عالية معروفة وقيمة دنيا
معروفة. وبالآخر **بوابة الترحيل**: كتالوج بلا تحليل وبلا سياق لازم
يعطي ترتيب اليوم بالحرف.
"""
import ast
import hashlib
import pathlib

import pytest

from ai_pipeline.agents import scoring
from ai_pipeline.agents.resolver import (
    AssetAnalysis, Catalog, CatalogEntry, choose, rank, score,
)
from ai_pipeline.agents.schemas import AssetIntentItem
from ai_pipeline.models.assets import Probe

Q = "slow motion rain on dark window"


def entry(ref="a", *, keywords=("rain", "night", "window"), shot_type="macro",
          palette="charcoal", duration=12.0, analysis=None):
    return CatalogEntry(
        provider="local", provider_ref=ref, path=f"{ref}.mp4", license="CC0",
        sha256=hashlib.sha256(ref.encode()).hexdigest(),
        probe=Probe(width=1920, height=1080, fps=25.0, duration=duration),
        keywords=keywords, shot_type=shot_type, palette=palette,
        analysis=analysis)


def want(**kw):
    d = {"segment_id": 1, "query": Q, "shot_type": "macro",
         "palette": "charcoal"}
    d.update(kw)
    return AssetIntentItem(**d)


# ══ ١ · semantic_match ══════════════════════════════════════════════
def test_semantic_match_rises_with_overlap():
    lo = scoring.semantic_match(entry(keywords=("rain",)), want())
    hi = scoring.semantic_match(entry(keywords=("rain", "window", "dark")), want())
    assert 0.0 < lo < hi <= 1.0


def test_semantic_match_is_normalised_by_the_intent_not_the_entry():
    """**أصل بعشرين كلمة ما بيغلب أصلًا بكلمتين دقيقتين لمجرّد إنه أطول.**

    بلا التطبيع، `len(q & kw)` بتكبر مع حجم الصفّ، فالكتالوج بيصير
    «اللي كلماته أكتر بيفوز» — وهاد ترجيح للحشو لا للدقّة.
    """
    precise = entry(keywords=("rain", "window"))
    padded = entry(keywords=("rain", "window") + tuple(f"x{i}" for i in range(30)))
    assert scoring.semantic_match(precise, want()) == \
           scoring.semantic_match(padded, want())


def test_semantic_match_reads_the_analysis_tags_too():
    plain = entry(keywords=("rain",))
    tagged = entry(keywords=("rain",),
                   analysis=AssetAnalysis(semantic_tags=("window", "dark")))
    assert scoring.semantic_match(tagged, want()) > \
           scoring.semantic_match(plain, want())


# ══ ٢ · shot_scale_fit ══════════════════════════════════════════════
def test_shot_scale_fit_peaks_on_the_exact_scale():
    exact = entry(analysis=AssetAnalysis(shot_scale="macro"))
    far = entry(analysis=AssetAnalysis(shot_scale="extreme_wide"))
    assert scoring.shot_scale_fit(exact, want(shot_type="macro")) == 1.0
    assert scoring.shot_scale_fit(far, want(shot_type="macro")) == 0.0


def test_shot_scale_fit_is_zero_when_the_question_does_not_apply():
    """`abstract` ما إلها مقاس، والغياب كمان — **صفر لا تخمين**."""
    a = entry(analysis=AssetAnalysis(shot_scale="macro"))
    assert scoring.shot_scale_fit(a, want(shot_type="abstract")) == 0.0
    assert scoring.shot_scale_fit(entry(), want(shot_type="macro")) == 0.0


# ══ ٣ · motion_affordance ═══════════════════════════════════════════
def test_motion_affordance_prefers_calm_footage_for_a_zoom():
    """**زوم على لقطة أصلًا سريعة بيعمل فوضى** — فالملاءمة عكسية."""
    calm = entry(analysis=AssetAnalysis(action="static"))
    busy = entry(analysis=AssetAnalysis(action="fast"))
    assert scoring.motion_affordance(calm, want(motion="zoom_in")) == 1.0
    assert scoring.motion_affordance(busy, want(motion="zoom_in")) == 0.0


def test_motion_affordance_is_silent_when_no_motion_is_asked_for():
    """بلا حركة مطلوبة، أي مستوى مقبول — الحدّ ما بيرجّح بلا سبب."""
    calm = entry(analysis=AssetAnalysis(action="static"))
    assert scoring.motion_affordance(calm, want(motion="none")) == 0.0


# ══ ٤ · composition_fit ═════════════════════════════════════════════
def test_composition_fit_ranks_the_caption_band():
    """الكابشن بينرسم بالأسفل، فموضوع بالأسفل بيتحجب."""
    good = entry(analysis=AssetAnalysis(safe_caption_area="bottom"))
    bad = entry(analysis=AssetAnalysis(safe_caption_area="top"))
    assert scoring.composition_fit(good) > scoring.composition_fit(bad)
    assert scoring.composition_fit(bad) == 0.0
    assert scoring.composition_fit(entry()) == 0.0


# ══ ٥ · duration_fit ════════════════════════════════════════════════
def test_duration_fit_saturates_instead_of_preferring_the_longest():
    """**ملف ٦٠ ثانية مش أحسن من ٢٠ لمقطع ٣ ثواني.**

    بلا الإشباع، الترجيح بيصير «اختار الأطول دايمًا» — وهاد بيغلب
    التطابق الدلالي على كتالوج فيه ملف طويل واحد.
    """
    assert scoring.duration_fit(entry(duration=20.0), 3.0) == \
           scoring.duration_fit(entry(duration=60.0), 3.0) == 1.0
    assert scoring.duration_fit(entry(duration=3.5), 3.0) < 1.0
    assert scoring.duration_fit(entry(duration=2.0), 3.0) == 0.0


def test_duration_fit_is_zero_without_a_required_duration():
    """بوابة الترحيل بتعتمد عليها: بلا سياق، الحدّ صامت."""
    assert scoring.duration_fit(entry(duration=60.0), 0.0) == 0.0


# ══ ٦ · continuity_bonus ════════════════════════════════════════════
def test_continuity_bonus_only_when_asked_for():
    """الحدّ ما بيقرّر **متى** الاستمرارية مرغوبة — بس إن المرشّح بيحقّقها."""
    assert scoring.continuity_bonus(entry("a"), "a") == 1.0
    assert scoring.continuity_bonus(entry("b"), "a") == 0.0
    assert scoring.continuity_bonus(entry("a"), None) == 0.0


# ══ ٧ · repetition_penalty ══════════════════════════════════════════
def test_repetition_penalty_grows_faster_than_linearly():
    """**الرابع مش أربع مرات أسوأ — هو أسوأ بكتير.**

    الفحص على النسبة لا على القيمة: خطّي بيعطي 2×، والتربيع 4×.
    """
    one = -scoring.repetition_penalty(entry("a"), ["a"])
    two = -scoring.repetition_penalty(entry("a"), ["a", "a"])
    assert one > 0 and two / one > 2.0


def test_repetition_penalty_is_zero_for_an_unused_asset():
    assert scoring.repetition_penalty(entry("a"), ["b", "c"]) == 0.0


# ══ ٨ · recency_penalty ═════════════════════════════════════════════
def test_recency_penalty_forgives_distance():
    """أصل رجع بعد بُعد أخفّ من أصل قريب — والعدد نفسه بالحالتين."""
    near = -scoring.recency_penalty(entry("a"), ["a"])
    far = -scoring.recency_penalty(entry("a"), ["a", "b", "c", "d"])
    assert near > far > 0


def test_recency_is_a_separate_axis_from_repetition():
    """**العدد بيقول «مستهلَك»، والمسافة بتقول «الجمهور لسا فاكره».**

    نفس العدد ومسافتان مختلفتان: `repetition` ما بتتغيّر و`recency`
    بتتغيّر. لو الاتنان حدًّا واحدًا، الفحص هاد بيفشل.
    """
    a, b = ["a"], ["a", "b", "c"]
    assert scoring.repetition_penalty(entry("a"), a) == \
           scoring.repetition_penalty(entry("a"), b)
    assert scoring.recency_penalty(entry("a"), a) != \
           scoring.recency_penalty(entry("a"), b)


# ══ التركيب ═════════════════════════════════════════════════════════
def test_every_term_has_a_weight_and_every_weight_a_term():
    """وزن بلا حدّ ميت، وحدّ بلا وزن **بينضاف للمجموع بصمت**."""
    assert set(scoring.WEIGHTS) == set(scoring.TERMS)
    assert set(scoring.terms(entry(), want())) == set(scoring.TERMS)


def test_each_term_moves_the_total_on_its_own():
    """**ولا حدّ ميت.** كل واحد لحاله لازم يغيّر المجموع.

    هاد الفحص اللي بيمسك الحدّ اللي انكتب وانحسب وما إله أثر — أكتر
    شكل بيمرق بطقم أخضر.
    """
    base = {k: 0.0 for k in scoring.TERMS}
    zero = scoring.combine(base)
    for k in scoring.TERMS:
        one = dict(base, **{k: 1.0})
        assert scoring.combine(one) != zero, f"حدّ بلا أثر: {k}"


# ══ بوابة الترحيل ═══════════════════════════════════════════════════
def test_the_eligible_set_is_exactly_what_it_was():
    """**شرط الترحيل الحقيقي — وهو أضيق مما كتبته أول مرة.**

    كتبت الفحص أول مرة على «`rank == score` بالضبط»، وفشل: `9.67`
    مقابل `9`. والكود كان صح، الادّعاء غلط — `semantic_match` بيقرا
    `keywords` لا `analysis`، فهو شغّال حتى على كتالوج قديم، **بقصد**:
    هو اللي بيصلّح ترجيح الحشو (فحص `_normalised_by_the_intent`).

    فالضمان مش «نفس الترتيب» — هو **نفس المجموعة المؤهَّلة**. الأهلية
    بيقرّرها `score is None` وحده (`must_avoid` · `must_include` ·
    شرط الدليل الموضوعي)، وهاد ما انلمس. الترتيب **داخل** المجموعة
    بيتحسّن، وهاد الغرض من المرحلة.
    """
    cands = [entry("a", keywords=("rain",)),
             entry("b", keywords=("rain", "window")),
             entry("c", keywords=("rain", "window", "dark"), palette="deep_blue"),
             entry("d", keywords=("storm",), shot_type="wide"),
             entry("e", keywords=("faces", "crowd"))]
    w = want()
    old_ok = {e.provider_ref for e in cands if score(e, w) is not None}
    new_ok = {e.provider_ref for e in cands if rank(e, w) is not None}
    assert old_ok == new_ok
    assert "d" not in old_ok and "e" not in old_ok      # المجموعة مش الكل


def test_only_the_keyword_term_is_alive_on_an_old_catalog():
    """وأي حدّ تاني بيشتغل بلا `analysis` بيكون **ترقية صامتة**.

    الفحص بيعدّ الحدود غير الصفرية على صفّ بلا تحليل وبلا سياق. لو
    صار عددها اتنين، حدّ جديد بدأ يغيّر اختيارات كتالوج قديم بلا ما
    حدا يطلب — والفحص بيسمّيه.
    """
    live = {k: v for k, v in scoring.terms(entry(), want()).items() if v}
    assert set(live) == {"semantic_match"}, f"حدود حيّة غير متوقَّعة: {sorted(live)}"


def test_the_exclusions_stay_absolute_and_are_never_outscored():
    """**`must_avoid` قاطع، لا حدّ ترجيح.**

    أصل بكل الحدود على أعلاها لازم يضل `None` لو حمل كلمة ممنوعة —
    وإلا رقم كبير بيشتري مخالفة، وهاد بالضبط الخلط اللي
    `edit/repetition.py` بيفصله بين العقوبة والحارس.
    """
    perfect = entry("a", keywords=("rain", "window", "dark", "faces"),
                    analysis=AssetAnalysis(shot_scale="macro", action="static",
                                           safe_caption_area="bottom"))
    w = want(must_avoid=("faces",), motion="zoom_in")
    assert rank(perfect, w, required_s=3.0) is None


# ══ الحدّ: الدرجة ما بتطلع ══════════════════════════════════════════
def test_repetition_actually_changes_the_pick_once_context_flows():
    """**الوصلة شغّالة فعلًا.** بلا سياق الحدود ميتة والوصلة بتبيّن
    قائمة وهي ما بتعمل شي — فالفحص على تغيّر **الاختيار**، لا على
    وجود الدالة."""
    cat = Catalog(entries=(entry("a", keywords=("rain", "window")),
                           entry("b", keywords=("rain", "window"))))
    w = want()
    assert choose(cat, w).provider_ref == "a"          # تعادل -> الأبجدي
    assert choose(cat, w, used=["a", "a"]).provider_ref == "b"


def test_the_selection_score_never_leaves_choose():
    """**درجة اختيار، لا حكمًا على المونتاج.**

    المشروع بيمنع الدرجة الإبداعية المجمّعة. الترجيح استثناء ضروري
    (اختيار ملف واحد بيلزمه ترتيب كلّي)، وحدّه إن الرقم **ما بيطلع**:
    ولا `return` من `resolve_assets` بيحمله، وولا عقد بيخزّنه.
    """
    src = pathlib.Path("ai_pipeline/agents/resolver.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "choose")
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    for r in returns:
        assert not isinstance(r.value, ast.Tuple), \
            "choose بترجّع tuple — الدرجة بتطلع معها"

    contracts = pathlib.Path("ai_pipeline/models").rglob("*.py")
    for f in contracts:
        t = f.read_text(encoding="utf-8")
        for bad in ("score", "rank", "visual_score"):
            assert f"{bad}:" not in t, f"{f.name}: العقد بيخزّن درجة"


# ══ الوصلة الحقيقية — عبر `resolve_assets` لا `choose` ══════════════
def test_repetition_changes_the_pick_through_the_production_path(tmp_path):
    """**طفرتان نجتا لولا هالفحص.**

    أول فحص للتكرار كان بينادي `choose` مباشرةً بـ`used=[...]`، فطفرة
    بتشيل تمرير السياق من `resolve_assets` — وطفرة بتشيل
    `used.append` — **مرقتا الاتنتان**: الدالة صحيحة، والمستدعي ما
    بيمرّرها شي.

    فالفحص لازم يمرق من المسار اللي المنتَج بيمشي فيه: نيّتان
    متطابقتان على كتالوج فيه مرشّحان متعادلان. بلا عقوبة التكرار
    الاتنان بياخدوا `a` (فكّ التعادل الأبجدي)؛ معها التانية بتاخد `b`.
    """
    from ai_pipeline.agents.resolver import resolve_assets
    from ai_pipeline.agents.schemas import AssetIntent

    def on_disk(ref):
        body = f"BYTES-{ref}".encode()
        (tmp_path / f"{ref}.mp4").write_bytes(body)
        return CatalogEntry(
            provider="local", provider_ref=ref, path=f"{ref}.mp4",
            license="CC0", sha256=hashlib.sha256(body).hexdigest(),
            probe=Probe(width=1920, height=1080, fps=25.0, duration=12.0),
            keywords=("rain", "window"), shot_type="macro",
            palette="charcoal")

    cat = Catalog(entries=(on_disk("a"), on_disk("b")))
    intents = AssetIntent(intents=(want(segment_id=1), want(segment_id=2)))
    got = resolve_assets(intents, {1: 3.0, 2: 3.0}, cat, tmp_path)
    assert got[1].provider_ref == "a"
    assert got[2].provider_ref == "b", \
        "التانية أخذت نفس الأصل — السياق مش واصل لـ`choose`"

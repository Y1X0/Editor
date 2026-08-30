"""الـResolver — الحدّ اللي بيمنع النموذج يختار الملف.

الوكيل بيقول شو يدوّر عليه؛ الـResolver بيقول **أي ملف**، وبيثبت
بصمته ورخصته ومدته. كل فحص هون بيثبت واحدة من الستّة، أو بيثبت إن
النيّة **ما بتقدر** تحمل هوية أصل أصلًا.
"""
import hashlib
import json
import pathlib

import pytest
from pydantic import ValidationError

from ai_pipeline.agents.expand import ThemeView
from ai_pipeline.agents.resolver import (
    DURATION_MARGIN_S, Catalog, CatalogEntry, choose, in_point_for,
    load_catalog, resolve, resolve_assets, score,
)
from ai_pipeline.agents.schemas import AssetIntent, AssetIntentItem
from ai_pipeline.errors import AssetError, ContractError
from ai_pipeline.models.assets import AssetsContract, Probe

THEME = ThemeView(theme_id="t", font_role="body", base_font_size=64,
                  size_step_px=6, max_lines=2, color_hex={"primary": "#FFFFFF"})
NEED = {1: 3.0}


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def entry(root, name="rain.mp4", body=b"RAIN-BYTES", **kw):
    (root / name).write_bytes(body)
    d = dict(provider="local", provider_ref=f"cat_{name}", path=name,
             license="CC0", sha256=digest(body),
             probe=Probe(width=3840, height=2160, fps=25.0, duration=12.0),
             keywords=("rain", "night", "window"), shot_type="macro",
             palette="charcoal")
    d.update(kw)
    return CatalogEntry(**d)


def catalog(*entries):
    return Catalog(entries=tuple(entries))


def intent(**kw):
    d = {"segment_id": 1, "query": "slow motion rain on dark window",
         "shot_type": "macro", "palette": "charcoal"}
    d.update(kw)
    return AssetIntent.model_validate_json(json.dumps({"intents": [d]}))


@pytest.fixture
def root(tmp_path):
    return tmp_path


# ══ الحالة السليمة ══════════════════════════════════════════════════
def test_a_matching_asset_resolves(root):
    got = resolve_assets(intent(), NEED, catalog(entry(root)), root)[1]
    assert got.provider_ref == "cat_rain.mp4"
    assert got.license == "CC0" and got.file_path == (root / "rain.mp4")
    assert got.sha256 == digest(b"RAIN-BYTES")


def test_resolve_produces_a_phase_one_contract(root):
    out = resolve(intent(), NEED, catalog(entry(root)), root, THEME)
    assert isinstance(out, AssetsContract) and len(out.assets) == 1
    a = out.assets[0]
    assert a.fit == THEME.fit and a.motion == "none"


def test_the_motion_still_comes_from_the_intent(root):
    out = resolve(intent(motion="zoom_in"), NEED, catalog(entry(root)),
                  root, THEME)
    assert out.assets[0].motion == "zoom_in"


# ══ ١· النيّة ما بتقدر تحمل هوية أصل ═══════════════════════════════
@pytest.mark.parametrize("field,value", [
    ("provider_ref", "px_8562341"), ("provider", "pexels"),
    ("file_path", "/etc/passwd"), ("sha256", "a" * 64),
    ("license", "CC0"), ("url", "https://x/y.mp4")])
def test_asset_identity_cannot_be_expressed_in_an_intent(field, value):
    """مش «بينرفض» — **ما إله حقل**. الرفض بيصير عند القراءة."""
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        intent(**{field: value})


def test_the_provider_ref_is_generated_by_the_catalog_not_the_model(root):
    e = entry(root, provider_ref="TRUSTED-REF")
    assert resolve_assets(intent(), NEED, catalog(e), root)[1].provider_ref \
        == "TRUSTED-REF"


# ══ ٢· ولا مطابقة ═══════════════════════════════════════════════════
def test_no_matching_asset_fails(root):
    e = entry(root, keywords=("desert", "road"))
    with pytest.raises(AssetError, match="ولا أصل بالكتالوج بيطابق"):
        resolve_assets(intent(), NEED, catalog(e), root)


def test_must_avoid_removes_a_candidate_however_good(root):
    """الاستبعاد قاطع، مش تفضيلًا بيتغلّب عليه تطابق نصّي."""
    e = entry(root, keywords=("rain", "night", "window", "people"))
    assert score(e, intent().intents[0]) is not None
    with pytest.raises(AssetError, match="ولا أصل"):
        resolve_assets(intent(must_avoid=["people"]), NEED, catalog(e), root)


def test_must_include_is_required(root):
    e = entry(root, keywords=("rain",))
    with pytest.raises(AssetError, match="ولا أصل"):
        resolve_assets(intent(must_include=["thunder"]), NEED, catalog(e), root)


# ══ ٣-٨· الحواجز الستّة ═════════════════════════════════════════════
def test_a_path_escaping_the_catalog_root_fails(root):
    (root.parent / "outside.mp4").write_bytes(b"X")
    e = entry(root, name="rain.mp4")
    e = e.model_copy(update={"path": "../outside.mp4",
                             "sha256": digest(b"X")})
    with pytest.raises(AssetError, match="برّا جذر الكتالوج"):
        resolve_assets(intent(), NEED, catalog(e), root)


def test_an_absolute_path_outside_the_root_fails(root, tmp_path_factory):
    other = tmp_path_factory.mktemp("elsewhere") / "x.mp4"
    other.write_bytes(b"X")
    e = entry(root).model_copy(update={"path": str(other),
                                       "sha256": digest(b"X")})
    with pytest.raises(AssetError, match="برّا جذر الكتالوج"):
        resolve_assets(intent(), NEED, catalog(e), root)


def test_a_missing_file_fails(root):
    e = entry(root)
    (root / "rain.mp4").unlink()
    with pytest.raises(AssetError, match="ملف الأصل مفقود"):
        resolve_assets(intent(), NEED, catalog(e), root)


def test_an_empty_file_fails(root):
    e = entry(root, body=b"")
    with pytest.raises(AssetError, match="فاضي"):
        resolve_assets(intent(), NEED, catalog(e), root)


def test_a_file_changed_after_registration_fails(root):
    """الاعتماد على الرقم المسجَّل لحاله بيخلّي ملفًا تبدّل يمرق."""
    e = entry(root)
    resolve_assets(intent(), NEED, catalog(e), root)          # سليم
    (root / "rain.mp4").write_bytes(b"DIFFERENT-BYTES")
    with pytest.raises(AssetError, match="الملف تبدّل بعد التسجيل"):
        resolve_assets(intent(), NEED, catalog(e), root)


def test_a_forged_sha_in_the_catalog_fails(root):
    e = entry(root).model_copy(update={"sha256": "b" * 64})
    with pytest.raises(AssetError, match="ما بتطابق الكتالوج"):
        resolve_assets(intent(), NEED, catalog(e), root)


def test_a_missing_license_is_rejected_by_the_catalog_schema(root):
    with pytest.raises(ValidationError):
        entry(root, license="")


def test_a_whitespace_license_fails_at_verification(root):
    e = entry(root, license="   ")
    with pytest.raises(AssetError, match="بلا رخصة موثَّقة"):
        resolve_assets(intent(), NEED, catalog(e), root)


@pytest.mark.parametrize("bad", [{"duration": 0.0}, {"fps": 0.0}])
def test_an_invalid_probe_is_rejected(root, bad):
    with pytest.raises(ValidationError):
        Probe(width=1920, height=1080, **{"fps": 25.0, "duration": 12.0, **bad})


def test_a_probe_that_passes_the_schema_but_not_the_guard(root):
    """`Probe` بترفض الصفر؛ الحارس بيمسك أي قيمة بتمرق لاحقًا."""
    e = entry(root, probe=Probe(width=16, height=16, fps=0.001, duration=0.001))
    with pytest.raises(AssetError, match="والمطلوب|probe غير صالح"):
        resolve_assets(intent(), NEED, catalog(e), root)


def test_an_asset_shorter_than_required_fails(root):
    e = entry(root, probe=Probe(width=1920, height=1080, fps=25.0, duration=2.5))
    with pytest.raises(AssetError, match="ولا تمديد صامت ولا قصّ صامت"):
        resolve_assets(intent(), NEED, catalog(e), root)


def test_the_duration_margin_is_enforced(root):
    """أصل بالضبط على المقاس بيقدر ينقص إطارًا عند التكميم."""
    exact = Probe(width=1920, height=1080, fps=25.0, duration=3.0)
    with pytest.raises(AssetError, match="هامش"):
        resolve_assets(intent(), NEED, catalog(entry(root, probe=exact)), root)
    ok = Probe(width=1920, height=1080, fps=25.0,
               duration=3.0 + DURATION_MARGIN_S)
    resolve_assets(intent(), NEED, catalog(entry(root, probe=ok)), root)


def test_a_segment_without_a_required_duration_fails(root):
    with pytest.raises(AssetError, match="ما في مدة مطلوبة"):
        resolve_assets(intent(), {}, catalog(entry(root)), root)


@pytest.mark.parametrize("need", [0.0, -1.0])
def test_a_non_positive_requirement_fails(root, need):
    with pytest.raises(AssetError, match="مدة مطلوبة"):
        resolve_assets(intent(), {1: need}, catalog(entry(root)), root)


# ══ الحتمية ═════════════════════════════════════════════════════════
def test_the_same_intent_and_catalog_give_the_same_asset(root):
    c = catalog(entry(root, name="a.mp4", body=b"AAA"),
                entry(root, name="b.mp4", body=b"BBB"))
    a = resolve_assets(intent(), NEED, c, root)
    b = resolve_assets(intent(), NEED, c, root)
    assert a[1] == b[1]


def test_ties_break_on_the_reference_not_the_file_order(root):
    """ترتيب الكتالوج بيتغيّر مع أي إضافة؛ النتيجة ما لازم تتغيّر معه."""
    x = entry(root, name="x.mp4", body=b"XXX", provider_ref="zzz")
    y = entry(root, name="y.mp4", body=b"YYY", provider_ref="aaa")
    assert resolve_assets(intent(), NEED, catalog(x, y), root)[1].provider_ref \
        == resolve_assets(intent(), NEED, catalog(y, x), root)[1].provider_ref \
        == "aaa"


def test_a_better_match_wins_over_the_tie_break(root):
    weak = entry(root, name="w.mp4", body=b"WWW", provider_ref="aaa",
                 keywords=("rain",), shot_type="wide", palette="monochrome")
    strong = entry(root, name="s.mp4", body=b"SSS", provider_ref="zzz")
    assert resolve_assets(intent(), NEED, catalog(weak, strong),
                          root)[1].provider_ref == "zzz"


def test_the_in_point_is_computed_from_the_asset(root):
    e = entry(root)                       # 12.0s، المطلوب 3.0
    assert in_point_for(e, 3.0) == 4.5
    assert resolve_assets(intent(), NEED, catalog(e), root)[1].in_point == 4.5


def test_the_in_point_never_goes_negative(root):
    e = entry(root, probe=Probe(width=16, height=16, fps=25.0, duration=3.2))
    assert in_point_for(e, 3.0) == 0.1
    assert in_point_for(e, 9.0) == 0.0


# ══ الكتالوج نفسه ═══════════════════════════════════════════════════
def test_a_missing_catalog_fails(root):
    with pytest.raises(ContractError, match="كتالوج الأصول مفقود"):
        load_catalog(root / "nope.json")


def test_a_malformed_catalog_fails(root):
    (root / "c.json").write_text("not json")
    with pytest.raises(ContractError, match="JSON غير صالح|كتالوج غير صالح"):
        load_catalog(root / "c.json")


def test_an_extra_catalog_field_fails(root):
    e = json.loads(entry(root).model_dump_json())
    e["note"] = "whatever"
    (root / "c.json").write_text(json.dumps({"entries": [e]}))
    with pytest.raises(ContractError, match="كتالوج غير صالح"):
        load_catalog(root / "c.json")


def test_an_empty_catalog_fails(root):
    (root / "c.json").write_text(json.dumps({"entries": []}))
    with pytest.raises(ContractError, match="كتالوج غير صالح"):
        load_catalog(root / "c.json")


def test_a_catalog_round_trips_from_disk(root):
    e = entry(root)
    (root / "c.json").write_text(
        json.dumps({"entries": [json.loads(e.model_dump_json())]}))
    cat, cat_root = load_catalog(root / "c.json")
    assert cat_root == root.resolve()
    assert resolve_assets(intent(), NEED, cat, cat_root)[1].provider_ref \
        == e.provider_ref


# ══ الحدّ: الـresolver ما بينادي نموذجًا ════════════════════════════
def test_the_resolver_never_calls_a_model():
    import ast
    src = (pathlib.Path(__file__).resolve().parents[2]
           / "ai_pipeline/agents/resolver.py").read_text("utf-8")
    for node in ast.walk(ast.parse(src)):
        mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                else [node.module] if isinstance(node, ast.ImportFrom)
                and node.module else [])
        for m in mods:
            for bad in ("anthropic", "runner", "providers", "prompts"):
                assert bad not in m, f"الـresolver مربوط بطبقة النموذج — {m}"
        if isinstance(node, ast.Attribute):
            assert node.attr != "complete", "الـresolver بينادي مزوّدًا"


def test_style_alone_never_makes_a_candidate(root):
    """أصل غير ذي صلة + نفس `shot_type`/`palette` = **مش مرشّحًا**.

    الأسلوب بيرجّح بين المرشّحين، وما بيصنع مرشّحًا. بلا هالشرط
    الـresolver بيرجّع أصلًا عشوائيًا بصمت وبيبيّن ناجحًا — وهاد أخطر
    من الفشل، لأن الفيديو بيطلع وفيه لقطة ما إلها علاقة.
    """
    e = entry(root, keywords=("desert", "road", "asphalt"))
    assert score(e, intent().intents[0]) is None
    with pytest.raises(AssetError, match="ولا أصل"):
        resolve_assets(intent(), NEED, catalog(e), root)


def test_must_include_alone_is_enough_evidence(root):
    """لو الوكيل حدّد `must_include` صراحةً، هو الدليل."""
    e = entry(root, keywords=("desert", "dune"))
    got = resolve_assets(intent(query="something else entirely",
                                must_include=["dune"]), NEED, catalog(e), root)
    assert got[1].provider_ref == e.provider_ref


# ── الاستمرارية عبر مقاطع متتالية بنفس الأصل ─────────────────────────
def test_the_same_asset_continues_instead_of_recentring(root):
    """مقطعان متتاليان بنفس الأصل: التاني بيبلّش من حيث انتهى الأول.

    **القطع بيضل بالـtimeline، والعين ما بتشوفه.** هيك بتنحلّ مشكلة
    «الخلفية بتتبدّل مع كل جملة» بلا ما نلمس `quantize` — مقيسة على
    فيديو مرجعي حمل تلات جمل بلقطة وحدة.
    """
    e = entry(root)                                   # 12.0s
    want = AssetIntentItem(segment_id=1, query="rain night window",
                           shot_type="macro", palette="charcoal")
    two = AssetIntent(intents=(want, want.model_copy(update={"segment_id": 2})))
    got = resolve_assets(two, {1: 3.0, 2: 3.0}, catalog(e), root)
    assert got[1].provider_ref == got[2].provider_ref
    assert got[2].in_point == round(got[1].in_point + 3.0, 3), (
        "المقطع التاني ما كمّل — بيرجع يتوسّط فالعين بتشوف قفزة")


def test_a_different_asset_in_between_resets_the_window(root):
    """أصل بيرجع **بعد أصل غيره** بيبلّش من جديد.

    الاستمرارية إلها معنى للمتتالي وبس: العين شافت قطعًا للأصل التاني
    على أي حال، فمتابعة النافذة القديمة بتوفّر لا شي وبتعقّد التتبّع.
    """
    a = entry(root)
    b = entry(root, name="other.mp4", body=b"OTHER-BYTES",
              keywords=("sun", "desert", "road"), shot_type="wide",
              palette="warm_gold")
    mk = lambda sid, q, sh, pa: AssetIntentItem(   # noqa: E731
        segment_id=sid, query=q, shot_type=sh, palette=pa)
    three = AssetIntent(intents=(
        mk(1, "rain night window", "macro", "charcoal"),
        mk(2, "sun desert road", "wide", "warm_gold"),
        mk(3, "rain night window", "macro", "charcoal")))
    got = resolve_assets(three, {1: 3.0, 2: 3.0, 3: 3.0},
                         catalog(a, b), root)
    assert got[1].provider_ref == got[3].provider_ref
    assert got[3].in_point == got[1].in_point, "ما رجع للتوسيط"


def test_continuation_falls_back_when_the_asset_runs_out(root):
    """الأصل ما بيكفّي لنافذة تانية -> بيرجع للتوسيط، ما بيتجاوز نهايته.

    بلا هالسقوط، `in_point + المطلوب` بيتخطّى المدة و`quantize` بترفض
    بـ«الأصل بيعطي N إطار من M مطلوبة» — فشل صحيح برسالة بمكان غلط.
    """
    e = entry(root, probe=Probe(width=1920, height=1080, fps=30.0,
                                duration=7.0))
    want = AssetIntentItem(segment_id=1, query="rain night window",
                           shot_type="macro", palette="charcoal")
    two = AssetIntent(intents=(want, want.model_copy(update={"segment_id": 2})))
    got = resolve_assets(two, {1: 3.0, 2: 3.0}, catalog(e), root)
    for sid in (1, 2):
        assert got[sid].in_point + 3.0 <= e.probe.duration

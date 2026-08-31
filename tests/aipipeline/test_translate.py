"""ترجمة النيّة للقيم الموجودة — **وولا عقد مجمَّد انفتح**."""
import pathlib

import pytest

from ai_pipeline.edit import (
    BeatProposal, CueProposal, EditPlan, EmphasisProposal, ShotProposal,
)
from ai_pipeline.agents.expand import ThemeView, expand_typography_proposal
from ai_pipeline.agents.schemas import (
    TypographyProposal, TypographySegmentProposal,
)
from ai_pipeline.edit.translate import (
    CUE_ASSET, CUE_GAIN, EMPHASIS, apply_emphasis, cue_events, silenced_beats,
    typography_overrides,
)

#: **الـtheme الحقيقي من `cli.THEMES`**، لا واحد مبني للاختبار. قيمة
#: بتنجح على theme مخترَع وبتفشل على المنتج ما بتثبت شي.
THEME = ThemeView(
    theme_id="nur-dark", font_role="body", base_font_size=66, size_step_px=3,
    color_hex={"primary": "#FFFFFF", "muted": "#EDEDED", "accent": "#FFF4DC"},
    max_lines=2)


def mk(emphasis=(), cues=()):
    return EditPlan(
        beats=(BeatProposal(beat_id=1, segment_ids=(1, 2), role="hook"),),
        shots=(ShotProposal(shot_id=1, beat_id=1, order=0),),
        emphasis=tuple(emphasis), cues=tuple(cues))


# ── الكابشن ──────────────────────────────────────────────────────────
def test_each_level_survives_the_real_expansion_into_the_frozen_contract():
    """**ولا قيمة مخترَعة.** كل مستوى بيمرق على التوسعة الحقيقية.

    الفحص مش «الـDTO بيقبل القيمة» — الـDTO مفردات مغلقة وبيقبلها
    بحكم تعريفه. الفحص إن القيمة **بتوصل عقد Phase 1 المجمَّد** عبر
    `expand_typography_proposal` نفسها اللي المسار القديم بيستعملها،
    مع الـtheme المنتَج، وإن الأرقام النهائية هي المقصودة: 66+step×3
    بكسل، والـhex من الـtheme لا من هون.

    **وحدّ الفحص معلَن:** ما بيقدر يمسك «قيمة بتعدّي الـschema
    وبتنكسر عند التوسعة» — `size_step ∈ [-2,+2]` بيعطي 60..72 وكلها
    جوّا `[8, 400]`، والأدوار التلاتة كلها معرَّفة بالـtheme. فالمدى
    اللي بيمسكه فعلًا (مقيس بطفرة M6): **الترجمة اللي ما بتطبّق**.
    """
    for level, (step, color, anim) in EMPHASIS.items():
        p = mk(emphasis=[EmphasisProposal(segment_id=1, word_index=0,
                                          level=level)])
        base = TypographyProposal(
            segments=(TypographySegmentProposal(segment_id=1),))
        c = expand_typography_proposal(apply_emphasis(base, p), THEME)
        assert c.segments[0].animation == anim
        assert c.overrides[1].font_size == 66 + step * 3
        assert c.overrides[1].text_color == THEME.color_hex[color]


def test_segments_without_emphasis_pass_through_the_translation_untouched():
    """الغياب بيوصل التوسعة **كما هو** — ولا قيمة بتنزرع بالطريق."""
    base = TypographyProposal(segments=(
        TypographySegmentProposal(segment_id=1, size_step=-1,
                                  color_role="muted", animation="fade"),
        TypographySegmentProposal(segment_id=2)))
    p = mk(emphasis=[EmphasisProposal(segment_id=2, word_index=0, level="peak")])
    out = apply_emphasis(base, p)
    assert out.segments[0] == base.segments[0]
    assert (out.segments[1].size_step, out.segments[1].color_role,
            out.segments[1].animation) == EMPHASIS["peak"]


def test_the_levels_are_ordered_and_distinct():
    """`peak` أقوى من `strong` أقوى من `normal` — وإلا الإبراز بلا معنى."""
    steps = [EMPHASIS[k][0] for k in ("normal", "strong", "peak")]
    assert steps == sorted(steps) and len(set(steps)) == 3
    assert EMPHASIS["normal"][1] == "primary"
    assert EMPHASIS["peak"][1] == "accent"


def test_the_highest_emphasis_wins_within_a_segment():
    """العقد بيعطي قيمة **لكل مقطع** لا لكل كلمة، فالاختيار معلَن."""
    p = mk(emphasis=[EmphasisProposal(segment_id=1, word_index=0, level="strong"),
                     EmphasisProposal(segment_id=1, word_index=2, level="peak"),
                     EmphasisProposal(segment_id=1, word_index=4, level="normal")])
    assert typography_overrides(p)[1] == EMPHASIS["peak"]


def test_segments_without_emphasis_are_absent_not_defaulted():
    """الغياب **غياب** — قيمة افتراضية صامتة بتخفي إن الوكيل ما قرّر."""
    p = mk(emphasis=[EmphasisProposal(segment_id=2, word_index=0, level="peak")])
    o = typography_overrides(p)
    assert set(o) == {2}


def test_the_typography_contract_was_not_opened():
    """**حارس على الشجرة المجمَّدة.** الترجمة بتستعمل حقولها، ما بتضيف."""
    src = pathlib.Path("ai_pipeline/models/typography.py").read_text(encoding="utf-8")
    assert "emphasis" not in src.lower()
    assert "word_index" not in src


# ── الصوت ────────────────────────────────────────────────────────────
def test_every_cue_kind_maps_to_a_real_asset_or_to_silence():
    root = pathlib.Path("assets/sfx")
    for kind, asset in CUE_ASSET.items():
        if asset is None:
            assert kind == "silence"
            continue
        assert (root / f"{asset}.wav").is_file(), f"أصل مفقود: {asset}"


def test_silence_produces_no_event():
    """`silence` **قرار بمنع مؤثر**، لا مؤثر صامت."""
    p = mk(cues=[CueProposal(beat_id=1, kind="silence")])
    assert cue_events(p) == []
    assert silenced_beats(p) == {1}


def test_a_sounding_cue_is_not_counted_as_silence():
    """الحالة السالبة: `silence` **تصنيف**، لا صفة لكل مؤثر.

    بلاها كان `silenced_beats` يقدر يرجّع كل الـbeats والطقم يضل
    أخضر — والمترجم بيكتم مؤثرات طُلبت صراحة.
    """
    p = mk(cues=[CueProposal(beat_id=1, kind="impact")])
    assert silenced_beats(p) == set()
    assert [e[2] for e in cue_events(p)] == ["impact"]


def test_weights_map_to_distinct_increasing_gains():
    g = [CUE_GAIN[k] for k in ("subtle", "normal", "heavy")]
    assert g == sorted(g) and len(set(g)) == 3


def test_the_headroom_still_holds():
    """**الهامش محسوب لا مقيس:** 0.70 (كلام) + 0.90 (أعلى ذروة أصل)
    × أقصى كسب. كسر هالحساب بيقصّ عيّنات بصمت."""
    assert 0.70 + 0.90 * max(CUE_GAIN.values()) < 1.0


def test_a_cue_carries_its_beat_anchor_and_gain():
    p = mk(cues=[CueProposal(beat_id=1, at="beat_start", kind="impact",
                             weight="heavy")])
    assert cue_events(p) == [(1, "beat_start", "impact", CUE_GAIN["heavy"])]


def test_no_cue_appears_without_a_proposal():
    """**الحدّ اللي انكسر:** المؤثر كان تابعًا لكل حدّ لقطة."""
    assert cue_events(mk()) == []

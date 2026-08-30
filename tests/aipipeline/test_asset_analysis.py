"""`AssetAnalysis` — وصف ما في اللقطة، لا ما اسمها.

**قاعدة الترحيل هون:** الغياب لازم يعطي سلوك اليوم **بالضبط**. كتالوج
قديم بلا تحليل ما بيصير خطأ ولا بياخد قيمة مخترَعة — بيمرق كما هو.
"""
import json

import pytest

from ai_pipeline.agents.resolver import (
    AssetAnalysis, CatalogEntry, in_point_for, load_catalog,
)
from ai_pipeline.errors import ContractError
from ai_pipeline.models.assets import Probe


def entry(**kw) -> CatalogEntry:
    base = dict(provider="local", provider_ref="ref", path="a.mp4",
                license="CC0", sha256="a" * 64,
                probe=Probe(width=1920, height=1080, fps=30.0, duration=30.0))
    return CatalogEntry(**{**base, **kw})


# ── الغياب = سلوك اليوم بالضبط ───────────────────────────────────────
def test_a_catalog_without_analysis_still_loads(tmp_path):
    """**شرط الترحيل الأول.** كتالوج قديم لازم يضل صالحًا حرفيًا."""
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps({"entries": [{
        "provider": "local", "provider_ref": "r", "path": "a.mp4",
        "license": "CC0", "sha256": "b" * 64,
        "probe": {"width": 1920, "height": 1080, "fps": 30.0, "duration": 12.0},
    }]}), encoding="utf-8")
    cat, _ = load_catalog(p)
    assert cat.entries[0].analysis is None


def test_without_analysis_the_in_point_is_still_centred():
    """التوسيط الرياضي **يبقى** لما ما في تحليل — بلا فرق ولا إطار."""
    e = entry()
    assert in_point_for(e, 10.0) == 10.0          # (30 − 10) ÷ 2


# ── best_window يغلب التوسيط ─────────────────────────────────────────
def test_best_window_beats_the_blind_midpoint():
    """أعلى حقل قيمة بالتحليل: لقطة أفضل ثانيتين فيها بأولها.

    بلاه بياخد المنتصف — بلا أي علم بأين الحركة.
    """
    e = entry(analysis=AssetAnalysis(best_window=(2.0, 8.0)))
    #  منتصف النافذة 5.0 · المطلوب 4s ⟶ يبدأ 3.0
    assert in_point_for(e, 4.0) == 3.0
    assert in_point_for(entry(), 4.0) == 13.0     # بلا تحليل: (30−4)÷2


def test_the_window_is_clamped_inside_the_asset():
    """نافذة بآخر الملف ما بتخلّي البداية تتجاوز `duration − required`."""
    e = entry(analysis=AssetAnalysis(best_window=(28.0, 30.0)))
    assert in_point_for(e, 10.0) == 20.0          # 30 − 10
    e2 = entry(analysis=AssetAnalysis(best_window=(0.0, 1.0)))
    assert in_point_for(e2, 10.0) == 0.0          # ما بتنزل تحت الصفر


def test_continuity_still_wins_over_best_window():
    """**الترتيب مقصود.** القطع غير المرئي أثمن من أفضل ثانية.

    الطفرة اللي بتقلب الترتيب بتخرّب الاستمرارية اللي صلّحناها بـ2772dea.
    """
    e = entry(analysis=AssetAnalysis(best_window=(2.0, 8.0)))
    assert in_point_for(e, 4.0, after=17.5) == 17.5


def test_a_full_window_falls_back_when_continuity_does_not_fit():
    """`after` بيتجاوز نهاية الأصل ⟶ `best_window` هي البديل، لا المنتصف."""
    e = entry(analysis=AssetAnalysis(best_window=(2.0, 8.0)))
    assert in_point_for(e, 4.0, after=29.0) == 3.0


# ── المفردات مغلقة ───────────────────────────────────────────────────
@pytest.mark.parametrize("field,bad", [
    ("subject", "car"), ("environment", "space"), ("action", "insane"),
    ("camera", "gimbal"), ("shot_scale", "huge"), ("composition", "diagonal"),
    ("energy", "wild"), ("safe_caption_area", "middle"),
])
def test_the_analysis_vocabulary_is_closed(field, bad):
    """نفس مبدأ `schemas.py`: القوة بما **لا يقدر** المصدر التعبير عنه.

    مفتوحة المفردات تعني إن أي تحليل آلي لاحقًا بيقدر يحقن قيمة
    الـResolver ما بيعرفها — وبتمرق بصمت.
    """
    with pytest.raises(Exception):
        AssetAnalysis(**{field: bad})


def test_an_inverted_window_is_rejected():
    with pytest.raises(Exception, match="best_window"):
        AssetAnalysis(best_window=(9.0, 3.0))
    with pytest.raises(Exception, match="best_window"):
        AssetAnalysis(best_window=(-1.0, 3.0))


def test_analysis_does_not_disturb_the_frozen_fields():
    """الحقول الحالية ما انلمست — الترخيص والبصمة والـprobe بمكانهن."""
    e = entry(analysis=AssetAnalysis(subject="hands"))
    assert e.license == "CC0" and e.sha256 == "a" * 64
    assert e.probe.duration == 30.0 and e.analysis.subject == "hands"

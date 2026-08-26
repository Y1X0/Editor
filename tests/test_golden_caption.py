"""
صور مرجعية للكابشن العربي.

ليش موجودة: التشكيل والاتجاه بيصيروا جوا libraqm/HarfBuzz، فالانحدار
هون بيطلع **شكل** — حروف مقلوبة، مربعات فاضية، كلمة بالمكان الغلط —
وما بينمسك بتأكيدات عددية. الصورة المرجعية بتمسكه.

بس رندر الخطوط بيتغيّر بين إصدارات Pillow/FreeType/HarfBuzz، فالمقارنة
بتسامح صغير، والفشل بيطبع بيئة التوليد مقابل بيئتك عشان تعرف إذا الفرق
انحدار حقيقي ولا بس اختلاف مكدّس.

تحديث المرجع بعد تغيير مقصود:
    AUTOREEL_REGEN_GOLDEN=1 pytest tests/test_golden_caption.py

تخطّيها على مكدّس خطوط مختلف:
    pytest -m "not golden"
"""
import json
import os
from pathlib import Path

import pytest

from autoreel import captions as CAP
from conftest import GOLDEN, needs_raqm

W = 1080
REGEN = os.environ.get("AUTOREEL_REGEN_GOLDEN") == "1"
MAX_DIFF = 0.02          # نسبة البكسلات المسموح تختلف

# (نص، فهرس التلوين، اسم التصدير) — التصدير None يعني جذر الconfig
CASES = {
    "one_line": ("وبيحط كابشن عربي بالاتجاه", None, None),
    "two_lines": ("الاستراتيجية المسؤوليات الاستثمارات المشروعات", None, None),
    "highlight_first": ("واحد اثنين ثلاثة", 0, None),
    "highlight_last": ("واحد اثنين ثلاثة", 2, None),
    "shrunk": ("المسؤوليات الاستراتيجية والاستثمارات الاجتماعية بالمستشفيات", None, None),
    # مقاس لكل تصدير: نفس النص بإعدادات وعرض مختلفين
    "size_reel": ("وبيحط كابشن عربي بالاتجاه", 1, "reel"),
    "size_square": ("وبيحط كابشن عربي بالاتجاه", 1, "square"),
    "size_wide": ("وبيحط كابشن عربي بالاتجاه", 1, "wide"),
}


def _env():
    from PIL import __version__ as pil
    from PIL import features
    return {
        "pillow": pil,
        "freetype": features.version("freetype2"),
        "raqm": features.version("raqm"),
        "harfbuzz": features.version("harfbuzz"),
    }


def _diff_ratio(a, b):
    from PIL import ImageChops
    d = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).convert("L")
    off = sum(n for v, n in enumerate(d.histogram()) if v > 8)
    return off / (d.width * d.height)


def case_config(caps, export):
    """إعدادات الكابشن وعرض الإطار للحالة — من التصدير أو من الجذر."""
    if export is None:
        return caps, W
    import json
    from autoreel import exports as X
    from conftest import ROOT
    root = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    root["captions"]["font"] = caps["font"]          # مسار مطلق من الfixture
    c = X.resolve(root, export)
    return c["captions"], c["output"]["width"]


@needs_raqm
@pytest.mark.golden
@pytest.mark.parametrize("name", sorted(CASES))
def test_caption_matches_golden(caps, name, tmp_path):
    from PIL import Image

    text, hl, export = CASES[name]
    ccfg, cw = case_config(caps, export)
    got = CAP.render_caption(text, ccfg, cw, highlight_idx=hl)
    ref = GOLDEN / f"{name}.png"

    if REGEN or not ref.exists():
        GOLDEN.mkdir(parents=True, exist_ok=True)
        got.save(ref)
        (GOLDEN / "ENV.json").write_text(
            json.dumps(_env(), indent=2, ensure_ascii=False), encoding="utf-8")
        pytest.skip(f"تولّد المرجع {ref.name} — راجعه بعينك وكمّته")

    want = Image.open(ref)
    made_on = json.loads((GOLDEN / "ENV.json").read_text(encoding="utf-8"))
    context = f"\nالمرجع تولّد على: {made_on}\nعندك: {_env()}"

    assert got.size == want.size, (
        f"مقاس الكابشن تغيّر: {got.size} بدل {want.size}.{context}")

    ratio = _diff_ratio(got, want)
    if ratio > MAX_DIFF:
        bad = tmp_path / f"{name}_got.png"
        got.save(bad)
        pytest.fail(f"{ratio:.1%} من البكسلات مختلفة (المسموح {MAX_DIFF:.0%})."
                    f"\nالناتج انحفظ بـ{bad}{context}")


@needs_raqm
@pytest.mark.golden
def test_golden_files_are_present():
    """لو انمسحت الصور المرجعية بالغلط، خلّي الاختبار يقول هيك بوضوح."""
    if REGEN:
        pytest.skip("وضع إعادة التوليد")
    missing = [n for n in CASES if not (GOLDEN / f"{n}.png").exists()]
    assert not missing, (
        f"صور مرجعية ناقصة: {missing}. "
        f"ولّدها بـ AUTOREEL_REGEN_GOLDEN=1 pytest tests/test_golden_caption.py")

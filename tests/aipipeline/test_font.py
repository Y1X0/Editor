"""§15 — خط غير صالح للنص المطلوب.

الخلل اللي هالملف موجود ليمسكه **مقيس**: `Tajawal` بترسم النص القرآني
دوائر منقّطة، بلا استثناء وبلا تحذير من ولا طبقة.
"""
import pytest

from ai_pipeline.errors import TypographyError
from ai_pipeline.validation.font import (
    check_font_can_render, covered_codepoints, missing_codepoints,
)

AMIRI_Q = "fonts/AmiriQuran-Regular.ttf"
AMIRI = "fonts/Amiri-Bold.ttf"
TAJAWAL = "fonts/Tajawal-ExtraBold.ttf"

QURAN = "الٓمٓ ۚ ذَٰلِكَ ٱلْكِتَٰبُ ۛ لَا رَيْبَ ۖ فِيهِ"
PLAIN = "ومن يتوكل على الله فهو حسبه"
TASHKEEL = "وَمَن يَتَوَكَّلْ عَلَى اللَّهِ"


@pytest.mark.parametrize("font", [AMIRI_Q, AMIRI, TAJAWAL])
def test_cmap_parses(font):
    assert len(covered_codepoints(font)) > 100


@pytest.mark.parametrize("font", [AMIRI_Q, AMIRI])
def test_amiri_covers_the_quranic_text(font):
    assert missing_codepoints(font, QURAN) == []
    check_font_can_render(font, [QURAN, TASHKEEL, PLAIN])


def test_tajawal_cannot_render_quranic_marks():
    """الخلل المقيس — علامات الوقف وألف الوصل مش موجودة بالخط."""
    missing = missing_codepoints(TAJAWAL, QURAN)
    assert missing, "لو صار Tajawal بيغطّيها، هالفحص لازم ينتحدَّث بقصد"
    assert set(missing) >= {0x06D6, 0x06DA, 0x06DB, 0x0671}


def test_tajawal_still_fine_for_the_editor_text():
    """المحرر بيستعمل Tajawal لنص عادي — والحارس ما بيمنعه."""
    check_font_can_render(TAJAWAL, [PLAIN, TASHKEEL])


def test_the_error_names_every_missing_codepoint():
    with pytest.raises(TypographyError) as e:
        check_font_can_render(TAJAWAL, [QURAN])
    msg = str(e.value)
    assert "[TYPOGRAPHY_ERROR]" in msg
    for cp in ("U+06D6", "U+06DA", "U+06DB", "U+0671"):
        assert cp in msg, cp
    assert "دوائر منقّطة" in msg


def test_missing_font_file_fails(tmp_path):
    with pytest.raises(TypographyError, match="الخط مش موجود"):
        check_font_can_render(tmp_path / "nope.ttf", [PLAIN])


def test_a_file_that_is_not_a_font_fails(tmp_path):
    p = tmp_path / "fake.ttf"
    p.write_bytes(b"this is not a font at all, not even close")
    with pytest.raises(TypographyError, match="صيغة خط غير مدعومة"):
        check_font_can_render(p, [PLAIN])


def test_truncated_font_fails(tmp_path):
    p = tmp_path / "short.ttf"
    p.write_bytes(b"\x00\x01")
    with pytest.raises(TypographyError, match="قصير"):
        check_font_can_render(p, [PLAIN])


def test_invisible_controls_are_not_reported():
    """محارف الاتجاه ما إلها رسم — غيابها مش خللًا."""
    assert missing_codepoints(AMIRI_Q, "‏‎ـ نص") == []

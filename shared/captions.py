"""رسم النص العربي — Pillow + libraqm.

⚠️ ولا `arabic_reshaper` ولا `python-bidi`. القاعدة بـ`CLAUDE.md`
بالجذر، وهي على مستوى المستودع مش على مستوى وحدة.

**مقيس قبل إعادة الاستعمال** (`docs/ai-video-pipeline/SPIKE-FINDINGS.md`):
`autoreel.captions._layout` بتقيس بـ`textbbox` على النص الفعلي، مش من
`font.getmetrics()` — فالتشكيل القرآني وعلامات الوقف **ما بتنقصّ**.
جرّبناها بنص `الٓمٓ ۚ ذَٰلِكَ ٱلْكِتَٰبُ` مع AmiriQuran: هامش 55px فوق و21px
تحت، ولا قصّ.

**بس الخط مش مشتركًا:** Tajawal ما فيها علامات الوقف ولا الألف
الخنجرية، فبتطلّع **دوائر منقّطة** على النص القرآني. لكل نظام
theme خاص فيه.
"""
from autoreel.captions import (                   # noqa: F401
    assert_fits_frame,
    available_width,
    blank_png,
    caption_box,
    caption_size,
    pad_to_box,
    render_caption,
)

__all__ = [
    "render_caption", "caption_size", "assert_fits_frame", "available_width",
    "pad_to_box", "caption_box", "blank_png",
]

"""
أدوات قياس لاختبارات القبول.

**كل أداة هون عندها اختبار أرضية بـ`tests/test_measure_floor.py`.**
مش عادة حلوة — شرط. بمرحلة الاستكشاف انكسرت عشر أدوات قياس أول مرة
انشغّلت فيها (عتبة فوق قمة الإشارة، ألوان بتتكرّر، صف وقع على خط شبكة،
خيار مخرَج انحطّ مكان مدخَل...)، وكل وحدة كانت رح تعطي رقمًا غلط
بالمواصفة. أداة قياس بلا اختبار على مدخل معروف الجواب = نتيجة بلا معنى.

الأدوات:
  source   — يبني مصدر اختبار بيحمل تلات إشارات سوا
  probe    — عدّ الإطارات واستخراجها
  identity — رقم الإطار (هوية) من صورة مخرَج
  zoom     — معامل التكبير من صورة مخرَج
  clicks   — أزمنة النقرات من مسار الصوت
"""
from .clicks import click_times
from .identity import frame_id, read_identities
from .probe import (count_frames, extract_frames, ffmpeg_available, run_ffmpeg)
from .source import (CLICK_EVERY, GRID_PITCH, ID_CAPACITY, PATCH, SR,
                     build_source, id_color)
from .zoom import expected_scale, measure_scale

__all__ = [
    "click_times", "frame_id", "read_identities", "count_frames",
    "extract_frames", "ffmpeg_available", "run_ffmpeg", "build_source",
    "id_color", "CLICK_EVERY", "GRID_PITCH", "ID_CAPACITY", "PATCH", "SR",
    "expected_scale", "measure_scale",
]

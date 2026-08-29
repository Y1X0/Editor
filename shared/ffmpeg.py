"""تشغيل ffmpeg — مصدر واحد لمكان الثنائية ولطريقة التشغيل."""
from __future__ import annotations

import os
import shutil

from autoreel.render import preview, run   # noqa: F401  (إعادة تصدير)

__all__ = ["exe", "run", "preview"]


def exe() -> str:
    """مسار ثنائية ffmpeg.

    الترتيب: `$FFMPEG` -> `ffmpeg` من الـPATH -> `imageio-ffmpeg` لو
    مثبَّتة. الأخيرة بتشحن بناءً ثابتًا 7.0.2 — نفس البناء اللي انمعاير
    عليه المشروع — فبتنفع بيئة بلا ffmpeg مركَّب.

    **`autoreel` لسا بتستعمل الحرفية `"ffmpeg"` بخمس مواقع، وهاد
    مقصود:** استبدالها بينلمس سلوك المحرر وقت التشغيل، فمؤجَّل لـcommit
    منفصل بخط أساس قبله وبعده. هالدالة لـ`ai_pipeline` هلأ.
    """
    if env := os.environ.get("FFMPEG"):
        return env
    if found := shutil.which("ffmpeg"):
        return found
    try:
        import imageio_ffmpeg
    except ModuleNotFoundError:
        raise RuntimeError(
            "ما لقيت ffmpeg. ركّبه بالنظام، أو حدّد $FFMPEG، أو "
            "`pip install imageio-ffmpeg`."
        ) from None
    return imageio_ffmpeg.get_ffmpeg_exe()

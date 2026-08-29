"""§1 و§19 — المدخلات موجودة وصالحة قبل ما يبلّش أي شغل.

**ليش مش `shared.probe.probe`:** هي مبنية لمصادر فيديو وبترمي على ملف
صوت خالص —

    RuntimeError: ما قدرت أقرا أبعاد الفيديو من input/audio.wav

فما بتقدر تجاوب على «هل هاد ملف صوت صالح». وتعديل `autoreel` عشان
تجاوب سؤالًا مش سؤالها تغيير بسلوك المحرر بلا مبرّر. النداء هون واحد
(`ffmpeg -i`)، وبلا `ffprobe` — نفس قرار المستودع.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from shared.ffmpeg import exe

from ..errors import AlignmentError, AssetError

_DUR = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d\.\d+)")
_AUDIO = re.compile(r"Stream #\d+:\d+.*: Audio: (\w+).*?(\d+) Hz")


def probe_audio(path: str | Path) -> tuple[float, str, int]:
    """`(مدة, ترميز, معدل العيّنات)` لملف صوت. بيرمي بدل ما يخمّن."""
    p = Path(path)
    if not p.is_file():
        raise AssetError(f"ملف الصوت مفقود: {p}")
    if p.stat().st_size == 0:
        raise AssetError(f"ملف الصوت فاضي: {p}")
    r = subprocess.run([exe(), "-hide_banner", "-i", str(p)],
                       capture_output=True, text=True)
    err = r.stderr
    m = _AUDIO.search(err)
    if not m:
        raise AssetError(
            f"{p}: ولا تيار صوت. ffmpeg قال:\n"
            + "\n".join(l for l in err.splitlines() if "Stream" in l or
                        "Invalid" in l or "does not contain" in l)[:400])
    d = _DUR.search(err)
    if not d:
        # مدة مجهولة بتنتشر لخطة الإطارات كلها — الرقم المخترَع أسوأ
        # من الفشل الصريح. نفس قرار `cuts.probe`.
        raise AssetError(f"{p}: ffmpeg ما أعطى مدة (Duration: N/A)")
    dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    if dur <= 0:
        raise AssetError(f"{p}: مدة غير صالحة {dur}")
    return dur, m.group(1), int(m.group(2))


def check_audio_matches_alignment(audio_duration: float, alignment) -> None:
    """آخر كلمة ما بتقدر تنتهي بعد نهاية الصوت."""
    last = max(w.end for w in alignment.words)
    if last > audio_duration + 0.05:
        raise AlignmentError(
            f"المحاذاة بتتجاوز الصوت: آخر كلمة بتنتهي عند {last:.3f}s "
            f"والصوت {audio_duration:.3f}s")


def check_script(path: str | Path) -> str:
    from ..errors import ContractError
    p = Path(path)
    if not p.is_file():
        raise ContractError(f"النص المصدر مفقود: {p}")
    t = p.read_text(encoding="utf-8")
    if not t.strip():
        raise ContractError(f"النص المصدر فاضي: {p}")
    return t

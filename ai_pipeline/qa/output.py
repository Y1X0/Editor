"""§17–§20 — فحص المخرَج نفسه، مش الخطة.

**القاعدة اللي بتحكم هالملف: `exit code 0` مش إثباتًا.**

مقيس بهالمستودع: تسلسل صور فيه ملف واحد ٤٠٨×٢٠٨ بدل ٤٠٧×٢٠٨ — فرق
**بكسل واحد** — أعطى **٧٣ إطار من ١٤٤**، وffmpeg خرج بصفر وبلا تحذير.
فالفحص الوحيد اللي بيعني شي هو عدّ اللي طلع فعلًا ومقارنته بالخطة.

وكل فحص هون عليه **ضابط سالب**: ملف مكسور عمدًا لازم يفشّله. حارس
ما انفحص على حالة سيّئة معروفة مش حارسًا.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shared.ffmpeg import exe
from shared.probe import assert_output_not_mislabelled

from ..errors import QaError

_FRAME = re.compile(r"frame=\s*(\d+)")
_VIDEO = re.compile(r"Video: (\w+).*?, (\d+)x(\d+)[^,]*,")
_FPS = re.compile(r",\s*([\d.]+) fps")
_SAR = re.compile(r"SAR (\d+):(\d+)")
_AUDIO = re.compile(r"Audio: (\w+).*?(\d+) Hz")


@dataclass(frozen=True)
class OutputProbe:
    frames: int
    width: int
    height: int
    fps: float
    sar: tuple[int, int]
    has_audio: bool
    audio_samples: int
    audio_rate: int


def probe_output(path: str | Path) -> OutputProbe:
    p = Path(path)
    if not p.is_file():
        raise QaError(f"المخرَج مش موجود: {p}")
    if p.stat().st_size == 0:
        raise QaError(f"المخرَج فاضي: {p}")

    info = subprocess.run([exe(), "-hide_banner", "-i", str(p)],
                          capture_output=True, text=True).stderr
    v = _VIDEO.search(info)
    if not v:
        raise QaError(f"{p}: ولا تيار فيديو")
    vline = info[info.index("Video:"):].split("\n")[0]
    fps = _FPS.search(vline)
    if not fps:
        raise QaError(f"{p}: ما قدرت أقرا معدل الإطارات")
    # **آخر SAR بسطر الفيديو، مش أولها.** الحاوية بتعلن وحدة والترميز
    # ممكن يعلن غيرها؛ اللي بيوصل للمشغّل هو المرمَّزة. الاختلاف
    # بينهن هو بالضبط حادثة SAR 10240:10239.
    sars = _SAR.findall(vline)
    sar = (int(sars[-1][0]), int(sars[-1][1])) if sars else (1, 1)

    a = _AUDIO.search(info)
    samples, rate = 0, 0
    if a:
        rate = int(a.group(2))
        raw = subprocess.run(
            [exe(), "-v", "error", "-i", str(p), "-map", "0:a",
             "-f", "s16le", "-ac", "1", "-ar", str(rate), "-"],
            capture_output=True).stdout
        samples = len(raw) // 2

    r = subprocess.run([exe(), "-v", "error", "-i", str(p), "-map", "0:v",
                        "-f", "null", "-", "-stats"],
                       capture_output=True, text=True)
    hits = _FRAME.findall(r.stderr)
    if not hits:
        raise QaError(f"{p}: ما قدرت أعدّ الإطارات — ffmpeg ما طبع تقدّمًا")
    return OutputProbe(int(hits[-1]), int(v.group(2)), int(v.group(3)),
                       float(fps.group(1)), sar, bool(a), samples, rate)


def verify_output(path, timeline, output) -> OutputProbe:
    """بيقارن المخرَج بالخطة وبيجمّع **كل** الاختلافات قبل ما يرمي.

    التجميع مقصود: الرمي عند أول اختلاف بيخبّي الباقي، فبتصلّح واحدة
    وبترمّز من جديد عشان تكتشف التانية.
    """
    pr = probe_output(path)
    bad: list[str] = []

    if pr.frames != timeline.total_frames:
        d = pr.frames - timeline.total_frames
        bad.append(f"إطارات: {pr.frames} بدل {timeline.total_frames} ({d:+d})")
    if (pr.width, pr.height) != (output.width, output.height):
        bad.append(f"الدقة: {pr.width}x{pr.height} بدل "
                   f"{output.width}x{output.height}")
    if round(pr.fps) != output.fps:
        bad.append(f"معدل الإطارات: {pr.fps} بدل {output.fps}")
    if pr.sar != (1, 1):
        bad.append(
            f"SAR {pr.sar[0]}:{pr.sar[1]} مش 1:1 — هدف `scale` غير صحيح "
            f"وffmpeg عوّض الفرق بنسبة البكسل. الإصلاح `setsar=1` بعد `crop`")
    if not pr.has_audio:
        bad.append("ولا تيار صوت بالمخرَج")
    else:
        if pr.audio_rate != output.sample_rate:
            bad.append(f"معدل العيّنات: {pr.audio_rate} بدل {output.sample_rate}")
        d = pr.audio_samples - timeline.total_samples
        # التسامح إطار واحد. المقيس على AAC هو +128 عيّنة (priming
        # delay)، والطول مثبَّت بالبناء (`apad,atrim=end_sample=N`) —
        # فأي فرق أكبر من إطار انزياح حقيقي مش هامش ترميز.
        if abs(d) > timeline.samples_per_frame:
            bad.append(
                f"طول الصوت: {pr.audio_samples} بدل {timeline.total_samples} "
                f"({d:+d} عيّنة = {d / pr.audio_rate * 1000:+.1f}ms)")

    if bad:
        raise QaError(f"{Path(path).name} ما طابق الخطة:\n" +
                      "\n".join(f"      · {b}" for b in bad))

    # وسم كاذب أخطر من غياب الوسم — نفس حارس المحرر، ما بينتنسخ
    assert_output_not_mislabelled(str(path))
    return pr

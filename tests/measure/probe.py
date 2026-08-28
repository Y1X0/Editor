"""تشغيل ffmpeg وعدّ الإطارات واستخراجها."""
import os
import re
import shutil
import subprocess


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def run_ffmpeg(args, check=True):
    """`args` بلا اسم البرنامج. بيرجّع CompletedProcess."""
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args],
                       capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"ffmpeg رجّع {r.returncode}:\n{r.stderr[-2000:]}")
    return r


def count_frames(path):
    """عدد الإطارات اللي بيفكّها ffmpeg فعلًا — مش المدة ÷ fps."""
    r = subprocess.run(["ffmpeg", "-i", str(path), "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"frame=\s*(\d+)", r.stderr)
    if not m:
        raise RuntimeError(f"ما قدرت أعدّ إطارات {path}:\n{r.stderr[-1000:]}")
    return int(m[-1])


def stream_fps(path):
    """معدّل الإطارات اللي **بتعلنه الحاوية** — مش اللي منتوقّعه."""
    r = subprocess.run(["ffmpeg", "-i", str(path)], capture_output=True, text=True)
    m = re.findall(r"(\d+(?:\.\d+)?)\s+fps", r.stderr)
    return float(m[0]) if m else None


def extract_frames(path, outdir):
    """
    كل إطارات الفيديو كـPNG، مرتّبة.

    `-fps_mode passthrough` **بعد** `-i`:
      * بدونها مخرِج الصور بيشتغل cfr وبيطلّع إطارًا زيادة (٣٣٧ بدل ٣٣٦)
        — خلل بالاستخراج بينقرا كأنه خلل بالمسار.
      * وهي خيار **مخرَج**؛ لو انحطّت قبل `-i` ffmpeg بيتجاهلها وبيطلّع
        صفر صورة، والاختبار بيمرق على مجموعة فاضية.
    """
    os.makedirs(outdir, exist_ok=True)
    run_ffmpeg(["-i", str(path), "-fps_mode", "passthrough",
                os.path.join(str(outdir), "%06d.png")])
    return [os.path.join(str(outdir), f)
            for f in sorted(os.listdir(str(outdir))) if f.endswith(".png")]


# وسوم ألوان SDR — بديل `render.probe_source_full` بالفحوص اللي
# موضوعها مش الألوان (هندسة، صوت، كابشن).
#
# **مش قاموسًا فاضيًا ولا `None`:** الاتنين بيعطّلوا سلسلة الـtonemap
# كمان، بس بمعنى «ما بنعرف» بدل «مصدر SDR». والفحص اللي بده يتأكد إن
# SDR ما بينتأثر لازم يمرّر مصدرًا معلوم الوسوم.
SDR_COLORS = {"pix_fmt": "yuv420p", "range": "tv", "primaries": "bt709",
              "matrix": "bt709", "trc": "bt709", "hdr": False, "bits": 8}


def sdr_probe(w, h, has_audio=True, duration=20.0):
    """`probe_source_full` وهمية لمصدر SDR معروف."""
    return lambda _p: (w, h, has_audio, duration, dict(SDR_COLORS))

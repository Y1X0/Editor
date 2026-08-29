"""§17–§20 — والضوابط السالبة على الحارس نفسه.

**القاعدة:** حارس ما انفحص على حالة سيّئة معروفة مش حارسًا. كل فحص
هون بيجي بزوج: ملف سليم بيمرق، وملف **مكسور عمدًا بنفس الطريقة**
بيفشل. الطقم الأخضر لحاله ما بيثبت إن الكاشف بيكشف.
"""
import subprocess

import pytest

from ai_pipeline.errors import QaError
from ai_pipeline.models.project import Output
from ai_pipeline.models.timeline import Span, Timeline
from ai_pipeline.qa.output import probe_output, verify_output
from shared.ffmpeg import exe

pytestmark = pytest.mark.ffmpeg

W, H, FPS, SR, N = 128, 224, 30, 48000, 60      # صغير عشان يضل سريعًا
OUT = Output(width=W, height=H, fps=FPS, sample_rate=SR)
TL = Timeline(fps=FPS, sample_rate=SR, total_frames=N,
              visual_spans=(Span(segment_id=1, f_start=0, f_end=N),),
              text_spans=(Span(segment_id=1, f_start=5, f_end=N - 5),))


def _make(path, *, frames=N, w=W, h=H, fps=FPS, audio=True,
          audio_frames=None, bad_sar=False):
    # `setsar=1` بعد scale — نفس اللي الرندر الحقيقي بيعمله. بدونه
    # `scale` غير المتناسب بيخلي ffmpeg يحفظ DAR بـSAR (قِسناها: 28:9)،
    # فالـfixture «السليمة» بتفشل الحارس. الفحص مسك fixture غلط قبل ما
    # يمسك كودًا غلط — وهاد وجه من نفس الدرس.
    vf = f"scale={w}:{h},setsar=1"
    if bad_sar:
        # نفس مسار الخلل الحقيقي: هدف scale غير صحيح من مصدر 16:9،
        # فffmpeg بيعوّض الفرق بـSAR بدل ما يشتكي.
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
              f"crop={w}:{h}")
    src = "testsrc2=s=384x216:r=%d:d=%.4f" % (fps, frames / fps + 0.5)
    cmd = [exe(), "-y", "-v", "error", "-f", "lavfi", "-i", src]
    if audio:
        af = (audio_frames if audio_frames is not None else frames)
        cmd += ["-f", "lavfi", "-i", f"sine=f=300:r={SR}:d={af / fps + 0.5}"]
    cmd += ["-vf", f"fps={fps},{vf}", "-frames:v", str(frames),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast"]
    if audio:
        af = (audio_frames if audio_frames is not None else frames)
        cmd += ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-ar", str(SR),
                "-af", f"aresample={SR},apad,atrim=end_sample={af * (SR // fps)}"]
    else:
        cmd += ["-map", "0:v", "-an"]
    cmd += [str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-600:]
    return path


@pytest.fixture(scope="module")
def good(tmp_path_factory):
    return _make(tmp_path_factory.mktemp("qa") / "good.mp4")


# ── المرجع السليم ────────────────────────────────────────────────────
def test_a_correct_output_passes(good):
    pr = verify_output(good, TL, OUT)
    assert pr.frames == N and (pr.width, pr.height) == (W, H)
    assert pr.sar == (1, 1) and pr.has_audio


def test_probe_reads_what_is_really_there(good):
    pr = probe_output(good)
    assert pr.audio_rate == SR
    assert abs(pr.audio_samples - TL.total_samples) <= TL.samples_per_frame


# ── الضوابط السالبة: كل واحد بيكسر شي واحد ──────────────────────────
def test_dropped_frames_are_caught(tmp_path):
    """أخطر شكل: ffmpeg بيخرج بصفر والملف ناقص إطارات."""
    f = _make(tmp_path / "short.mp4", frames=N - 7)
    with pytest.raises(QaError, match="إطارات: 53 بدل 60"):
        verify_output(f, TL, OUT)


def test_extra_frames_are_caught(tmp_path):
    f = _make(tmp_path / "long.mp4", frames=N + 4)
    with pytest.raises(QaError, match=r"\+4"):
        verify_output(f, TL, OUT)


def test_wrong_resolution_is_caught(tmp_path):
    f = _make(tmp_path / "res.mp4", w=W + 2)
    with pytest.raises(QaError, match="الدقة"):
        verify_output(f, TL, OUT)


def test_wrong_fps_is_caught(tmp_path):
    f = _make(tmp_path / "fps.mp4", fps=25, frames=N)
    with pytest.raises(QaError, match="معدل الإطارات"):
        verify_output(f, TL, OUT)


def test_missing_audio_stream_is_caught(tmp_path):
    f = _make(tmp_path / "silent.mp4", audio=False)
    with pytest.raises(QaError, match="ولا تيار صوت"):
        verify_output(f, TL, OUT)


def test_short_audio_is_caught(tmp_path):
    """انزياح الصوت بيوصل للنشر لأنه ما بيبيّن بالصورة."""
    f = _make(tmp_path / "audio.mp4", audio_frames=N - 6)
    with pytest.raises(QaError, match="طول الصوت"):
        verify_output(f, TL, OUT)


def test_non_square_sar_is_caught(tmp_path):
    """إعادة إنتاج حادثة SAR 10240:10239 بالبناء نفسه."""
    f = _make(tmp_path / "sar.mp4", bad_sar=True)
    pr = probe_output(f)
    assert pr.sar != (1, 1), "الـfixture ما أنتجت SAR مكسورة — الضابط ميت"
    with pytest.raises(QaError, match="setsar=1"):
        verify_output(f, TL, OUT)


def test_all_mismatches_are_reported_together(tmp_path):
    """الرمي عند أول اختلاف بيخبّي الباقي ويكلّف تشغيلة ترميز لكل واحد."""
    f = _make(tmp_path / "many.mp4", frames=N - 3, w=W + 2, audio=False)
    with pytest.raises(QaError) as e:
        verify_output(f, TL, OUT)
    msg = str(e.value)
    assert "إطارات" in msg and "الدقة" in msg and "ولا تيار صوت" in msg


# ── §20 ──────────────────────────────────────────────────────────────
def test_missing_output_file_is_caught(tmp_path):
    with pytest.raises(QaError, match="مش موجود"):
        probe_output(tmp_path / "never-made.mp4")


def test_zero_byte_output_is_caught(tmp_path):
    p = tmp_path / "empty.mp4"; p.write_bytes(b"")
    with pytest.raises(QaError, match="فاضي"):
        probe_output(p)


def test_truncated_output_is_caught(tmp_path, good):
    """ffmpeg بيموت بنص الترميز فبيسيب ملفًا بيفتح وما بيكمّل."""
    p = tmp_path / "trunc.mp4"
    p.write_bytes(good.read_bytes()[: good.stat().st_size // 3])
    with pytest.raises(QaError):
        verify_output(p, TL, OUT)

"""
قراءة معلومات المصدر — **بلا `ffprobe`**.

هون بينمسك PR-1: `cli.main` بتنادي `probe_duration` بأول سطر، وهي كانت
بتنادي `ffprobe`. بيئة ffmpeg static ما فيها `ffprobe`، فالأمر اللي
بالREADME كان بينهار:

    FileNotFoundError: [Errno 2] No such file or directory: 'ffprobe'

**وليش ما مسكه ولا فحص من الـ٦٢٩:** كل فحص بيمرق على المسار بيبدّل
`probe_duration` بـ`monkeypatch`، لأن الفحوص بتولّد مصادرها وبتعرف
مدتها سلفًا. فالطقم أخضر والبرنامج ما بيقلع.

فالقاعدة هون: **ولا فحص بهالملف بيبدّل `probe_duration` ولا `probe`.**
منشغّل المسار الحقيقي على ffmpeg الموجود فعليًا بالبيئة. ولأن الغياب
لحاله ما بيثبت شي على جهاز فيه `ffprobe`، في فحص بيخبّي `ffprobe` عن
`PATH` وبيتأكد إن المسار بيكمّل.
"""
import os
import shutil
import subprocess

import pytest

from measure import build_source, ffmpeg_available
from measure.pipeline import shrink_config, write_srt

from autoreel import cuts as C
from autoreel import render as R

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود")

FPS, NFRAMES = 30, 300


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    return build_source(tmp_path_factory.mktemp("probe_src"),
                        width=320, height=568, fps=FPS, nframes=NFRAMES)


# ------------------------------------------------------------- القراءة

def test_probe_reads_everything_in_one_call(src):
    w, h, has_audio, dur = C.probe(src["path"])
    assert (w, h) == (320, 568)
    assert has_audio is True
    assert dur == pytest.approx(NFRAMES / FPS, abs=0.01)


def test_probe_duration_matches_the_full_probe(src):
    assert C.probe_duration(src["path"]) == C.probe(src["path"])[3]


def test_probe_source_is_the_same_reading(src):
    assert R.probe_source(src["path"]) == C.probe(src["path"])[:3]


def test_hours_are_parsed_not_dropped(tmp_path):
    """
    `Duration: HH:MM:SS.ss` — والمصدر القصير ما بيثبت إن `HH` بتنقرا.
    طفّرنا حدّ الساعات من التحليل وما فشل ولا فحص، لأن كل مصادر الطقم
    تحت الساعة.

    مصدر ساعة رخيص: ٣٦٦١ إطار ٣٢×٣٢ عند 1fps = ٨٣ms و٥٢ ك.ب.
    """
    long_src = tmp_path / "long.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=black:s=32x32:r=1", "-t", "3661",
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", str(long_src)], check=True)
    assert C.probe_duration(str(long_src)) == pytest.approx(3661.0, abs=0.02)


def test_an_unreadable_file_raises(tmp_path):
    bad = tmp_path / "مش-فيديو.mp4"
    bad.write_bytes(b"\x00" * 4096)
    with pytest.raises(RuntimeError):
        C.probe(str(bad))


def test_a_missing_duration_raises_instead_of_guessing(src, tmp_path):
    """
    `Duration: N/A` بتطلع لتيار حي أو خام بلا حاوية. أي رقم منخترعه هون
    بينتشر لخطة القص كلها، فالفشل أوضح من التخمين.

    **المصدر لازم يكون فيه فيديو صالح** وبس بلا مدة: ملف زبالة بيفشل
    عند قراءة الأبعاد قبل ما يوصل لفحص المدة، فما بيختبر هالفرع أصلًا.
    تيار H.264 خام بيعطي أبعادًا و`Duration: N/A` — بالضبط الحالة.
    """
    raw = tmp_path / "raw.h264"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src["path"]),
                    "-map", "0:v", "-c:v", "copy", "-f", "h264", str(raw)],
                   check=True)
    probe = subprocess.run(["ffmpeg", "-i", str(raw)], capture_output=True, text=True)
    assert "Duration: N/A" in probe.stderr, "المصدر ما طلع بلا مدة"

    with pytest.raises(RuntimeError, match="مدة"):
        C.probe(str(raw))


# ------------------------------------------ الدليل إن ffprobe ما عاد لازم

def _without_ffprobe(tmp_path):
    """
    `PATH` فيه أدوات ffmpeg بس — وبلا `ffprobe`.

    منعمل مجلد فيه وصلات لكل شي بالـ`PATH` الأصلي **إلا** `ffprobe`.
    هيك الفحص إله أسنان حتى على جهاز مثبَّت عليه `ffprobe`.
    """
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    seen = set()
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d or not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name in seen or name == "ffprobe":
                continue
            seen.add(name)
            try:
                os.symlink(os.path.join(d, name), fake / name)
            except OSError:
                pass
    assert shutil.which("ffmpeg", path=str(fake)), "كسرنا ffmpeg كمان"
    assert not shutil.which("ffprobe", path=str(fake)), "ffprobe لسا موصول"
    return str(fake)


def test_the_whole_cli_runs_with_ffprobe_hidden(src, tmp_path):
    """
    **الحارس الأساسي لـPR-1.**

    تشغيل حقيقي للـCLI — مش `--dry-run`، ولا تبديل لـ`probe_duration` —
    على `PATH` مقصوص منه `ffprobe`. لازم يطلع كود خروج صفر وملف مخرَج.
    """
    cfg = shrink_config(tmp_path / "config.json", 360, 640)
    srt = write_srt(tmp_path / "in.srt",
                    [(1.0, 2.2, "كلمة تانية تالتة"),
                     (3.5, 4.9, "رابعة خامسة App Store")])
    out = tmp_path / "out.mp4"

    env = dict(os.environ, PATH=_without_ffprobe(tmp_path))
    r = subprocess.run(
        ["python", "-m", "autoreel.cli", str(src["path"]),
         "--srt", str(srt), "-c", str(cfg), "-o", str(out)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env, capture_output=True, text=True, timeout=300)

    assert r.returncode == 0, f"stdout:\n{r.stdout[-2000:]}\nstderr:\n{r.stderr[-2000:]}"
    assert "ffprobe" not in r.stderr, r.stderr[-2000:]
    assert out.exists() and out.stat().st_size > 0


def test_probe_itself_needs_no_ffprobe(src, tmp_path):
    """`probe` لحالها بلا `ffprobe` — بعزل عن باقي المسار."""
    env = dict(os.environ, PATH=_without_ffprobe(tmp_path))
    r = subprocess.run(
        ["python", "-c",
         "import sys;from autoreel import cuts as C;print(C.probe(sys.argv[1]))",
         str(src["path"])],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    assert "320, 568, True" in r.stdout, r.stdout


def test_no_production_module_mentions_ffprobe_as_a_command():
    """
    حارس: `ffprobe` ممنوع يرجع **كأمر** بالإنتاج.

    الفحص على شجرة الكود مش على النص: منّدور على ثابت نصّي قيمته
    `"ffprobe"` بالضبط — وهاد شكل الوسيط بقائمة أمر. ذكره بتوثيق أو
    برسالة خطأ عادي، ومطلوب كمان (السبب موثّق بـ`cuts.probe`)، فحارس
    نصّي كان بيفشل على الوصف نفسه.
    """
    import ast

    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "autoreel")
    bad = []
    for name in sorted(os.listdir(root)):
        if not name.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(root, name), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "ffprobe":
                bad.append(f"{name}:{node.lineno}")
    assert not bad, "رجع نداء ffprobe: " + ", ".join(bad)

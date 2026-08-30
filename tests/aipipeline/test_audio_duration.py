"""من وين بتيجي `audio_duration` — وليش الطريق التاني بيغري.

`quantize` بتاخد `audio_duration` **كوسيط**، وما بتقيسها. فالسؤال «مين
بيقيسها» مفتوح عند كل مستدعي جديد، وعنده جوابان مغريان:

    shared.probe.probe_duration      ← تفويض لـ`autoreel.cuts.probe`
    validation.inputs.probe_audio    ← الصح لملف صوت خالص

والأول بيطلع أول بالبحث لأنه بـ`shared/`، واسمه بيقول «مدة». وهاد
بالضبط اللي صار: أول مستدعي حقيقي للمسار ناداه على `voice.wav` وطلع
«ما قدرت أقرا أبعاد الفيديو» — والقارئ الصحيح كان موجودًا من Phase 2
ومفحوصًا بـ`test_inputs.py`.

فالخلل ما كان بغياب قارئ. كان بغياب **حارس على الاختيار**. الملف هون
بيسدّه بتلات مستويات: الفرضية اللي القسمة مبنية عليها، وحارس ثابت على
شجرة الكود، وسلوك الحالات الحدّية اللي `test_inputs.py` ما غطّاها.

⚠️ ولا سطر إنتاج انتغيّر لهالملف. `validation/inputs.py` من الشجرة
المجمَّدة (Phase 2)، و`probe_audio` بتعمل شغلها صح.
"""
import ast
import pathlib
import subprocess

import pytest

from ai_pipeline.errors import AssetError
from ai_pipeline.validation.inputs import probe_audio
from shared.ffmpeg import exe
from shared.probe import probe_duration

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: أسماء بتقرا **مصدر فيديو**. نداء أي وحدة منهن على مسار الصوت هو
#: الغلطة اللي هالملف موجود عشانها.
VIDEO_READERS = frozenset({"probe", "probe_duration", "probe_source",
                           "probe_source_full", "verify_source"})

#: `qa/` بتفحص **المخرَج**، وهو فيديو فعلًا — فقراءتها منه صحيحة.
#: الاستثناء بالاسم مش بالنمط: مجلّد جديد بيلزمه قرار، مش انزلاق.
VIDEO_READER_OK = {"qa"}


@pytest.fixture(scope="module")
def wav_3s(tmp_path_factory):
    """صوت خالص، بلا أي تيار فيديو — مُدخَل المسار الحقيقي."""
    p = tmp_path_factory.mktemp("audio") / "voice.wav"
    subprocess.run([exe(), "-v", "error", "-f", "lavfi",
                    "-i", "sine=f=220:d=3", "-ar", "48000", "-ac", "1",
                    "-y", str(p)], check=True)
    return p


# ── ١· الفرضية اللي القسمة مبنية عليها ───────────────────────────────
@pytest.mark.ffmpeg
def test_the_editor_probe_cannot_read_audio_only(wav_3s):
    """**القارئان مش قابلين للتبادل** — وهاد اللي بيبرّر الحارس تحت.

    الفحص على الفرضية مش على الحالة: لو `autoreel.cuts.probe` صارت
    بيوم تقرا الصوت، هالتأكيد بيفشل وبيرجّع القارئ للقاعدة بدل ما
    يضل الحارس قائمًا على سبب ما عاد موجودًا.
    """
    with pytest.raises(RuntimeError, match="أبعاد الفيديو"):
        probe_duration(str(wav_3s))
    assert probe_audio(wav_3s)[0] > 0      # والتاني بيقراه عادي


# ── ٢· الحارس على شجرة الكود ─────────────────────────────────────────
def test_no_ai_pipeline_module_reads_duration_through_the_video_probe():
    """ولا وحدة بـ`ai_pipeline/` بتستورد قارئ فيديو (عدا `qa/`).

    ast مش نصًّا: `"probe_duration"` بتعليق أو بسطر توثيق مش نداء،
    والحارس اللي بيمسك التوثيق بيعلّم الناس يشيلوا التوثيق.
    """
    offenders = []
    for f in sorted((ROOT / "ai_pipeline").rglob("*.py")):
        rel = f.relative_to(ROOT / "ai_pipeline")
        if rel.parts and rel.parts[0] in VIDEO_READER_OK:
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith("shared.probe"):
                continue
            for a in node.names:
                if a.name in VIDEO_READERS:
                    offenders.append(f"{rel}: {a.name}")
    assert not offenders, (
        "قارئ مصدر فيديو انستورد بمسار الصوت:\n  " + "\n  ".join(offenders)
        + "\nمُدخَل `ai_pipeline` صوت خالص — القارئ الصحيح "
          "`validation.inputs.probe_audio`.")


def test_the_guard_names_readers_that_actually_exist():
    """كل اسم بـ`VIDEO_READERS` لازم يكون موجودًا فعلًا بـ`shared.probe`.

    بلا هيك الحارس بيصير قائمة أشباح: اسم انتغيّر بالمصدر بيخرج من
    التغطية بصمت والحارس بيضل أخضر وهو ما عاد بيحرس شي.
    """
    import shared.probe as sp
    missing = sorted(n for n in VIDEO_READERS if not hasattr(sp, n))
    assert not missing, f"أسماء مش موجودة بـshared.probe: {missing}"


# ── ٣· الحالات الحدّية اللي `test_inputs.py` ما غطّاها ───────────────
@pytest.mark.ffmpeg
def test_audio_with_no_samples_fails_closed(tmp_path):
    """ملف صوت **صالح البنية وفاضي المحتوى** بيفشل، ما بياخد صفرًا.

    ملف حقيقي مش مُحاكاة: wav بـ٧٨ بايت — ترويسة سليمة وولا عيّنة —
    وffmpeg بيعلن `Audio: pcm_s16le` مع `Duration: N/A`. فسطر التيار
    بيمرق والمدة لأ، وهاي بالضبط الحالة اللي بتخلّي مدة مخترَعة تتسرّب
    لخطة الإطارات كلها.
    """
    p = tmp_path / "empty_samples.wav"
    subprocess.run([exe(), "-v", "error", "-f", "lavfi", "-i", "sine=f=440",
                    "-t", "0", "-ar", "48000", "-y", str(p)], check=True)
    assert p.stat().st_size > 0            # مش الحالة الفاضية المغطّاة
    info = subprocess.run([exe(), "-hide_banner", "-i", str(p)],
                          capture_output=True, text=True).stderr
    assert "Duration: N/A" in info and "Audio:" in info   # الفرضية نفسها

    with pytest.raises(AssetError, match="ما أعطى مدة"):
        probe_audio(p)


@pytest.mark.ffmpeg
def test_the_same_file_gives_the_same_answer(wav_3s):
    """ولا ساعة ولا عشوائية ولا حالة: نفس المسار = نفس الثلاثي بالضبط."""
    first = probe_audio(wav_3s)
    assert all(probe_audio(wav_3s) == first for _ in range(3))


@pytest.mark.ffmpeg
def test_duration_is_within_a_centisecond_of_the_decoded_stream(wav_3s):
    """المدة المعلَنة مقابل **اللي ffmpeg بيسلّمه فعلًا** للفلاتر.

    `Duration:` مقرَّبة لجزء المئة (قرار مثبَّت بالمستودع)، و`quantize`
    بتضربها بالـfps. فحدّ الخطأ لازم يكون مقيسًا مش مفترَضًا: عند 30fps
    الـ١٠ms بتساوي 0.3 إطار — تحت نصف إطار، فالتقريب ما بيقدر يزحلق
    `total_frames`.
    """
    dur, _, sr = probe_audio(wav_3s)
    raw = subprocess.run(
        [exe(), "-v", "error", "-i", str(wav_3s), "-map", "0:a",
         "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
        capture_output=True, check=True).stdout
    decoded = len(raw) // 2 / sr
    assert abs(dur - decoded) <= 0.01, (
        f"المعلَن {dur}s والمفكوك {decoded}s — الفرق أكبر من جزء المئة، "
        f"يعني المدة مش مقرَّبة وبس")

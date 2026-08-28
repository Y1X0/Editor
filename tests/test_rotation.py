"""
الدوران — `probe` بترجّع أبعاد **العرض** مش المرمَّزة، وفحص الفرضية.

**الحادثة:** الآيفون بيسجّل أفقيًا وبيحط مصفوفة دوران، وffmpeg بيدوّر
**تلقائيًا عند الفكّ**. `cuts.probe` كانت بتقرا سطر `Stream` — الحجم
المرمَّز (١٩٢٠×١٠٨٠) — بينما اللي بيوصل رسم الفلاتر ١٠٨٠×١٩٢٠.

`graph.size_chain` بتبني نافذة القص من أرقام بايثون (لأن `crop.iw` ما
بتتتبّع مقاسًا متغيّرًا)، فالنافذة كانت بتطلع من مكان غلط **بلا ما
تفشل**: `✅ خلص` وملف سليم بتأطير مكسور.

**والرسم كان غلط بالتلات مقاسات** — `reel` بينجو وقت التشغيل بس لأن
`crop` بتقصّ الإحداثي الخارج عن الحدود لصفر. مقيس: PSNR `inf` عند
`reel` مقابل 8.50 و10.19 عند `square` و`wide`.

**ولا فحص هون بيبدّل `probe`** — نفس قاعدة `tests/test_probe.py`:
الفحص اللي بيبدّل الجزء المكسور ما بيشوف الكسر.
"""
import json
import os
import re
import subprocess

import pytest

from measure import ffmpeg_available, run_ffmpeg

from autoreel import cuts as C
from autoreel import exports as X
from autoreel import graph as G

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 30


@pytest.fixture(scope="module")
def land(tmp_path_factory):
    """مصدر أفقي ٦٤٠×٣٦٠ — بلا مصفوفة دوران."""
    d = tmp_path_factory.mktemp("rot")
    p = d / "land.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", f"smptehdbars=size=640x360:rate={FPS}:duration=4",
                "-f", "lavfi", "-i", "sine=duration=4:sample_rate=48000",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "1",
                "-shortest", str(p)])
    return {"path": str(p), "dir": d}


def _rotated(land, angle):
    """نفس الملف + مصفوفة دوران، **بلا إعادة ترميز**."""
    p = os.path.join(str(land["dir"]), f"rot{angle}.mov")
    run_ffmpeg(["-display_rotation", str(angle), "-i", land["path"],
                "-c", "copy", str(p)])
    return p


# ------------------------------------------------- S1: probe بترجّع العرض

@pytest.mark.parametrize("angle,expected", [
    (90, (360, 640)),
    (180, (640, 360)),
    (270, (360, 640)),
    (-90, (360, 640)),
])
def test_probe_returns_display_dimensions(land, angle, expected):
    """
    **الإشارة مش معلومة مفيدة:** ffmpeg بيطبّع الزاوية لـ(-180, 180]،
    فـ`270` و`-90` بيطلعوا `rotation of -90.00 degrees` بالضبط.
    """
    src = _rotated(land, angle)
    assert C.probe(src)[:2] == expected


def test_a_source_without_a_matrix_is_untouched(land):
    assert C.probe(land["path"])[:2] == (640, 360)


# ----------------------------------------- S2: التطابق مع اللي ffmpeg بيسلّم

@pytest.mark.parametrize("angle", [90, 180, 270, -90])
def test_probe_matches_what_ffmpeg_actually_delivers(land, angle):
    """
    **الفحص الجوهري.** مش «الدوران متصلّح» — بل «فرضيتنا تطابق الواقع».
    """
    src = _rotated(land, angle)
    assert C.probe(src)[:2] == C.delivered(src)[:2]


def test_the_plain_source_matches_too(land):
    assert C.probe(land["path"])[:2] == C.delivered(land["path"])[:2]


# ------------------------------------------------ S3: الرسم صار متطابقًا

@pytest.mark.parametrize("angle", [90, 270])
def test_the_filter_graph_is_now_identical_for_every_size(land, angle):
    """
    **S3.** قبل الإصلاح كان الرسم مختلفًا بالتلات مقاسات، و`reel`
    بينجو وقت التشغيل بس لأن `crop` بتقصّ الإحداثي الخارج عن الحدود.
    """
    src = _rotated(land, angle)
    pw, ph = C.probe(src)[:2]
    dw, dh = C.delivered(src)[:2]
    root = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    for name in X.select(root, "all"):
        cfg = X.resolve(root, name)
        a = G.size_chain(cfg, [1], [1.0], "v", "o", pw, ph)
        b = G.size_chain(cfg, [1], [1.0], "v", "o", dw, dh)
        assert a == b, f"رسم {name} لسا مبني على أبعاد غير مطبَّعة"


# ------------------------------------------------------ S5: الفحص بيرمي

def test_verify_source_raises_on_a_broken_assumption(land):
    """
    **بيرمي ما بيحذّر.** التحذير بيضيع بين أسطر تقدّم ffmpeg، والمستخدم
    بيشوف `✅ خلص` بالآخر.
    """
    with pytest.raises(RuntimeError, match="فرضية مكسورة"):
        C.verify_source(land["path"], 1920, 1080)


def test_the_error_names_both_numbers(land):
    """رسالة بلا رقمين ما بتقول للقارئ وين الخلل."""
    with pytest.raises(RuntimeError) as e:
        C.verify_source(land["path"], 111, 222)
    msg = str(e.value)
    assert "111" in msg and "222" in msg and "640" in msg and "360" in msg


@pytest.mark.parametrize("angle", [90, 180, 270])
def test_verify_source_passes_on_every_rotation(land, angle):
    src = _rotated(land, angle)
    w, h = C.probe(src)[:2]
    C.verify_source(src, w, h)


# --------------------------------------------------------- C8: SAR 0:1

def test_an_undefined_sar_is_accepted(land, tmp_path):
    """
    **`0:1` = غير محدَّد، وffmpeg بيعامله ١:١ — ولقطات الآيفون بتعطيه.**
    فحص بيقارن بـ`1:1` وبس كان رح يرمي على كل ملف منها.
    """
    assert "0:1" in C.OK_SAR and "1:1" in C.OK_SAR
    p = tmp_path / "sar01.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "smptehdbars=size=320x180:rate=30:duration=1",
                "-vf", "setsar=0/1", "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", str(p)])
    w, h = C.probe(str(p))[:2]
    C.verify_source(str(p), w, h)


def test_a_non_square_sar_is_refused(tmp_path):
    """
    `size_chain` بتشتغل على أبعاد التخزين وبتتجاهل SAR، فالصورة
    بتنضغط. مش مدعوم — والرفض أوضح من صورة مضغوطة بصمت.
    """
    p = tmp_path / "sar2.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "smptehdbars=size=320x180:rate=30:duration=1",
                "-vf", "setsar=2/1", "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", str(p)])
    w, h = C.probe(str(p))[:2]
    with pytest.raises(RuntimeError, match="SAR"):
        C.verify_source(str(p), w, h)


# ------------------------------------------------------ S6: الفحص موصول

def test_the_cli_actually_verifies_the_source(land, tmp_path):
    """
    **حارس الوصل.** `verify_source` موجودة بس مين بيناديها؟

    بلا هالفحص، شيل السطر من `cli.main` وكل فحوص S5 بتضل خضراء —
    نفس شكل خلل `motion.pan_px`. ونفس الخلل صار فعلًا بهالمرحلة:
    `cli` كانت بتمرّر ثلاثية فوسوم الألوان بتنقطع بصمت.

    منكسر الفرضية بتبديل `cuts.probe` **بعملية منفصلة** — مش بتبديل
    داخل الفحص — فالمسار الحقيقي هو اللي بينفحص.
    """
    shim = tmp_path / "shim.py"
    shim.write_text(
        "import sys, runpy\n"
        "from autoreel import cuts as C\n"
        "_real = C.probe\n"
        "C.probe = lambda p: (_real(p)[0] + 40,) + _real(p)[1:]\n"
        "sys.argv = ['autoreel'] + sys.argv[1:]\n"
        "runpy.run_module('autoreel.cli', run_name='__main__')\n",
        encoding="utf-8")
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:00,300 --> 00:00:01,500\nكلمة تانية\n\n", encoding="utf-8")
    # `python /path/shim.py` بتحط **مجلد السكربت** بالـpath مش الـcwd،
    # فالحزمة ما بتنلقى بلا `PYTHONPATH`.
    r = subprocess.run(
        ["python", str(shim), land["path"], "--srt", str(srt),
         "-o", str(tmp_path / "o.mp4")],
        cwd=ROOT, env=dict(os.environ, PYTHONPATH=ROOT),
        capture_output=True, text=True, timeout=300)
    assert r.returncode != 0, "الفرضية انكسرت والمسار كمّل — الفحص مش موصول"
    assert "فرضية مكسورة" in r.stderr, r.stderr[-1500:]
    assert not os.path.exists(str(tmp_path / "o.mp4")), "طلع ملف رغم كسر الفرضية"


# --------------------------------------------- S4: المعاينة = الترميز

@pytest.mark.slow
def test_the_preview_frames_match_the_encoded_output(land, tmp_path):
    """
    **S4 — الفحص اللي بيغلق أخطر شكل للخلل.**

    قبل الإصلاح: `render.segment_filter` (المعاينة) بتكتب `(iw-W)/2`
    فبتنحلّ على الأبعاد الحقيقية وبتطلع **صح**، بينما `size_chain`
    (الترميز) بتكتب أرقام بايثون وبتطلع **غلط**. يعني المسار الموصى
    فيه بالREADME — معاينة ثم تصدير — كان بيوري تأطيرًا سليمًا ثم
    بيصدّر غيره.

    **المقارنة لازم تكون على نفس اللحظة ومع الكابشن بالاتنين.** أول
    مرة قِستها بـ`--no-captions` على الترميز وحده فطلعت ٢١dB، والفرق
    كله كان الكابشن المحروق بالمعاينة — أثر قياس مش خلل.
    """
    src = _rotated(land, 90)
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:00,400 --> 00:00:03,000\nكلمة تانية تالتة\n\n",
                   encoding="utf-8")
    base = str(tmp_path / "o.mp4")
    for extra in (["--preview-frames"], []):
        r = subprocess.run(
            ["python", "-m", "autoreel.cli", src, "--srt", str(srt),
             "--sizes", "all", "-o", base] + extra,
            cwd=ROOT, capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]

    root = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    from autoreel import transcribe as T
    segs = C.segments_from_words(T.from_srt(str(srt)), C.probe_duration(src),
                                 **root["cuts"])
    a0, b0 = segs[0]
    n = round(((a0 + b0) / 2 - a0) * root["output"]["fps"])

    stem = base[:-4]
    for size in X.select(root, "all"):
        frame = str(tmp_path / f"e_{size}.png")
        run_ffmpeg(["-i", f"{stem}.{size}.mp4", "-vf", f"select=eq(n\\,{n})",
                    "-frames:v", "1", frame])
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", f"{stem}.{size}.preview.png",
             "-i", frame, "-lavfi", "[0:v][1:v]psnr", "-f", "null", "-"],
            capture_output=True, text=True)
        m = re.search(r"average:([\d.]+|inf)", out.stderr)
        assert m, out.stderr[-800:]
        db = float("inf") if m.group(1) == "inf" else float(m.group(1))
        assert db > 40, f"{size}: معاينة ↔ ترميز {db:.1f}dB — نافذتان مختلفتان"

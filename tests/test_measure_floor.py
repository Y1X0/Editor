"""
أرضية أدوات القياس — **يشتغل قبل أي اختبار قبول**.

كل أداة بـ`tests/measure/` بتنفحص على مدخل جوابه معروف مسبقًا، ودقّتها
بتنتوثّق برقم. بدون هالملف ما بنعرف نميّز انحدارًا بالمسار عن ضجيج
بالأداة — وهاي كانت أكتر مصيدة وقعنا فيها بمرحلة الاستكشاف.

بيحتاج ffmpeg وترميزًا حقيقيًا، فمعلّم `slow`.
"""
import os

import pytest
from PIL import Image

from measure import (CLICK_EVERY, GRID_PITCH, ID_CAPACITY, build_source,
                     click_times, count_frames, extract_frames,
                     ffmpeg_available, frame_id, id_color, measure_scale,
                     read_identities, run_ffmpeg)
from measure.clicks import drift_ms
from measure.identity import identity_report
from measure.zoom import expected_scale

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود"),
]

FPS = 30
NF = 240
SRC_W, SRC_H = 640, 1138

# الأرضيات الموثّقة. أي اختبار قبول بيستعمل عتبة **أوسع** من هدول.
FLOOR_SCALE = 0.004        # مقاس ٠.٠٠٠٧ — الهامش لاختلاف مكدّس الترميز
FLOOR_CLICK_MS = 5.0       # مقاس ١.٩٨ms = عرض النقرة نفسها


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    return build_source(tmp_path_factory.mktemp("measure_src"),
                        width=SRC_W, height=SRC_H, fps=FPS, nframes=NF)


# ------------------------------------------------------------------ probe

def test_count_frames_matches_what_we_built(src):
    assert count_frames(src["path"]) == NF


def test_extract_returns_exactly_the_frames_that_exist(src, tmp_path):
    assert len(extract_frames(src["path"], tmp_path / "fr")) == NF


def test_extract_does_not_inflate_a_concatenated_clip(src, tmp_path):
    """
    الحالة اللي بتكشف غياب `-fps_mode passthrough`.

    مصدر نظيف CFR بينستخرج صح حتى بلا الراية، فالفحص اللي فوقه ما إله
    أسنان لحاله — طفّرنا الراية وما فشل ولا اختبار. المشغّل الحقيقي هو
    **وجود مسار صوت** بمخرَج `concat` demuxer: مدة الحاوية بتتعدّى مدة
    الفيديو، والاستخراج بنمط cfr بيحشي إطارًا زيادة (١٦٩ بدل ١٦٨).

    الشكل هاد كان مخرَج `build_base` وقت ما انكتب الفحص. `build_base`
    انحذفت، بس الفحص ضلّ: هو حارس **أداة القياس** مش حارس الإنتاج —
    بيثبّت إن `extract_frames` ما بتحشي إطارات، وهاد اللي بتتّكل عليه
    كل اختبارات القبول.
    """
    parts, lst = [], tmp_path / "list.txt"
    for i, a in enumerate((0.237, 1.512, 3.104, 4.05)):
        p = str(tmp_path / f"s{i}.mp4")
        run_ffmpeg(["-ss", f"{a:.6f}", "-i", src["path"], "-frames:v", "42",
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", p])
        parts.append(p)
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = str(tmp_path / "joined.mp4")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", joined])

    n = count_frames(joined)
    assert n == 4 * 42, "المقدّمة انكسرت — المقاطع نفسها مش ١٦٨ إطار"
    assert len(extract_frames(joined, tmp_path / "fr2")) == n


# --------------------------------------------------------------- identity

def test_id_colors_are_unique():
    assert len({id_color(n) for n in range(ID_CAPACITY)}) == ID_CAPACITY


def test_every_source_frame_reads_back_its_own_number(src, tmp_path):
    pngs = extract_frames(src["path"], tmp_path / "fr")
    assert len(pngs) == NF, "الاستخراج فشل — لا تقارن على مجموعة فاضية"
    rep = identity_report(read_identities(pngs), list(range(NF)))
    assert rep["mismatches"] == []
    assert rep["duplicates"] == 0
    assert rep["missing"] == []
    assert rep["unreadable"] == []


def test_identity_returns_none_when_the_patch_is_absent():
    """
    بلا تسامح، أقرب لون دايمًا بينلاقى — فالأداة بتخترع هوية لإطار
    ما فيه رقعة. لازم ترجّع None.
    """
    assert frame_id(Image.new("RGB", (64, 64), (0, 200, 0))) is None


def test_identity_report_catches_a_swap_that_keeps_the_count():
    """
    الحالة اللي مرقت من E1: إطار ضايع وإطار مكرر، والعدد صح.
    لو هالفحص ما مسكها، E7 كله بلا قيمة.
    """
    want = [10, 11, 12, 13]
    got = [10, 12, 13, 13]          # ١١ ضاع و١٣ تكرّر — نفس الطول
    rep = identity_report(got, want)
    assert len(got) == len(want)
    assert rep["mismatches"] and rep["duplicates"] == 1 and rep["missing"] == [11]


# ------------------------------------------------------------------- zoom

@pytest.mark.parametrize("zoom", [1.0, 1.04, 1.10, 1.14, 1.25])
def test_measured_scale_matches_the_production_filter(src, tmp_path, zoom):
    """
    بنشغّل **نفس** سلسلة `render.segment_filter` لنمط crop، وبنتأكد إن
    الأداة بتقرا معاملها. المرجع `expected_scale` مش `zoom` نفسه: التقريب
    لزوجي و`increase` بيحرّكوه بأجزاء الألف.
    """
    out_w, out_h = 540, 960
    sw, sh = int(out_w * zoom / 2) * 2, int(out_h * zoom / 2) * 2
    vf = (f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
          f"crop={out_w}:{out_h}:(iw-{out_w})/2:(ih-{out_h})*0.5,"
          f"fps={FPS},setsar=1")
    clip = str(tmp_path / f"z{zoom}.mp4")
    run_ffmpeg(["-t", "0.4", "-i", src["path"], "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "10",
                "-pix_fmt", "yuv420p", clip])
    pngs = extract_frames(clip, tmp_path / f"fr{zoom}")
    assert pngs, "ما انستخرج ولا إطار"
    got = measure_scale(pngs[len(pngs) // 2])
    want = expected_scale(SRC_W, SRC_H, out_w, out_h, zoom)
    assert abs(got - want) < FLOOR_SCALE, f"مقيس {got:.4f} والمتوقَّع {want:.4f}"


def test_zoom_tool_separates_the_smallest_step_in_the_cycle(src, tmp_path):
    """
    `zoom_cycle` فيه ١.٠٠ و١.٠٤ — فرق ٠.٠٤. لو أرضية الأداة مش أضيق
    منه بكتير، فحص الزوم ما بيميّز مقطعًا عن جاره.
    """
    assert FLOOR_SCALE * 3 < 0.04, "أرضية الأداة قريبة من أصغر خطوة زوم"


# ----------------------------------------------------------------- clicks

def test_clicks_read_back_at_their_known_times(src):
    got = click_times(src["path"])
    want = src["click_at"]
    assert len(got) == len(want), f"لقينا {len(got)} نقرة والمتوقَّع {len(want)}"
    errs = drift_ms(got, want)
    assert max(abs(e) for e in errs) <= FLOOR_CLICK_MS


def test_click_threshold_is_relative_not_absolute(src):
    """
    أول نسخة استعملت عتبة مطلقة ٠.٢٥ وقمة الإشارة ٠.١٣٧ -> صفر نبضات.
    نص الصوت لازم يضل ينقرا نفس عدد النقرات.
    """
    quiet = str(os.path.join(os.path.dirname(src["path"]), "quiet.mp4"))
    run_ffmpeg(["-i", src["path"], "-af", "volume=0.2", "-c:v", "copy",
                "-c:a", "aac", quiet])
    assert len(click_times(quiet)) == len(src["click_at"])


def test_drift_refuses_to_compare_different_counts():
    """مقارنة أول min(len) بتخبّي نقرة ضايعة وبتطلّع انزياحًا صفرًا."""
    with pytest.raises(AssertionError):
        drift_ms([0.0, 0.5], [0.0, 0.5, 1.0])


# ------------------------------------------------------------------ source

def test_source_carries_all_three_signals_at_once(src, tmp_path):
    """
    الثوابت لازم تنقاس بنفس التشغيلة. لو المصدر ما حمل الثلاثة، بنكون
    أثبتنا إنهن بيزبطوا لحالهن مش مع بعض.
    """
    pngs = extract_frames(src["path"], tmp_path / "fr")
    img = Image.open(pngs[NF // 2])
    assert frame_id(img) == NF // 2                       # هوية
    assert abs(measure_scale(img) - 1.0) < FLOOR_SCALE    # شبكة
    assert len(click_times(src["path"])) >= 2             # صوت
    assert src["click_at"][1] - src["click_at"][0] == pytest.approx(CLICK_EVERY)
    assert GRID_PITCH > 1

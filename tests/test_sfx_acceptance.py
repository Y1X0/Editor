"""
S-E1..S-E11 — اختبارات قبول المؤثرات الصوتية.

انكتبت بالمرحلة ٢ **وهي فاشلة عمدًا**، وضلّت حمرا تلات مراحل لحد ما
انوصل المسار بالمرحلة ٥ — لأن **الاختبار اللي ما شفناه بيفشل مش
اختبار**. بتنادي `render.build_output` نفسها، مش نسخة منها.

    pytest -m "not sfx"      # الطقم بدونهن

---

**S-E9 هو المحور.** كل باقي الفحوص بتقيس "ما تغيّر شي": نفس عدد
الإطارات، نفس عدد العيّنات، نفس تزامن الكلام. وكلهن بينجحوا نجاحًا
تامًا لو **المؤثرات ما نزلت أصلًا**. بلا S-E9 الطقم كله بيوافق على
ميزة غير موجودة. صار معنا بالضبط بالمرحلة ٨ (فحص قتل ffmpeg اللي كان
بيمرق على عملية ميتة وبيطلع أخضر).
"""
import json
import os
import subprocess

import pytest

from measure import build_source, count_frames, ffmpeg_available
from measure import sfx as S
from measure.pipeline import shrink_config, write_srt

from autoreel import cuts as C
from autoreel import graph as G

pytestmark = [
    pytest.mark.sfx,
    pytest.mark.slow,
    pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود"),
]

FPS, OUT_W, OUT_H = 30, 360, 640
SEGS = [(1.0, 3.0), (5.0, 7.5), (9.0, 11.0), (12.5, 14.0)]
# أحداث على إطارات مخرَج — الفهرس هو الزمن، زي الكابشن بالضبط
EVENTS = [(0, "impact"), (17, "pop"), (44, "pop"), (60, "whoosh"),
          (91, "pop"), (120, "pop"), (150, "whoosh"), (180, "pop")]
TRANSIENT_EVENTS = [(f, a) for f, a in EVENTS if a in ("tick", "pop", "impact")]


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    return build_source(tmp_path_factory.mktemp("sfx_src"),
                        width=320, height=568, fps=FPS, nframes=420)


@pytest.fixture(scope="module")
def plan():
    return C.frame_plan(SEGS, FPS)


def _require_support():
    if not hasattr(G, "sfx_chain"):
        pytest.fail("`graph.sfx_chain` مش موجودة — مسار المؤثرات ما انبنى")


SCFG = {"output": {"width": OUT_W, "height": OUT_H, "fps": FPS, "crf": 23},
        "motion": {"enabled": False, "zoom_cycle": [1.0], "pan_px": 0},
        "geometry": {"fit": "crop", "crop_bias": 0.5},
        "captions": {"enabled": False, "y_ratio": 0.72, "size": 40},
        "cuts": {"min_gap": 0.45}}


def _cues_for(events):
    """أحداث الفحص -> `Cue` بواجهة `sfx.py` نفسها، بلا إعادة منطق."""
    from autoreel import sfx as X
    return [X.Cue(f, X.frame_to_sample(f, FPS), "caption", a, 0.25)
            for f, a in events]


def _render(src, out, events, pcm_audio=False):
    """
    تشغيلة كاملة **عبر `render.build_output`** — المسار الإنتاجي نفسه،
    مش نسخة منه.

    `pcm_audio=True` بيلغي ترميز AAC: قياس الوضع بدقة العيّنة بيتشوّش
    بضجيج AAC. التزامن الطرف-لطرف مع AAC محروس بـE2.
    """
    _require_support()
    import tempfile
    from autoreel import render as R

    work = tempfile.mkdtemp(prefix="sfxacc_")
    if pcm_audio:
        # نفس الرسم ونفس المدخلات — بس PCM بدل AAC عند الترميز.
        # الحاوية بتضل `.mkv` (mp4 ما بتقبل PCM)، فالمنادي بيمرّر اسمًا
        # بهالامتداد.
        real_run = R.run

        def pcm_run(cmd, *a2, **k2):
            cmd = list(cmd)
            for enc in ("aac",):
                if enc in cmd:
                    i = cmd.index(enc)
                    cmd[i] = "pcm_s16le"
            for flag in ("-b:a", "128k"):
                if flag in cmd:
                    i = cmd.index(flag)
                    del cmd[i:i + 2]
            return real_run(cmd, *a2, **k2)

        import unittest.mock as _m
        with _m.patch.object(R, "run", pcm_run):
            R.build_output(src["path"] if isinstance(src, dict) else src,
                           SEGS, [], SCFG, out, work, cues=_cues_for(events))
        return out
    R.build_output(src["path"] if isinstance(src, dict) else src,
                   SEGS, [], SCFG, out, work, cues=_cues_for(events))
    return out


def _touched(events):
    out = set()
    for frame, name in events:
        start = S.frame_to_sample(frame, FPS)
        out.update(range(max(0, start - 8),
                         start + S.wav_info(S.asset(name))[3] + 8))
    return out


def _signal(with_sfx, without, events):
    """
    إشارة المؤثرات معزولة — **بعد إلغاء كسب الكلام**.

    الطرح الخام بيخلّي فرق الكلام بالإشارة فالكاشف بيمسك نقرات المصدر
    كمؤثرات (مقيس: ٢٧ نبضة مقابل ٨ مؤثرات). المنهج المعتمد بالمرحلة ٤.
    """
    touched = _touched(events)
    g = S.estimate_gain(with_sfx, without, touched)
    return S.difference(with_sfx, without, gain=g), g


def _pair(src, tmp_path, events, tag=""):
    a = str(tmp_path / f"off{tag}.mkv")
    b = str(tmp_path / f"on{tag}.mkv")
    _render(src, a, [], pcm_audio=True)
    _render(src, b, events, pcm_audio=True)
    return b, a


# ------------------------------------------------------ الحارس الأساسي

def test_se9_the_effects_are_actually_present(src, tmp_path):
    """
    **S-E9 — بلا هاد الفحص، الطقم كله بيوافق على ميزة غير موجودة.**

    الفرق بين تشغيلة بمؤثرات وتشغيلة بدونهن لازم يكون **غير صفري**،
    وعدد المؤثرات المكتشفة لازم يساوي عدد الأحداث المطلوبة بالضبط.
    """
    _require_support()
    with_sfx, without = _pair(src, tmp_path, EVENTS)
    diff, _ = _signal(with_sfx, without, EVENTS)
    assert max(diff) > 0.01, "الفرق صفر — المؤثرات ما نزلت"

    # طاقة بكل نافذة، وولا طاقة برّا النوافذ. العدّ العام ما بيشتغل:
    # الأصول الصاعدة بتعبر العتبة مرارًا (مقيس ٢١ نبضة لـ٨ مؤثرات).
    for frame, name in EVENTS:
        st = S.frame_to_sample(frame, FPS)
        n = S.wav_info(S.asset(name))[3]
        assert S.onset_in_window(diff, st, n) is not None, \
            f"ما في مؤثر عند {name}@{frame}"
    # النوافذ **مرة وحدة** برّا الحلقة: بناؤها جوّاها بيعيد تركيب
    # مجموعة ٧٧ ألف عنصر ٣٨٤ ألف مرة، والفحص بيعلّق دقايق.
    touched = _touched(EVENTS)
    outside = [diff[i] for i in range(len(diff)) if i not in touched]
    assert max(outside) < 0.01, f"طاقة برّا النوافذ: {max(outside):.4f}"


# ----------------------------------------------------- حفظ الكلام والطول

def test_se1_speech_is_preserved_sample_for_sample(src, tmp_path):
    """
    الخاصية اللي بتحمي E2 بنيويًا: برّا نوافذ المؤثرات، ولا عيّنة
    كلام بتتغيّر. مقيسة بالتجارب: `normalize=0` -> ٠ من ٢٨٨٠٠٠.
    الطفرة اللي بتفشّلها: شيل `normalize=0`.
    """
    _require_support()
    with_sfx, without = _pair(src, tmp_path, EVENTS)
    a, b = S.pcm(without), S.pcm(with_sfx)
    touched = _touched(EVENTS)
    clean = [i for i in range(min(len(a), len(b)))
             if i not in touched and abs(a[i]) > 0.05]
    assert len(clean) > 50
    r = [b[i] / a[i] for i in clean]
    assert max(r) - min(r) < 0.01, "النسبة مش ثابتة — تشويه أو تنفّس أو إزاحة"
    assert abs(sum(r) / len(r) - G.DEFAULT_SPEECH_GAIN) < 0.01


def test_se2_frame_count_is_unchanged(src, tmp_path, plan):
    _require_support()
    out = str(tmp_path / "w.mp4")
    _render(src, out, EVENTS)
    assert count_frames(out) == sum(plan)


def test_se3_sample_count_is_unchanged(src, tmp_path):
    """
    الطفرة اللي بتفشّلها: شيل `duration=first` — مؤثر قريب من النهاية
    بيمدّد المخرَج.
    """
    _require_support()
    with_sfx, without = _pair(src, tmp_path, EVENTS)
    assert len(S.pcm(with_sfx)) == len(S.pcm(without))


# --------------------------------------------------------- دقة الوضع

def test_se4_every_effect_lands_on_its_planned_frame(src, tmp_path):
    """
    الطفرة اللي بتفشّلها: استبدال `adelay=NS` بميلي صحيح (±٢٣ عيّنة).

    بأصول **عابرة** بس — أرضية `whoosh`/`riser` بالمئات والآلاف
    لأن ذروتهن مش عند بدايتهن (`test_sfx_floor.py`).
    """
    _require_support()
    with_sfx, without = _pair(src, tmp_path, TRANSIENT_EVENTS, "t")
    diff, _ = _signal(with_sfx, without, TRANSIENT_EVENTS)
    for frame, name in TRANSIENT_EVENTS:
        want = S.frame_to_sample(frame, FPS)
        hit = S.onset_in_window(diff, want, S.wav_info(S.asset(name))[3])
        assert hit is not None, f"ما في مؤثر عند {name}@{frame}"
        err = hit - S.detector_floor(name) - want
        assert abs(err) <= 2, \
            f"{name}@{frame}: انزياح {err} عيّنة ({err / S.SR * 1000:.3f}ms)"


def test_se5_placement_error_does_not_accumulate(src, tmp_path):
    """
    `adelay` مطلقة مش متسلسلة، فالانزياح ما بيتراكم **بالبناء**.
    آخر مؤثر لازم يكون بنفس دقة أوّلهن.
    """
    _require_support()
    with_sfx, without = _pair(src, tmp_path, TRANSIENT_EVENTS, "t")
    diff, _ = _signal(with_sfx, without, TRANSIENT_EVENTS)
    errs = [S.onset_in_window(diff, S.frame_to_sample(f, FPS),
                              S.wav_info(S.asset(n))[3])
            - S.detector_floor(n) - S.frame_to_sample(f, FPS)
            for f, n in TRANSIENT_EVENTS]
    assert abs(errs[-1] - errs[0]) <= 1, f"الانزياح بيتراكم: {errs}"


# ------------------------------------------------------ فخاخ الصيغة

def test_se6_a_stereo_asset_lands_correctly(src, tmp_path):
    """
    الطفرة اللي بتفشّلها: شيل `all=1`. مقيس: المؤثر بيقع عند العيّنة
    **٠** بدل مكانه — لأن `adelay` بتأخّر القناة الأولى بس. صامت
    تمامًا، ولا تحذير من ffmpeg.
    """
    _require_support()
    assert S.wav_info(S.asset("pop"))[0] == 2, "الأصل مش ستيريو فالفحص فقد معناه"
    ev = [(60, "pop")]
    with_sfx, without = _pair(src, tmp_path, ev, "st")
    diff, _ = _signal(with_sfx, without, ev)
    want = S.frame_to_sample(60, FPS)
    hit = S.onset_in_window(diff, want, S.wav_info(S.asset("pop"))[3])
    assert hit is not None
    err = hit - S.detector_floor("pop") - want
    assert abs(err) <= 2, f"انزياح {err} — غالبًا `all=1` ناقصة"


def test_se7_a_44100hz_asset_lands_correctly(src, tmp_path):
    """
    الطفرة اللي بتفشّلها: شيل `aformat=sample_rates=…`. مقيس:
    +٤٢٤٥ عيّنة = **+٨٨ms**، بلا أي تحذير.

    أصول المستودع كلها 48k، فمنولّد أصلًا 44.1k عمدًا — بدونه هالفحص
    ما بيفحص شي.
    """
    _require_support()
    from autoreel import render as R

    # مجلد أصول بديل فيه `pop` بـ44.1k — بينمرّ على **نفس** مسار
    # الإنتاج (`render.sfx_asset`)، مش على مسار جانبي.
    odd_dir = tmp_path / "odd_assets"
    odd_dir.mkdir()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", S.asset("pop"),
                    "-ar", "44100", "-c:a", "pcm_s16le",
                    str(odd_dir / "pop.wav")], check=True, capture_output=True)
    import wave
    with wave.open(str(odd_dir / "pop.wav")) as w:
        assert w.getframerate() == 44100

    ev = [(60, "pop")]
    old = R.SFX_DIR
    try:
        R.SFX_DIR = str(odd_dir)
        with_sfx, without = _pair(src, tmp_path, ev, "odd")
    finally:
        R.SFX_DIR = old

    diff, _ = _signal(with_sfx, without, ev)
    want = S.frame_to_sample(60, FPS)
    hit = S.onset_in_window(diff, want, 4080, lead=256)
    assert hit is not None, "ما نزل المؤثر"
    err = hit - want
    assert abs(err) <= 60, f"انزياح {err} عيّنة — غالبًا `aformat` ناقصة"


# ------------------------------------------------------ E2 ما انكسر

def test_se8_source_audio_sync_is_untouched(src, tmp_path, plan):
    """
    **الحارس اللي ما بينتنازل عنه.** نقرات المصدر لازم تطلع بنفس
    المواقع بالضبط مع المؤثرات وبدونهن. أي فرق = المؤثرات حرّكت
    الكلام، وهاد بيلغي كل مكسب المرحلة ٦.
    """
    _require_support()
    # **`click_times` مش أداة تزامن هون.** عتبتها نسبية لقمة الملف،
    # والمؤثرات بترفع القمة فبتسقّط نقرات مصدر خافتة وبتعدّ مؤثرات
    # كنقرات (مقيس: ٣ ناقصة و٥ زايدة). قرار مثبَّت بالمرحلة ٤.
    #
    # البديل أقوى: شكل موجة الكلام نفسه. برّا نوافذ المؤثرات كل عيّنة
    # = الأصلية × **نفس** الثابت. إزاحة بعيّنة وحدة بتخرّب المدى
    # (مقيس ٠.٧٤ مقابل ٠.٠٠٠٦)، و`normalize=1` كمان (٠.٣٣).
    with_sfx, without = _pair(src, tmp_path, EVENTS, "sync")
    a, b = S.pcm(without), S.pcm(with_sfx)
    touched = _touched(EVENTS)
    clean = [i for i in range(min(len(a), len(b)))
             if i not in touched and abs(a[i]) > 0.05]
    assert len(clean) > 50
    r = [b[i] / a[i] for i in clean]
    assert max(r) - min(r) < 0.01, \
        f"شكل الكلام اتغيّر (مدى {max(r) - min(r):.4f}) — إزاحة أو تشويه"


# ------------------------------------------------- الخطة والحالات الحدّية

@pytest.mark.filterwarnings("ignore")
def test_se10_the_plan_respects_min_gap_and_max_concurrent():
    """
    **انبنت بالمرحلة ٣** — `autoreel/sfx.py`. الحدود بتنطبّق على
    **خطة المؤثرات** قبل بناء الرسم، زي `graph.py` بالضبط، فبتنفحص
    بلا ffmpeg. التغطية التفصيلية بـ`tests/test_sfx_plan.py`.

    هون بنتأكد من التعاقد اللي مرحلة الرسم رح تتّكل عليه: مؤثر واحد
    لكل نافذة، وفهرس عيّنة صحيح لكل مؤثر، وولا اتنين على إطار واحد.
    """
    from autoreel import sfx as X

    plan = C.frame_plan(SEGS, FPS)
    cues = X.plan_cues(plan, FPS, zooms=[1.0, 1.1, 1.2, 1.0],
                       caption_frames=[3, 4, 5, 40, 100, 150, 210])
    assert cues, "الخطة طلعت فاضية"

    gap = X.seconds_to_frames(X.DEFAULTS["min_gap"], FPS)
    frames = [c.frame for c in cues]
    assert all(b - a >= gap for a, b in zip(frames, frames[1:])), \
        f"مؤثرات أقرب من {gap} إطار: {frames}"

    spf = X.samples_per_frame(FPS)
    assert all(c.sample == c.frame * spf for c in cues)
    X.assert_within(cues, sum(plan))


def test_se11_a_source_without_audio_disables_effects(src, tmp_path, plan):
    """
    `[0:a]` مش موجودة، فما في `[acat]` نمزج عليها. المؤثرات لازم
    **تنطفي** والتشغيلة تنجح — مش تنبني على سرير مفقود.
    """
    _require_support()
    mute = str(tmp_path / "mute.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src["path"],
                    "-an", "-c:v", "copy", mute], check=True)
    out = str(tmp_path / "out.mp4")
    _render({"path": mute}, out, EVENTS)
    assert count_frames(out) == sum(plan)

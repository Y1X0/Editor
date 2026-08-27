"""
S-E1..S-E11 — اختبارات قبول المؤثرات الصوتية.

⚠️ **هالفحوص المفروض تفشل هلأ.** المؤثرات ما انبنت بالإنتاج بعد،
و`graph.sfx_chain` غير موجودة. هاي المرحلة ٢ من `SFX-SPEC.md` §E:
اكتب الفحص، **شوفه بيفشل**، بعدين نفّذ.

    pytest -m "not sfx"      # الطقم بدونهن

القاعدة اللي فرضت هالترتيب: بإعادة التصميم ضلّت E1 وE7 فاشلتين
عمدًا لمرحلتين، لأن **الاختبار اللي ما شفناه بيفشل مش اختبار**.

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


def _sfx_supported():
    return hasattr(G, "sfx_chain")


def _require_support():
    if not _sfx_supported():
        pytest.fail(
            "`graph.sfx_chain` مش موجودة — مسار المؤثرات ما انبنى بعد.\n"
            "هاد **الفشل المتوقَّع** بالمرحلة ٢ من SFX-SPEC.md §E.")


def _render(src, out, events, pcm_audio=False):
    """
    تشغيلة كاملة مع/بدون مؤثرات عبر واجهة الإنتاج المتفق عليها.

    `pcm_audio=True` بيلغي ترميز AAC — لازم لقياس الوضع بدقة العيّنة،
    لأن AAC بيضيف ضجيج ±٠.٠٠٣ بيخرّب كشف البداية. تزامن الطرف-لطرف
    مع AAC محروس أصلًا بـE2.
    """
    _require_support()
    raise NotImplementedError   # بينكتب بمرحلة التنفيذ


# ------------------------------------------------------ الحارس الأساسي

def test_se9_the_effects_are_actually_present(src, tmp_path):
    """
    **S-E9 — بلا هاد الفحص، الطقم كله بيوافق على ميزة غير موجودة.**

    الفرق بين تشغيلة بمؤثرات وتشغيلة بدونهن لازم يكون **غير صفري**،
    وعدد المؤثرات المكتشفة لازم يساوي عدد الأحداث المطلوبة بالضبط.
    """
    _require_support()
    with_sfx = str(tmp_path / "with.wav")
    without = str(tmp_path / "without.wav")
    _render(src, without, [], pcm_audio=True)
    _render(src, with_sfx, EVENTS, pcm_audio=True)

    diff = S.difference(with_sfx, without)
    assert max(diff) > 0.01, "الفرق صفر — المؤثرات ما نزلت"
    got = S.hits(diff)
    assert len(got) == len(EVENTS), \
        f"المطلوب {len(EVENTS)} مؤثر، لقينا {len(got)}"


# ----------------------------------------------------- حفظ الكلام والطول

def test_se1_speech_is_preserved_sample_for_sample(src, tmp_path):
    """
    الخاصية اللي بتحمي E2 بنيويًا: برّا نوافذ المؤثرات، ولا عيّنة
    كلام بتتغيّر. مقيسة بالتجارب: `normalize=0` -> ٠ من ٢٨٨٠٠٠.
    الطفرة اللي بتفشّلها: شيل `normalize=0`.
    """
    _require_support()
    with_sfx, without = str(tmp_path / "w.wav"), str(tmp_path / "o.wav")
    _render(src, without, [], pcm_audio=True)
    _render(src, with_sfx, EVENTS, pcm_audio=True)

    a, b = S.pcm(without), S.pcm(with_sfx)
    touched = set()
    for frame, name in EVENTS:
        start = S.frame_to_sample(frame, FPS)
        touched.update(range(max(0, start - 4), start + S.wav_info(S.asset(name))[3] + 4))
    changed = [i for i in range(min(len(a), len(b)))
               if i not in touched and a[i] != b[i]]
    assert not changed, f"{len(changed)} عيّنة كلام تغيّرت برّا نوافذ المؤثرات"


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
    with_sfx, without = str(tmp_path / "w.wav"), str(tmp_path / "o.wav")
    _render(src, without, [], pcm_audio=True)
    _render(src, with_sfx, EVENTS, pcm_audio=True)
    assert len(S.pcm(with_sfx)) == len(S.pcm(without))


# --------------------------------------------------------- دقة الوضع

def test_se4_every_effect_lands_on_its_planned_frame(src, tmp_path):
    """
    الطفرة اللي بتفشّلها: استبدال `adelay=NS` بميلي صحيح (±٢٣ عيّنة).

    بأصول **عابرة** بس — أرضية `whoosh`/`riser` بالمئات والآلاف
    لأن ذروتهن مش عند بدايتهن (`test_sfx_floor.py`).
    """
    _require_support()
    with_sfx, without = str(tmp_path / "w.wav"), str(tmp_path / "o.wav")
    _render(src, without, [], pcm_audio=True)
    _render(src, with_sfx, TRANSIENT_EVENTS, pcm_audio=True)

    got = S.hits(S.difference(with_sfx, without))
    assert len(got) == len(TRANSIENT_EVENTS)
    for (frame, name), hit in zip(TRANSIENT_EVENTS, got):
        want = S.frame_to_sample(frame, FPS)
        err = hit - S.detector_floor(name) - want
        assert abs(err) <= 2, \
            f"{name}@{frame}: انزياح {err} عيّنة ({err / S.SR * 1000:.3f}ms)"


def test_se5_placement_error_does_not_accumulate(src, tmp_path):
    """
    `adelay` مطلقة مش متسلسلة، فالانزياح ما بيتراكم **بالبناء**.
    آخر مؤثر لازم يكون بنفس دقة أوّلهن.
    """
    _require_support()
    with_sfx, without = str(tmp_path / "w.wav"), str(tmp_path / "o.wav")
    _render(src, without, [], pcm_audio=True)
    _render(src, with_sfx, TRANSIENT_EVENTS, pcm_audio=True)

    got = S.hits(S.difference(with_sfx, without))
    errs = [h - S.detector_floor(n) - S.frame_to_sample(f, FPS)
            for (f, n), h in zip(TRANSIENT_EVENTS, got)]
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
    with_sfx, without = str(tmp_path / "w.wav"), str(tmp_path / "o.wav")
    _render(src, without, [], pcm_audio=True)
    _render(src, with_sfx, [(60, "pop")], pcm_audio=True)
    got = S.hits(S.difference(with_sfx, without))
    assert len(got) == 1
    err = got[0] - S.detector_floor("pop") - S.frame_to_sample(60, FPS)
    assert abs(err) <= 2, f"انزياح {err} — غالبًا `all=1` ناقصة"


def test_se7_a_44100hz_asset_lands_correctly(src, tmp_path):
    """
    الطفرة اللي بتفشّلها: شيل `aformat=sample_rates=…`. مقيس:
    +٤٢٤٥ عيّنة = **+٨٨ms**، بلا أي تحذير.

    أصول المستودع كلها 48k، فمنولّد أصلًا 44.1k عمدًا — بدونه هالفحص
    ما بيفحص شي.
    """
    _require_support()
    odd = str(tmp_path / "odd_44100.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", S.asset("pop"),
                    "-ar", "44100", "-c:a", "pcm_s16le", odd], check=True)
    assert S.wav_info(odd)[2] == 44100
    with_sfx, without = str(tmp_path / "w.wav"), str(tmp_path / "o.wav")
    _render(src, without, [], pcm_audio=True)
    _render(src, with_sfx, [(60, odd)], pcm_audio=True)
    got = S.hits(S.difference(with_sfx, without))
    assert len(got) == 1
    err = got[0] - S.frame_to_sample(60, FPS)
    assert abs(err) <= 60, f"انزياح {err} عيّنة — غالبًا `aformat` ناقصة"


# ------------------------------------------------------ E2 ما انكسر

def test_se8_source_audio_sync_is_untouched(src, tmp_path, plan):
    """
    **الحارس اللي ما بينتنازل عنه.** نقرات المصدر لازم تطلع بنفس
    المواقع بالضبط مع المؤثرات وبدونهن. أي فرق = المؤثرات حرّكت
    الكلام، وهاد بيلغي كل مكسب المرحلة ٦.
    """
    _require_support()
    from measure.clicks import click_times
    a, b = str(tmp_path / "a.mp4"), str(tmp_path / "b.mp4")
    _render(src, a, [])
    _render(src, b, EVENTS)
    assert click_times(a) == click_times(b), "تزامن الكلام اتغيّر"


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

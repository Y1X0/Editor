"""
أرضية أدوات قياس المؤثرات + التحقّق من الأصول.

**هاي بتمرق من هلأ.** بتفحص الأدوات والأصول، مش الميزة — الميزة لسا
ما انبنت. الفحوص اللي بتفحص الميزة بـ`test_sfx_acceptance.py` ولازم
**تفشل** لحد ما تنبنى.

الدرس اللي فرض وجود هالملف: بمرحلة سابقة طلع فحص بيقول `0/0 ✅` —
نجح وهو ما فحص ولا شي. أداة قياس بلا أرضية موثّقة مش أداة.
"""
import hashlib
import os
import subprocess
import sys

import pytest

from measure import ffmpeg_available
from measure import sfx as S

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER = os.path.join(REPO, "assets", "sfx", "build_assets.py")


# ------------------------------------------------------ الأصول والترخيص

def test_all_five_assets_exist():
    missing = [n for n in S.ASSETS if not os.path.exists(S.asset(n))]
    assert not missing, f"أصول ناقصة: {missing}"


@pytest.mark.parametrize("name", S.ASSETS)
def test_asset_is_wav_48k_stereo_pcm16(name):
    """الصيغة المتفق عليها. أي انحراف بيرجّع فخّ `aformat` المقاس."""
    ch, bits, sr, nframes = S.wav_info(S.asset(name))
    assert (ch, bits, sr) == (2, 16, 48000), \
        f"{name}: {ch}ch/{bits}b/{sr}Hz — المطلوب 2ch/16b/48000Hz"
    assert nframes > 0


@pytest.mark.parametrize("name", S.ASSETS)
def test_asset_has_headroom_and_no_clipping(name):
    """
    ذروة ≤٠.٩٠ شرط الهامش: ٠.٧٠ (كلام مطبَّع) + ٠.٩٠×٠.٢٥ = ٠.٩٢٥ < ١.
    `riser` ذروته ٠.٨١٩ — انحراف مقاس وموثّق بـassets/sfx/README.md،
    وهو **أخفض** فما بيكسر الحدّ.
    """
    peak = S.peak_of(S.asset(name))
    assert 0.5 <= peak <= 0.901, f"{name}: ذروة {peak:.4f}"
    assert S.clipped(S.asset(name)) == 0, f"{name}: فيه عيّنات مقصوصة"


def test_the_headroom_arithmetic_actually_holds():
    """الحدّ مش ادعاءً: أعلى ذروة × ٠.٢٥ + ٠.٧٠ لازم تضل تحت ١.٠"""
    worst = max(S.peak_of(S.asset(n)) for n in S.ASSETS)
    assert 0.70 + worst * 0.25 < 1.0, f"أعلى ذروة {worst:.4f} بتكسر الهامش"


def test_assets_are_byte_reproducible_from_the_builder():
    """
    مصدر الأصول هو السكربت. لو إعادة التوليد ما أعطت نفس البايتات،
    فإما السكربت تغيّر أو سلوك `random` تغيّر — والاتنين قرار مش قبول.
    """
    before = {n: hashlib.sha256(open(S.asset(n), "rb").read()).hexdigest()
              for n in S.ASSETS}
    r = subprocess.run([sys.executable, BUILDER], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    after = {n: hashlib.sha256(open(S.asset(n), "rb").read()).hexdigest()
             for n in S.ASSETS}
    diff = [n for n in before if before[n] != after[n]]
    assert not diff, f"الأصول اتغيّرت بإعادة التوليد: {diff}"


def test_assets_are_acoustically_distinct():
    """
    خمس أصول متطابقة بتخلّي كل فحوص الوضع تنجح وهي ما بتميّز شي.
    معدّل عبور الصفر تقريب رخيص لمركز الطيف.
    """
    zc = {}
    for n in S.ASSETS:
        s = S.pcm(S.asset(n))
        crossings = sum(1 for i in range(1, len(s)) if (s[i - 1] < 0) != (s[i] < 0))
        zc[n] = crossings / (len(s) / S.SR) / 2
    buckets = {round(v / 50) for v in zc.values()}
    assert len(buckets) == len(S.ASSETS), f"في أصول متشابهة طيفيًا: {zc}"


# --------------------------------------------------------- أرضية الكاشف

# الأرضية **مش رقمًا واحدًا** — هاي نتيجة مقاسة صدمتنا أول مرة.
#
# الكاشف بيرجّع أول عيّنة بتوصل ٣٥٪ من الذروة. لما تكون ذروة الصوت
# عند بدايته هاد ≈ البداية. بس `whoosh` ذروته بالنص و`riser` ذروته
# بالآخر — فالأرضية بتصير ضخمة:
#
#     أصل      موقع الذروة   الأرضية
#     tick          2%            9
#     pop           2%           10
#     impact        1%           32
#     whoosh       52%         4609   (٩٦ms)
#     riser        99%        35973   (٧٤٩ms)
#
# **مش خلل بالأداة — هاد شكل الصوت.** صعود ذروته بالآخر ما إله
# "بداية حادة" أصلًا. والنتيجة على تصميم الفحوص:
#
#   * قياس **دقة الوضع** بينعمل بأصول عابرة (tick/pop/impact) —
#     أرضيتهن ≤٣٢ عيّنة يعني ≤٠.٧ms.
#   * الأصول الصاعدة بتنقاس بأرضيتها الخاصة، وبتضل صالحة لأنها
#     ثابتة ومحسوبة لكل أصل — بس بدقة أخشن بكتير.
TRANSIENT = ("tick", "pop", "impact")
SWELL = ("whoosh", "riser")


@pytest.mark.parametrize("name", TRANSIENT)
def test_transient_assets_have_a_tight_detector_floor(name):
    """الأصول العابرة هي اللي بتنقاس فيها دقة الوضع، فأرضيتها لازم تضل ضيّقة."""
    f = S.detector_floor(name)
    assert 0 <= f <= 64, f"{name}: أرضية {f} عيّنة ({f / S.SR * 1000:.2f}ms)"


@pytest.mark.parametrize("name", SWELL)
def test_swell_assets_have_a_large_but_stable_floor(name):
    """
    الأصول الصاعدة أرضيتها كبيرة — وهاد متوقَّع وموثّق. المهم إنها
    **ثابتة**، لأنها بتنطرح من القياس. لو تغيّرت بلا ما ننتبه بتصير
    نتائج الوضع منزاحة بصمت.
    """
    f = S.detector_floor(name)
    assert f > 64, f"{name}: أرضية {f} — صار عابرًا؟ راجع التصنيف"
    assert f == S.detector_floor(name), "الأرضية مش حتمية"
    assert f < S.wav_info(S.asset(name))[3], "الأرضية أطول من الأصل نفسه"


def test_the_difference_signal_isolates_the_effect(tmp_path):
    """
    حجر الأساس: الفرق بين تشغيلتين = المؤثر لحاله.

    منركّب الحالة يدويًا — سرير فيه "كلام" عالي، ومؤثر واحد بمكان
    معروف — ومنتأكد إن `hits` بتلاقيه على الفرق بينما بتضيع لو
    قِسنا المخرَج مباشرة.
    """
    speech = str(tmp_path / "speech.wav")
    plain = str(tmp_path / "plain.wav")
    mixed = str(tmp_path / "mixed.wav")
    run = lambda a: subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + a,
                                   capture_output=True, text=True, check=True)
    run(["-f", "lavfi", "-i", f"sine=frequency=300:sample_rate={S.SR}:duration=3",
         "-af", "volume=8", "-ac", "2", "-c:a", "pcm_s16le", speech])
    run(["-i", speech, "-c:a", "pcm_s16le", plain])
    at = S.frame_to_sample(45, 30)
    fmt = f"aformat=sample_rates={S.SR}:channel_layouts=stereo"
    run(["-i", speech, "-i", S.asset("pop"), "-filter_complex",
         f"[1:a]{fmt},volume=0.25,adelay={at}S:all=1[s];[0:a]{fmt}[b];"
         f"[b][s]amix=inputs=2:duration=first:normalize=0[a]",
         "-map", "[a]", "-c:a", "pcm_s16le", mixed])

    got = S.hits(S.difference(mixed, plain))
    assert len(got) == 1, f"المفروض مؤثر واحد، لقينا {len(got)}"
    err = got[0] - S.detector_floor("pop") - at
    assert abs(err) <= 2, f"انزياح {err} عيّنة"

    # وللمقارنة: الكشف المباشر على المخرَج بيغرق بالكلام
    direct = S.hits([abs(v) for v in S.pcm(mixed)])
    assert len(direct) > 5, ("الكشف المباشر المفروض يغرق بالكلام — "
                             "لو ما غرق فالسرير مش شبه كلام وهالفحص فقد معناه")


def test_frame_to_sample_is_exact_integer_math():
    assert S.frame_to_sample(0, 30) == 0
    assert S.frame_to_sample(1, 30) == 1600
    assert S.frame_to_sample(180, 30) == 288000
    assert S.frame_to_sample(50, 25) == 96000
    with pytest.raises(AssertionError):
        S.frame_to_sample(1, 29)          # ٤٨٠٠٠ ما بتنقسم على ٢٩

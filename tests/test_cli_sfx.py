"""
وصل المؤثرات بالـCLI — **المسار الإنتاجي من طرف لطرف**.

`test_sfx_acceptance.py` بتنادي `render.build_output` مباشرة، فبتفحص
الرندر بس. هون منشغّل `cli.main` الحقيقي: قراءة الconfig، بناء الخطة،
تمريرها للرندر. الفجوة بينهن حقيقية — طفّرنا `cues=None` عند نداء
`build_output` من `cli` وما فشل ولا فحص، لأن ما كان في فحص بيمرق من
هون أصلًا.
"""
import json
import os
import subprocess
import sys

import pytest

from measure import build_source, count_frames, ffmpeg_available
from measure import sfx as S
from measure.pipeline import shrink_config, write_srt

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود"),
]

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 30
CUES = [(1.0, 2.2, "كلمة تانية تالتة"),
        (3.5, 4.9, "رابعة خامسة سادسة"),
        (6.0, 7.4, "سابعة تامنة تاسعة"),
        (9.0, 10.5, "عاشرة حادية تانية")]


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    return build_source(tmp_path_factory.mktemp("clisfx"),
                        width=320, height=568, fps=FPS, nframes=420)


def _run(src, out, extra=(), cfg_patch=None):
    d = os.path.dirname(out)
    cfg = shrink_config(os.path.join(d, "config.json"), 360, 640)
    if cfg_patch:
        raw = json.loads(open(cfg, encoding="utf-8").read())
        raw.setdefault("sfx", {}).update(cfg_patch)
        open(cfg, "w", encoding="utf-8").write(
            json.dumps(raw, ensure_ascii=False))
    srt = write_srt(os.path.join(d, "in.srt"), CUES)
    r = subprocess.run(
        [sys.executable, "-m", "autoreel.cli", str(src["path"]),
         "--srt", str(srt), "-c", str(cfg), "-o", str(out), *extra],
        cwd=REPO, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"{r.stdout[-1500:]}\n{r.stderr[-1500:]}"
    return r


def test_sfx_are_off_by_default(src, tmp_path):
    """
    الافتراضي مطفي: ميزة جديدة ما بتغيّر صوت كل ريل موجود بلا طلب.

    وهاد مش تفضيلًا — تشغيلها افتراضيًا **كسر E2 فعلًا**: الكاشف عدّ
    مؤثرًا كنقرة مصدر (٩ بدل ٨).
    """
    r = _run(src, str(tmp_path / "out.mp4"))
    assert "مؤثر صوتي" not in r.stdout, r.stdout


def test_the_sfx_flag_actually_puts_effects_in_the_output(src, tmp_path):
    """
    **حارس الوصل.** التشغيلة بتنجح حتى لو الخطة طلعت فاضية، فنجاح
    الأمر ما بيثبت شي. القياس على المخرَج هو اللي بيثبت.

    وهاد بالضبط اللي مسك باگًا حقيقيًا: `--sfx` كانت بتشغّل الفرع بس
    `plan_cues` بترجّع فاضي لأنها بتقرا `enabled: false` من نفس
    الconfig. الأمر نجح، وما في مؤثر ولا واحد.
    """
    off = str(tmp_path / "off.mp4")
    on = str(tmp_path / "on.mp4")
    _run(src, off)
    r = _run(src, on, extra=("--sfx",))
    assert "مؤثر صوتي" in r.stdout, r.stdout

    assert count_frames(on) == count_frames(off)
    a, b = S.pcm(off), S.pcm(on)
    assert len(a) == len(b), "طول الصوت اتغيّر"

    gain = S.estimate_gain(on, off)
    assert 0.6 < gain < 0.8, f"كسب الكلام {gain:.4f} برّا المتوقَّع"
    diff = S.difference(on, off, gain=gain)
    assert max(diff) > 0.01, "الأمر نجح بس ما في ولا مؤثر بالمخرَج"
    assert S.clipped(on) == 0


def test_no_sfx_overrides_the_config(src, tmp_path):
    off = str(tmp_path / "a.mp4")
    forced = str(tmp_path / "b.mp4")
    _run(src, off)
    r = _run(src, forced, extra=("--no-sfx",), cfg_patch={"enabled": True})
    assert "مؤثر صوتي" not in r.stdout, r.stdout
    assert max(S.difference(forced, off)) < 1e-6, "المؤثرات نزلت رغم --no-sfx"


def test_each_distinct_asset_is_opened_exactly_once(src, tmp_path):
    """
    مدخَل لكل **أصل مميّز**، مش لكل مؤثر. `asplit` بتغطي التكرار —
    مقيس إنه بيوفّر ٣٤–٣٨٪ ذاكرة ووقت عند ٢٠٠ مؤثر.

    الفحص على الأمر المطبوع: عدد `-i` لملفات الأصول = عدد الأصول
    المميّزة، مهما تكرّرت استعمالاتها.
    """
    r = _run(src, str(tmp_path / "d.mp4"), extra=("--sfx", "--dry-run"))
    cmd = [l for l in r.stdout.splitlines() if l.startswith("$ ffmpeg")]
    assert cmd, r.stdout[-1500:]
    assets = [w for w in cmd[0].split() if "assets/sfx/" in w]
    assert assets, "ولا أصل انمرّر للأمر"
    assert len(assets) == len(set(assets)), \
        f"أصل انفتح أكتر من مرة: {assets}"

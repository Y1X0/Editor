"""
إدارة الألوان — HLG/PQ ‏BT.2020 -> SDR BT.709، والوسم الكاذب.

**الحادثة:** أول لقطة آيفون حقيقية طلعت `hevc · yuv420p10le ·
bt2020nc/bt2020/arib-std-b67` — يعني HLG بعشر بتّات، وهاي **إعدادات
الآيفون الافتراضية** مش حالة نادرة. المسار كان بيمرّرها بلا ولا فلتر
ألوان، فالتشبّع بينزل ٣٤٪.

**والأخطر إن ffmpeg بينسخ وسوم المصدر للمخرَج.** فالنتيجة ملف H.264
ثمان بتّات موسوم `bt2020/arib-std-b67`: بيدّعي HDR وجوّاه بايتات ما
انتحوّلت. وهاد أسوأ من غياب الوسم — **المشغّل بيقرّر**، فنفس الملف
بيطلع غير عند كل مشاهد وما بتقدر تعيد إنتاج الشكوى.

القاعدة اللي بتنفحص هون: **أي وسم على المخرَج لازم يكون صحيحًا عن
محتواه** — بالاتجاهين. منوسم `bt709` لأننا حوّلنا، وما منوسم محتوى
ما لمسناه.
"""
import json
import os
import subprocess

import pytest

from measure import ffmpeg_available, run_ffmpeg

from autoreel import cuts as C
from autoreel import graph as G
from autoreel import render as R

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------- مصادر

def _sdr(path, size="320x180", dur=1):
    run_ffmpeg(["-f", "lavfi", "-i", f"smptehdbars=size={size}:rate=30:duration={dur}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12",
                "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
                "-color_trc", "bt709", "-colorspace", "bt709", str(path)])
    return str(path)


def _hlg(path, sdr_src):
    """نفس محتوى `sdr_src` بس بـHLG/BT.2020/عشر بتّات — زي الآيفون."""
    run_ffmpeg(["-i", str(sdr_src), "-vf",
                "zscale=t=bt709:npl=100,zscale=t=linear,"
                "zscale=p=bt2020:t=arib-std-b67:m=bt2020nc:r=tv,format=yuv420p10le",
                "-c:v", "libx265", "-preset", "ultrafast", "-crf", "12",
                "-tag:v", "hvc1", "-color_primaries", "bt2020",
                "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc", str(path)])
    return str(path)


def _untagged(path):
    run_ffmpeg(["-f", "lavfi", "-i", "smptehdbars=size=320x180:rate=30:duration=1",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-color_primaries", "unspecified", "-color_trc", "unspecified",
                "-colorspace", "unspecified", str(path)])
    return str(path)


@pytest.fixture(scope="module")
def srcs(tmp_path_factory):
    d = tmp_path_factory.mktemp("color")
    sdr = _sdr(d / "sdr.mp4")
    return {"sdr": sdr, "hlg": _hlg(d / "hlg.mov", sdr),
            "untagged": _untagged(d / "untagged.mp4"), "dir": d}


# ----------------------------------------------------------- C1: الكشف

def test_the_colour_tags_are_read_from_the_same_single_call(srcs):
    """
    **ولا نداء إضافي ولا `ffprobe`.** سطر التيار بـ`ffmpeg -i` فيه
    الوسوم أصلًا، فقاعدة PR-1 ما بتنمسّ.
    """
    hlg = C.probe(srcs["hlg"])[4]
    assert hlg["hdr"] is True
    assert hlg["trc"] == "arib-std-b67"
    assert hlg["primaries"] == "bt2020"
    assert hlg["bits"] == 10

    sdr = C.probe(srcs["sdr"])[4]
    assert sdr["hdr"] is False and sdr["trc"] == "bt709" and sdr["bits"] == 8

    un = C.probe(srcs["untagged"])[4]
    assert un["hdr"] is False, "بلا وسوم ≠ HDR"
    assert un["trc"] is None, "«ما بنعرف» لازم تكون None مش bt709"


def test_reading_the_colour_tags_adds_no_call_to_probe():
    """
    حارس: قراءة الألوان ما بتضيف نداءً **جوّا `probe`**.

    الفحص على `probe` نفسها مش على عدد النداءات بالملف — `cuts.py`
    فيها نداءات تانية مقصودة (`ffmpeg_version`، `delivered`)، وعدّها
    بيخلّي الفحص يفشل عند أي إضافة مشروعة بدل ما يحمي القاعدة.

    **وهاد صار فعلًا:** الصيغة الأولى كانت `len(runs) == 2` وفشلت لما
    `delivered` انضافت — رقم سحري بيقيس الملف مش القاعدة.
    """
    import ast
    src = open(os.path.join(ROOT, "autoreel", "cuts.py"), encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "probe")
    runs = [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "run"]
    assert len(runs) == 1, f"`probe` صار فيها {len(runs)} نداء بدل واحد"


# ------------------------------------------------- C2: التشبّع بينسترجع

def _sat(png):
    from PIL import Image
    import colorsys
    im = Image.open(png).convert("RGB")
    d = list(im.getdata())
    return sum(colorsys.rgb_to_hsv(*[c / 255 for c in p])[1] for p in d) / len(d)


def _render(src, out, sizes="wide"):
    srt = os.path.join(os.path.dirname(out), "s.srt")
    with open(srt, "w", encoding="utf-8") as f:
        f.write("1\n00:00:00,100 --> 00:00:00,800\nكلمة تانية\n\n")
    r = subprocess.run(
        ["python", "-m", "autoreel.cli", src, "--srt", srt, "--sizes", sizes,
         "--no-captions", "-o", out],
        cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    return out


def test_hlg_keeps_its_saturation_through_the_pipeline(srcs, tmp_path):
    """
    **C2.** نفس المحتوى من مصدرين — SDR وHLG — لازم يطلع بنفس التشبّع.
    قبل الإصلاح كان الفرق ‎−٣٤.٦٪.

    التشبّع مش السطوع: خسارة التشبّع من غياب تحويل BT.2020->709 وهاي
    اللي منصلّحها. السطوع بيتبع `npl` وهو **لسا مش معايَر** — لهيك ما
    في هون تأكيد عليه.
    """
    a = _render(srcs["sdr"], str(tmp_path / "a.mp4"))
    b = _render(srcs["hlg"], str(tmp_path / "b.mp4"))
    pa, pb = str(tmp_path / "a.png"), str(tmp_path / "b.png")
    for src, png in ((a, pa), (b, pb)):
        run_ffmpeg(["-i", src, "-frames:v", "1", png])
    sa, sb = _sat(pa), _sat(pb)
    assert abs(sb - sa) / sa < 0.05, (
        f"تشبّع مخرَج HLG {sb:.3f} مقابل SDR {sa:.3f} — "
        f"فرق {(sb - sa) / sa * 100:+.1f}٪")


# ------------------------------------------------- C3: وسم المخرَج صادق

def _tags(path):
    return C.probe(path)[4]


def test_an_hdr_source_yields_an_honestly_tagged_output(srcs, tmp_path):
    """**C3.** مخرَج من HLG لازم يطلع موسومًا `bt709` — لأننا حوّلناه."""
    out = _render(srcs["hlg"], str(tmp_path / "o.mp4"))
    t = _tags(out)
    assert t["trc"] == "bt709" and t["primaries"] == "bt709"
    assert t["bits"] == 8


def test_the_output_never_claims_hdr_at_eight_bits(srcs, tmp_path):
    """**الحارس الأساسي.** ولا مصدر بيطلّع مخرَجًا ٨ بتّات بيدّعي HDR."""
    for key in ("hlg", "sdr", "untagged"):
        out = _render(srcs[key], str(tmp_path / f"{key}.mp4"))
        t = _tags(out)
        claimed = " ".join(str(t.get(k)) for k in ("primaries", "matrix", "trc"))
        for bad in R.FORBIDDEN_TAGS:
            assert bad not in claimed, f"مخرَج من {key} موسوم {bad} وهو ٨ بتّات"


def test_a_mislabelled_output_is_refused_and_deleted(tmp_path):
    """
    الحارس بيرمي **وبيحذف**. ملف بشكل مخرَج وهو بوسم كاذب أخطر من
    الفشل، لأنه بينكتشف بعد الرفع.
    """
    bad = tmp_path / "bad.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "smptehdbars=size=320x180:rate=30:duration=1",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-color_primaries", "bt2020", "-color_trc", "arib-std-b67",
                "-colorspace", "bt2020nc", str(bad)])
    assert _tags(str(bad))["trc"] == "arib-std-b67", "المصدر ما طلع موسومًا غلط"
    with pytest.raises(RuntimeError, match="كاذب"):
        R.assert_output_not_mislabelled(str(bad))


def test_a_ten_bit_hdr_file_is_not_flagged(srcs):
    """الحارس على **الكذب** مش على HDR: ملف ١٠ بتّات موسوم HLG صادق."""
    R.assert_output_not_mislabelled(srcs["hlg"])


# ---------------------------------------- C4 · C5: SDR وبلا وسوم بينجوا

def test_an_sdr_source_is_untouched_by_the_colour_path(srcs):
    """
    **C4.** السلسلة ممنوع تنطبّق على SDR. مقيس إنها بتدمّره:
    ‎Y ١٠١.٣ -> ٧٠.٤ عند `npl=1000`.
    """
    assert G.tonemap_chain(C.probe(srcs["sdr"])[4]) == ""


def test_an_untagged_source_gets_no_chain(srcs):
    """
    **C5.** `zscale` بترمي `no path between colorspaces` على مصدر بلا
    وسوم. الشرط بيمنع الحالة قبل ما توصل ffmpeg.
    """
    assert G.tonemap_chain(C.probe(srcs["untagged"])[4]) == ""


def test_an_untagged_source_still_renders(srcs, tmp_path):
    """والمسار كامل بيمرق عليه — مش بس السلسلة بترجع فاضية."""
    out = _render(srcs["untagged"], str(tmp_path / "u.mp4"))
    assert os.path.getsize(out) > 0


def test_the_chain_is_built_for_hdr_and_is_ordered_correctly(srcs):
    """
    الترتيب داخل السلسلة مش تفصيلًا: **`t=linear` قبل `tonemap`**
    إلزامية. بدونها `tonemap` بتشتغل بلا خطأ وبتعطي نتيجة أسوأ من لا
    شي — فخّ صامت.
    """
    ch = G.tonemap_chain(C.probe(srcs["hlg"])[4])
    assert ch, "مصدر HLG لازم ياخد سلسلة"
    assert ch.index("t=linear") < ch.index("tonemap="), "`t=linear` لازم تسبق `tonemap`"
    assert "tin=arib-std-b67" in ch, "المدخل لازم ينعلن صراحة مش ينستنتج"
    assert ch.rstrip().endswith("format=yuv420p")


# ------------------------------------- C6: الكابشن بعد الـtonemap

def test_the_caption_overlay_comes_after_the_tonemap(srcs):
    """
    **C6.** الـtonemapper ما بيميّز بكسل الكابشن عن بكسل المشهد،
    فبيقرا أبيض الكابشن كوميض ١٠٠٠-نِت وبيضغطه (٢٣٥ -> ١٥١ مقيسة مع
    `hable`). فالكابشن لازم ينحط على قاعدة **مطبَّعة**.

    الفحص على بنية الرسم: الـtonemap بالجذع قبل `split`، والoverlay
    بعده بمسافة.
    """
    import json as _json
    cfg = _json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    colors = C.probe(srcs["hlg"])[4]
    graph, _ = G.build_graph(cfg, [30], [0], [("reel", cfg)], 1080, 1920,
                             caption_inputs={"reel": 1}, with_audio=False,
                             colors=colors)
    assert "tonemap=" in graph
    assert graph.index("tonemap=") < graph.index("overlay="), \
        "الـoverlay صار قبل الـtonemap — أبيض الكابشن رح ينسحق"
    # الجذع بينتهي عند `[stem]`، وكل اللي بعده بيستهلكه. فوقوع
    # الـtonemap قبله = مرة وحدة لكل المقاسات.
    # (**مش** `split`: بمقاس واحد `split_chain` بتعطي `null`.)
    assert graph.index("tonemap=") < graph.index("[stem]"), \
        "الـtonemap لازم يكون بالجذع مرة وحدة، قبل توزيع المقاسات"

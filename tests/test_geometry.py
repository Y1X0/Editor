"""
باني سلسلة الفلاتر — `render.segment_filter`.

دالة نقية، فبتنفحص بلا ffmpeg. وهون بينمسك أخطر شي بالهندسة: نافذة
قص بتطلع برّا الإطار، أو محتوى بينقصّ من غير قصد.

الفحص الأساسي `assert_crop_inside`: بيحاكي حسبة ffmpeg للـ`scale` مع
`force_original_aspect_ratio=increase` وبيقيّم تعابير الـ`crop`، وبيتأكد
إن النافذة كلها جوا الإطار المكبّر.
"""
import re

import pytest

from autoreel import render as R

# (اسم، عرض، ارتفاع) — مصادر واقعية
SOURCES = [("عمودي", 1080, 1920), ("عريض", 1920, 1080),
           ("مربع", 1080, 1080), ("عمودي ٤:٥", 1080, 1350)]
TARGETS = [("reel", 1080, 1920), ("square", 1080, 1080), ("wide", 1920, 1080)]


def cfg_for(w, h, pan_px=0, **geometry):
    return {"output": {"width": w, "height": h, "fps": 30, "crf": 19},
            "motion": {"pan_px": pan_px},
            "geometry": geometry}


def scaled(src_w, src_h, sw, sh):
    """أبعاد الإطار بعد scale=sw:sh:force_original_aspect_ratio=increase."""
    k = max(sw / src_w, sh / src_h)
    return round(src_w * k), round(src_h * k)


def parse_crop(vf):
    m = re.search(r"crop=(\d+):(\d+):([^,]+):([^,]+)", vf)
    assert m, f"ما لقينا crop بـ{vf}"
    return int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)


def evaluate(expr, iw, ih):
    """تقييم تعبير crop تبع ffmpeg — بس iw/ih والحساب البسيط."""
    return eval(expr.replace("iw", str(iw)).replace("ih", str(ih)))  # noqa: S307


def assert_crop_inside(vf, src_w, src_h):
    sm = re.search(r"scale=(\d+):(\d+):force_original_aspect_ratio=increase", vf)
    assert sm, f"ما لقينا scale بـ{vf}"
    iw, ih = scaled(src_w, src_h, int(sm.group(1)), int(sm.group(2)))
    cw, ch, xe, ye = parse_crop(vf)
    x, y = evaluate(xe, iw, ih), evaluate(ye, iw, ih)
    assert 0 <= x <= iw - cw, f"x={x} برّا المدى [0,{iw-cw}] · {vf}"
    assert 0 <= y <= ih - ch, f"y={y} برّا المدى [0,{ih-ch}] · {vf}"
    return x, y, iw, ih


# ------------------------------------------------------------------ crop

@pytest.mark.parametrize("sname,sw,sh", SOURCES)
@pytest.mark.parametrize("tname,tw,th", TARGETS)
@pytest.mark.parametrize("zoom", [1.0, 1.04, 1.1, 1.14])
@pytest.mark.parametrize("pan_dir", [-1, 0, 1])
def test_crop_never_leaves_the_frame(sname, sw, sh, tname, tw, th, zoom, pan_dir):
    """كل تركيبة مصدر × هدف × زوم × اتجاه pan."""
    cfg = cfg_for(tw, th, pan_px=26)
    assert_crop_inside(R.segment_filter(cfg, zoom=zoom, pan_dir=pan_dir), sw, sh)


@pytest.mark.parametrize("bias", [0.0, 0.25, 0.38, 0.5, 0.75, 1.0, -3.0, 9.0])
def test_crop_bias_is_clamped_and_ordered(bias):
    """قيم برّا [0,1] بتنحدّ — حتى -3.0 و9.0 بتعطوا نافذة جوا الإطار."""
    vf = R.segment_filter(cfg_for(1080, 1080, crop_bias=bias))
    assert_crop_inside(vf, 1080, 1920)


def test_lower_bias_moves_the_window_up():
    def y_of(b):
        vf = R.segment_filter(cfg_for(1080, 1080, crop_bias=b))
        return assert_crop_inside(vf, 1080, 1920)[1]
    assert y_of(0.0) < y_of(0.38) < y_of(0.5) < y_of(1.0)


def test_default_bias_reproduces_centre_crop():
    """بدون geometry بالconfig لازم يطلع نفس سلوك اليوم بالضبط."""
    vf = R.segment_filter({"output": {"width": 1080, "height": 1920, "fps": 30}})
    _, y, _, ih = assert_crop_inside(vf, 1080, 1920)
    assert y == pytest.approx((ih - 1920) / 2)


def test_bias_038_keeps_the_head_for_square():
    """
    من مصدر 1080×1920 المركز بياخد ٢٢٪–٧٨٪ فبيقصّ أعلى الرأس.
    ٠.٣٨ لازم تنقل النافذة لفوق بشكل ملموس.
    """
    vf = R.segment_filter(cfg_for(1080, 1080, crop_bias=0.38))
    _, y, _, ih = assert_crop_inside(vf, 1080, 1920)
    top_pct = y / ih * 100
    assert top_pct < 22, f"النافذة بتبلّش عند {top_pct:.0f}٪ — ما ارتفعت كفاية"


# -------------------------------------------------------------- pan حدّ

@pytest.mark.parametrize("zoom", [1.0, 1.02, 1.04, 1.1, 1.14])
def test_pan_never_exceeds_the_available_room(zoom):
    """
    الانحدار: pan_px=26 مع زوم ١.٠٤ كان بيطلب x=47 والمدى ٤٢،
    وffmpeg بيقصقصها بصمت فالـpan بيتصرف عشوائي.
    """
    cfg = cfg_for(1080, 1920, pan_px=200)          # أكبر بكتير من أي مدى
    for d in (-1, 1):
        assert_crop_inside(R.segment_filter(cfg, zoom=zoom, pan_dir=d), 1080, 1920)


def test_no_pan_without_zoom():
    cfg = cfg_for(1080, 1920, pan_px=26)
    a = R.segment_filter(cfg, zoom=1.0, pan_dir=1)
    b = R.segment_filter(cfg, zoom=1.0, pan_dir=-1)
    assert a == b                                  # ما في مدى فما في فرق


def test_pan_directions_are_opposite_when_there_is_room():
    cfg = cfg_for(1080, 1920, pan_px=8)
    xr = assert_crop_inside(R.segment_filter(cfg, zoom=1.14, pan_dir=1), 1080, 1920)[0]
    xl = assert_crop_inside(R.segment_filter(cfg, zoom=1.14, pan_dir=-1), 1080, 1920)[0]
    assert xr > xl


def test_offset_is_rendered_without_double_sign():
    """`+-26` كانت تشتغل بس بتربك القراءة بالسجل."""
    vf = R.segment_filter(cfg_for(1080, 1920, pan_px=8), zoom=1.14, pan_dir=-1)
    assert "+-" not in vf and "--" not in vf


# ------------------------------------------------------------------- pad

@pytest.mark.parametrize("sname,sw,sh", SOURCES)
@pytest.mark.parametrize("tname,tw,th", TARGETS)
def test_pad_keeps_the_whole_frame(sname, sw, sh, tname, tw, th):
    """
    المقدّمة لازم تنقاس بـ`decrease` على أبعاد المخرَج بالضبط — يعني
    الإطار كامل بيدخل. `increase` أو القياس على sw×sh بيرجّعوا القصّ.
    """
    vf = R.segment_filter(cfg_for(tw, th, fit="pad"), zoom=1.14)
    assert f"scale={tw}:{th}:force_original_aspect_ratio=decrease" in vf
    assert "force_original_aspect_ratio=increase" in vf      # الخلفية بس


def test_pad_foreground_fits_inside_the_output_frame():
    """حساب فعلي: المقدّمة ما بتتعدى الإطار بأي بُعد."""
    tw, th = 1920, 1080
    for sw, sh in [(1080, 1920), (1080, 1080), (1920, 1080)]:
        k = min(tw / sw, th / sh)
        assert round(sw * k) <= tw and round(sh * k) <= th


def test_pad_blurs_only_the_background():
    vf = R.segment_filter(cfg_for(1920, 1080, fit="pad", pad_blur=30))
    bg = vf.split("[bgb]")[0]
    assert "gblur=sigma=30" in bg
    assert "gblur" not in vf.split("[bgb];")[1]


def test_pad_graph_has_one_in_and_one_out():
    """`-vf` بيقبل رسم بمسمّيات داخلية بشرط مدخل واحد ومخرَج واحد."""
    vf = R.segment_filter(cfg_for(1920, 1080, fit="pad"))
    steps = vf.split(";")
    assert steps[0].startswith("split[")             # ماخد المدخل الضمني
    assert not steps[-1].endswith("]")               # مخرَج ضمني


def test_pad_zoom_moves_the_background_only():
    a = R.segment_filter(cfg_for(1920, 1080, fit="pad"), zoom=1.0)
    b = R.segment_filter(cfg_for(1920, 1080, fit="pad"), zoom=1.14)
    assert a != b                                    # الخلفية بتتحرك
    fg = "scale=1920:1080:force_original_aspect_ratio=decrease"
    assert fg in a and fg in b                       # المقدّمة ثابتة


# ------------------------------------------------------------------- عام

def test_unknown_fit_is_rejected_loudly():
    with pytest.raises(ValueError, match="crop, pad"):
        R.segment_filter(cfg_for(1080, 1920, fit="stretch"))


@pytest.mark.parametrize("fit", ["crop", "pad"])
@pytest.mark.parametrize("zoom", [1.0, 1.04, 1.14])
def test_dimensions_stay_even(fit, zoom):
    """yuv420p بيرفض الأبعاد الفردية."""
    vf = R.segment_filter(cfg_for(1080, 1920, fit=fit), zoom=zoom)
    for w, h in re.findall(r"scale=(\d+):(\d+)", vf):
        assert int(w) % 2 == 0 and int(h) % 2 == 0


@pytest.mark.parametrize("fit", ["crop", "pad"])
def test_fps_and_sar_are_always_set(fit):
    vf = R.segment_filter(cfg_for(1080, 1920, fit=fit))
    assert "fps=30" in vf and "setsar=1" in vf


def test_pan_reads_from_the_real_config_file():
    """
    الانحدار: قراءة `pan_px` انتقلت لقسم `geometry` بينما هو ساكن
    بـ`motion`، فالـpan صار صفر بصمت. الفحوصات اللي فوق ما مسكته لأنها
    بتبني config خاص فيها — فهاد بيقرا `config.json` الحقيقي.
    """
    import json
    from conftest import ROOT
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert cfg["motion"]["pan_px"] > 0, "الconfig نفسه ما فيه pan"

    z = max(cfg["motion"]["zoom_cycle"])            # أوسع مدى متاح
    right = R.segment_filter(cfg, zoom=z, pan_dir=1)
    left = R.segment_filter(cfg, zoom=z, pan_dir=-1)
    assert right != left, "pan_px بالconfig موجود بس ما وصل الفلتر"

    src = (cfg["output"]["width"], cfg["output"]["height"])
    xr = assert_crop_inside(right, *src)[0]
    xl = assert_crop_inside(left, *src)[0]
    assert xr > xl


def test_geometry_defaults_fill_the_gaps():
    """قسم geometry ناقص أو غايب = القيم الافتراضية، مش انفجار."""
    vf = R.segment_filter({"output": {"width": 1080, "height": 1920, "fps": 30}})
    assert "crop=1080:1920:" in vf
    vf2 = R.segment_filter(cfg_for(1080, 1920, crop_bias=0.3))   # fit غايب
    assert "crop=1080:1920:" in vf2

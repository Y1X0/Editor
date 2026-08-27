"""
معامل التكبير من صورة مخرَج، عن طريق تباعد خطوط الشبكة.

**كشف الكتل بعتبة ما بيزبط**، جرّبناه وانكسر مرتين:
  * الخط بينشقّ لكتلتين مع التنعيم -> فروق [26.0, 3.9, 30.1] بدل [30,30,30]
  * صف فيه ضجيج ضغط بيعطي ٤٤ "خط" كلهن وهم
  * وصف بيصادف خط شبكة أفقي بيطلع أبيض كامل -> ولا خط بينكشف

البديل: **مرشّح مطابَق** على بروفايل الصورة كامل — بلا عتبة، بلا كتل،
وبيستعمل كل الإشارة مش قممها. طاقة البروفايل عند دورة p هي
|Σ v(x)·e^{-2πix/p}|، وأعلى p هي التباعد.
"""
import math

from PIL import Image

from .source import GRID_PITCH, PATCH, grid_rows


def _profile(img):
    """متوسط الأعمدة على شريط فوق رقعة الهوية."""
    px = img.load()
    w, h = img.size
    top = max(2, h // 6)
    bot = max(top + 8, h // 2 - PATCH)
    n = bot - top
    return [sum(px[x, y][1] for y in range(top, bot)) / n for x in range(w)]


def _power(v, p):
    w = 2 * math.pi / p
    re_ = sum(val * math.cos(w * x) for x, val in enumerate(v))
    im_ = sum(val * math.sin(w * x) for x, val in enumerate(v))
    return math.hypot(re_, im_)


def measure_scale(img, lo=0.80, hi=2.20):
    """
    معامل المصدر->المخرَج. زوم ١.٠ بيعطي ١.٠ لو المصدر والمخرَج بنفس
    الأبعاد؛ غير هيك قارنه بـ`expected_scale`.
    """
    if isinstance(img, str):
        img = Image.open(img)
    img = img.convert("RGB")
    v = _profile(img)
    plo, phi = GRID_PITCH * lo, GRID_PITCH * hi
    best, bp = -1.0, plo
    p = plo
    while p <= phi:                      # مسح خشن
        s = _power(v, p)
        if s > best:
            best, bp = s, p
        p += 0.05
    best, fine = -1.0, bp
    p = bp - 0.06
    while p <= bp + 0.06:                # مسح ناعم حوالين القمة
        s = _power(v, p)
        if s > best:
            best, fine = s, p
        p += 0.001
    return fine / GRID_PITCH


def expected_scale(src_w, src_h, out_w, out_h, zoom):
    """
    المعامل اللي بينفّذه `render.segment_filter` فعلًا — مش `zoom`.

    الأبعاد بتتقرّب لزوجي (`_even`)، و
    `force_original_aspect_ratio=increase` بتاخد **الأكبر** من نسبتي
    التغطية. النتيجة بتفترق عن `zoom` بأجزاء الألف، وهاي الأجزاء أوسع
    من دقّة الأداة فلازم تنحسب مش تنتجاهل.
    """
    sw, sh = int(out_w * zoom / 2) * 2, int(out_h * zoom / 2) * 2
    return max(sw / src_w, sh / src_h)

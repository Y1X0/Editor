"""
المرحلة ٠ — أداة القياس أولًا، ومتحقَّق منها.

مصدر بشبكة خطوط بتباعد معروف. الزوم z بيكبّر المصدر لـ(W·z, H·z) وبياخد
نافذة W×H، فتباعد الخطوط بالمخرَج = التباعد الأصلي × z. قراءة التباعد
بترجّع الزوم مباشرة.

**كشف الكتل بعتبة ما زبط** (المحاولة الأولى): الخط بينشقّ لكتلتين مع
التنعيم (فروق [26.0, 3.9, 30.1] بدل [30, 30, 30])، وصف فيه ضجيج ضغط
بيعطي ٤٤ "خط" كلهن وهم. البديل: **مرشّح مطابَق** على البروفايل كامل —
بلا عتبة، بلا كتل، وبيستعمل كل الإشارة مش قممها.
"""
import subprocess, os, re, math
from PIL import Image, ImageDraw

FPS = 30
SW, SH = 540, 960
W, H = 540, 960
PITCH = 24
DUR = 20
SRC = "/tmp/realrun/grid.mp4"
_TMP = "/tmp/realrun/_z"


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def frames(p):
    f = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', p, '-f', 'null', '-'], text=True).stderr)
    return int(f[-1]) if f else None


def make_source():
    img = Image.new("RGB", (SW, SH), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for x in range(0, SW, PITCH):
        d.line([(x, 0), (x, SH)], fill=(255, 255, 255), width=1)
    for y in range(0, SH, PITCH):
        d.line([(0, y), (SW, y)], fill=(255, 255, 255), width=1)
    p = "/tmp/realrun/grid.png"
    img.save(p)
    sh(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-framerate', str(FPS),
        '-t', str(DUR), '-i', p,
        '-f', 'lavfi', '-i', f'sine=frequency=440:duration={DUR}:sample_rate=48000',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '12',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', SRC], check=False)


def profile(img):
    """متوسط الأعمدة على شريط أوسط — الخطوط الأفقية بتضيف ثابت وبس."""
    px = img.load()
    y0, y1 = img.height // 4, 3 * img.height // 4
    n = y1 - y0
    return [sum(px[x, y][1] for y in range(y0, y1)) / n for x in range(img.width)]


def _power(v, p):
    """|Σ v(x)·e^{-2πix/p}| — طاقة البروفايل عند الدورة p."""
    re_, im_ = 0.0, 0.0
    w = 2 * math.pi / p
    for x, val in enumerate(v):
        re_ += val * math.cos(w * x)
        im_ -= val * math.sin(w * x)
    return math.hypot(re_, im_)


def fit_pitch(v, lo, hi):
    """أفضل دورة بين lo و hi: مسح خشن ثم ناعم حوالين القمة."""
    best, bp = -1.0, lo
    p = lo
    while p <= hi:
        s = _power(v, p)
        if s > best:
            best, bp = s, p
        p += 0.05
    best, bp2 = -1.0, bp
    p = bp - 0.06
    while p <= bp + 0.06:
        s = _power(v, p)
        if s > best:
            best, bp2 = s, p
        p += 0.001
    return bp2


def grab(path, frame_idx, out_png):
    sh(['ffmpeg', '-y', '-v', 'error', '-i', path,
        '-vf', f'select=eq(n\\,{frame_idx})', '-vsync', '0',
        '-frames:v', '1', out_png])
    return os.path.exists(out_png)


def measure_zoom(path, frame_idx, lo=0.85, hi=1.45):
    os.makedirs(_TMP, exist_ok=True)
    f = f"{_TMP}/_m_{os.getpid()}.png"
    if os.path.exists(f):
        os.remove(f)
    if not grab(path, frame_idx, f):
        return None
    v = profile(Image.open(f).convert("RGB"))
    return fit_pitch(v, PITCH * lo, PITCH * hi) / PITCH


def real_zoom(z, w=W, h=H, sw_src=SW, sh_src=SH):
    """
    الزوم الفعلي اللي بينفّذه فلتر الإنتاج، مش z المطلوب.

    `scale=sw:sh:force_original_aspect_ratio=increase` بتاخد **الأكبر**
    من نسبتي التغطية، والتقريب لزوجي بيكسر النسبة شوي — فمثلًا z=1.25
    بتعطي معامل ١.٢٥٠٠ مش ٦٧٤/٥٤٠=١.٢٤٨١.
    """
    sw, sh_ = int(w * z / 2) * 2, int(h * z / 2) * 2
    return max(sw / sw_src, sh_ / sh_src)


if __name__ == "__main__":
    os.makedirs(_TMP, exist_ok=True)
    if not os.path.exists(SRC):
        make_source()
    print(f"المصدر: {frames(SRC)} إطار · {SW}×{SH} · تباعد {PITCH}px\n")
    print("تحقّق الأداة على زوم معروف (نفس فلتر الإنتاج بالضبط):")
    worst = 0.0
    for z in (1.0, 1.04, 1.10, 1.14, 1.25, 1.40):
        sw, sh_ = int(W * z / 2) * 2, int(H * z / 2) * 2
        vf = (f"scale={sw}:{sh_}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H}:(iw-{W})/2:(ih-{H})*0.5000,fps={FPS},setsar=1")
        out = f"{_TMP}/k{z}.mp4"
        sh(['ffmpeg', '-y', '-v', 'error', '-t', '1', '-i', SRC, '-vf', vf,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '12',
            '-pix_fmt', 'yuv420p', out])
        got = measure_zoom(out, 5)
        rz = real_zoom(z)
        err = abs(got - rz) if got else 99
        worst = max(worst, err)
        print(f"   z={z:<5} (فعليًا {rz:.4f})  ->  مقيس {got:.4f}   خطأ {err:.4f}"
              f"  {'✅' if err < 0.004 else '❌'}")
    print(f"\nأسوأ خطأ = {worst:.4f} — "
          + ("✅ الأداة موثوقة" if worst < 0.004 else "❌ الأداة مش موثوقة، وقّف"))

"""
مصدر اختبار بيحمل **تلات إشارات** بنفس الملف:

  ١. شبكة خطوط بتباعد معروف        -> قياس معامل التكبير (zoom)
  ٢. رقعة لون بالوسط = رقم الإطار  -> هوية الإطار (إسقاط/تكرار/ترتيب)
  ٣. نقرات صوتية بأزمنة معروفة     -> انزياح الصوت

ليش الثلاثة سوا: الثوابت لازم تنقاس **بنفس التشغيلة**. لو قِسنا الزوم
بملف والصوت بملف تاني، بنكون أثبتنا إنهن بيزبطوا لحالهن، مش إنهن
بيزبطوا مع بعض — وهاد بالضبط اللي بينكسر بالتكامل.

**ليش رقعة لون مش باركود:** قارئ الباركود بده يحسب مكان الشريط بالمخرَج
من هندسة القص (زوم + pan + bias)، فبيصير مربوطًا بالشي اللي عم يفحصه.
رقعة لون كبيرة بالوسط بتنقرا من أي بكسل جواتها: بلا حساب هندسي، وبلا
افتراض عن الزوم.
"""
import array
import math
import os

from PIL import Image, ImageDraw

from .probe import run_ffmpeg

SR = 48000
GRID_PITCH = 24          # تباعد خطوط الشبكة بالمصدر (px)
PATCH = 120              # ضلع رقعة الهوية (px) — بتنجى بأي زوم معقول
CLICK_EVERY = 0.5        # ثانية
CLICK_MS = 2

# ألوان الهوية: ١٢ درجة لكل قناة بخطوة ٢٠ -> ١٧٢٨ إطار (٥٧s @30fps).
# خطوة ٢٠ واسعة عشان تنجى من الترميز الخاسر؛ خطوة أضيق بتخلط الألوان
# عند crf عالي وبيصير "إطار مكرر" وهمي.
_LEVELS = 12
_STEP = 20
_BASE = 30
ID_CAPACITY = _LEVELS ** 3


def id_color(n):
    """لون فريد لكل رقم إطار."""
    if not 0 <= n < ID_CAPACITY:
        raise ValueError(f"رقم الإطار {n} برّا سعة الهوية ({ID_CAPACITY})")
    return tuple(_BASE + ((n // _LEVELS ** k) % _LEVELS) * _STEP for k in range(3))


def _grid(w, h):
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for x in range(0, w, GRID_PITCH):
        d.line([(x, 0), (x, h)], fill=(255, 255, 255), width=1)
    for y in range(0, h, GRID_PITCH):
        d.line([(0, y), (w, y)], fill=(255, 255, 255), width=1)
    return img


def patch_box(w, h):
    """مستطيل رقعة الهوية (يسار، فوق، يمين، تحت) بإحداثيات المصدر."""
    return (w // 2 - PATCH // 2, h // 2 - PATCH // 2,
            w // 2 + PATCH // 2, h // 2 + PATCH // 2)


def grid_rows(h):
    """صفوف صالحة لقياس الشبكة: فوق رقعة الهوية، وبعيد عن الحواف."""
    top = h // 2 - PATCH // 2
    return range(max(4, top // 3), max(5, top - 8))


def _click_track(nframes, fps, path):
    n = int(SR * nframes / fps)
    a = array.array("h", bytes(2 * n))
    times, t = [], 0.0
    width = int(SR * CLICK_MS / 1000)
    while True:
        i0 = round(t * SR)
        if i0 + width >= n:
            break
        for j in range(width):
            a[i0 + j] = 32000 if j % 2 == 0 else -32000
        times.append(t)
        t += CLICK_EVERY
    with open(path, "wb") as f:
        f.write(a.tobytes())
    return times


def build_source(outdir, width=640, height=1138, fps=30, nframes=600, crf=10):
    """
    يبني `<outdir>/source.mp4` ويرجّع dict فيه كل الحقائق المعروفة عنه.

    البناء بيرسم الشبكة **مرة وحدة** وبيلصق رقعة الهوية لكل إطار — رسم
    الشبكة ٦٠٠ مرة بياخد أضعاف الوقت بلا داعي.
    """
    if nframes > ID_CAPACITY:
        raise ValueError(f"{nframes} إطار > سعة الهوية {ID_CAPACITY}")
    os.makedirs(outdir, exist_ok=True)
    src = os.path.join(str(outdir), "source.mp4")
    frames_dir = os.path.join(str(outdir), "_srcframes")
    os.makedirs(frames_dir, exist_ok=True)

    base = _grid(width, height)
    box = patch_box(width, height)
    for n in range(nframes):
        img = base.copy()
        ImageDraw.Draw(img).rectangle(box, fill=id_color(n))
        img.save(os.path.join(frames_dir, f"{n:06d}.png"))

    raw = os.path.join(str(outdir), "_clicks.raw")
    click_at = _click_track(nframes, fps, raw)

    run_ffmpeg(["-framerate", str(fps), "-start_number", "0",
                "-i", os.path.join(frames_dir, "%06d.png"),
                "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", raw,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", str(SR),
                "-shortest", src])
    return {
        "path": src, "width": width, "height": height, "fps": fps,
        "nframes": nframes, "click_at": click_at, "pitch": GRID_PITCH,
    }

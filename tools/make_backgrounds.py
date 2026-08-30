"""خلفيات مرسومة بـPIL — تحكّم كامل وتحقّق بصري بكل خطوة. ملف مؤقت."""
import math, random, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

W, H = 1620, 2880                     # عمودي 9:16، أكبر ١.٥× من الهدف لغرفة الزحف
A = Path(sys.argv[1])

def grad(top, bot, cx=0.5, cy=0.35, glow=None):
    """تدرّج رأسي + هالة ناعمة. الألوان بالضبط اللي بدي إياها."""
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)],
               fill=tuple(round(top[i] + (bot[i]-top[i]) * t) for i in range(3)))
    if glow:
        g = Image.new("L", (W, H), 0)
        gd = ImageDraw.Draw(g)
        r = int(W * 0.42)
        gd.ellipse([cx*W-r, cy*H-r*0.8, cx*W+r, cy*H+r*0.8], fill=170)
        g = g.filter(ImageFilter.GaussianBlur(int(W*0.13)))
        im = Image.composite(Image.new("RGB", (W, H), glow), im, g)
    return im

def bokeh(im, colour, n=64, seed=7, lo=18, hi=190, alpha=(12, 46)):
    """نقاط ضوء ناعمة بأحجام وشفافيات مختلفة."""
    rnd = random.Random(seed)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(n):
        r = rnd.randint(lo, hi)
        x, y = rnd.randint(-r, W+r), rnd.randint(-r, H+r)
        a = rnd.randint(*alpha)
        d.ellipse([x-r, y-r, x+r, y+r], fill=colour + (a,))
    layer = layer.filter(ImageFilter.GaussianBlur(9))
    out = im.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")

def vignette(im, strength=0.72):
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).ellipse(
        [-W*0.18, -H*0.30, W*1.18, H*1.30], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(int(W*0.09)))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.blend(dark, im, 1.0).point(lambda v: v) if False else \
        Image.composite(im, Image.blend(im, dark, strength), m)

SPECS = {
 "night_bokeh":  (grad((11, 26, 58), (2, 5, 14), glow=(24, 52, 104)),
                  (150, 195, 255), 11),
 "gold_dust":    (grad((58, 38, 10), (10, 7, 3), cx=0.62, cy=0.28,
                       glow=(120, 80, 22)), (255, 214, 140), 29),
 "ember_dark":   (grad((30, 12, 10), (6, 4, 5), cx=0.38, cy=0.42,
                       glow=(78, 26, 18)), (255, 150, 96), 47),
 "mist_mono":    (grad((44, 48, 54), (10, 11, 13), cx=0.5, cy=0.55,
                       glow=(88, 94, 104)), (220, 228, 240), 61),
 "deep_teal":    (grad((8, 40, 46), (2, 8, 11), cx=0.30, cy=0.30,
                       glow=(16, 78, 88)), (140, 235, 236), 83),
}
for name, (base, dots, seed) in SPECS.items():
    im = vignette(bokeh(base, dots, seed=seed))
    im.save(A / f"{name}.png")
    print(f"{name}.png  {im.size}")

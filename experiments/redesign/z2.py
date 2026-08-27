"""
مصدر أقوى: كل إطار بيحمل **رقمه** مشفّرًا بصريًا، فوق شبكة الزوم.

ليش: عدد الإطارات الصح ما بينفي إسقاط إطار مع تكرار إطار تاني
(الاتنين بيلغوا بعض بالعدّ). الباركود بيخلّي كل إطار مخرَج يقول من أي
إطار مصدر إجا — فبينمسك الإسقاط والتكرار والترتيب سوا.

الباركود بالوسط عموديًا وأفقيًا عشان ينجى من أي نافذة قص عند زوم ≤١.٢٥.
"""
import os, subprocess, math
from PIL import Image, ImageDraw

FPS = 30
SW, SH = 540, 960
PITCH = 24
NBITS = 12
CELL_W, CELL_H = 26, 34
BAND_Y = SH // 2 - CELL_H // 2
BAND_X = SW // 2 - (NBITS * CELL_W) // 2
DUR_FRAMES = 600
SRC = "/tmp/realrun/grid2.mp4"
_D = "/tmp/realrun/_g2"


def sh(a, **k):
    return subprocess.run(a, capture_output=True, **k)


def build():
    os.makedirs(_D, exist_ok=True)
    for n in range(DUR_FRAMES):
        img = Image.new("RGB", (SW, SH), (0, 0, 0))
        d = ImageDraw.Draw(img)
        for x in range(0, SW, PITCH):
            d.line([(x, 0), (x, SH)], fill=(255, 255, 255), width=1)
        for y in range(0, SH, PITCH):
            d.line([(0, y), (SW, y)], fill=(255, 255, 255), width=1)
        # شريط أسود تحت الباركود عشان الشبكة ما تلخبطه
        d.rectangle([BAND_X - 6, BAND_Y - 6,
                     BAND_X + NBITS * CELL_W + 5, BAND_Y + CELL_H + 5], fill=(0, 0, 0))
        for b in range(NBITS):
            on = (n >> b) & 1
            x0 = BAND_X + b * CELL_W
            d.rectangle([x0 + 3, BAND_Y + 3, x0 + CELL_W - 4, BAND_Y + CELL_H - 4],
                        fill=(255, 255, 255) if on else (30, 30, 30))
        img.save(f"{_D}/{n:05d}.png")
    sh(['ffmpeg', '-y', '-v', 'error', '-framerate', str(FPS), '-start_number', '0',
        '-i', f'{_D}/%05d.png',
        '-f', 'lavfi', '-i', f'sine=frequency=440:duration={DUR_FRAMES/FPS}:sample_rate=48000',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '10',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', SRC], check=False)


def read_barcode(img, zoom, pan_out=0.0, bias=0.5):
    """
    يقرا رقم الإطار من صورة مخرَج. الباركود انكبّر بمعامل `zoom` وانقصّ
    حوالين المركز، فمكانه بالمخرَج بينحسب هندسيًا.
    """
    Wo, Ho = img.size
    s = zoom
    # مركز نافذة القص بإحداثيات المصدر
    cx = SW / 2 + pan_out / s
    cy = (SH - Ho / s) * bias + (Ho / s) / 2
    px = img.load()
    bits = 0
    for b in range(NBITS):
        sx = BAND_X + b * CELL_W + CELL_W / 2
        sy = BAND_Y + CELL_H / 2
        ox = (sx - cx) * s + Wo / 2
        oy = (sy - cy) * s + Ho / 2
        if not (2 <= ox < Wo - 2 and 2 <= oy < Ho - 2):
            return None
        acc = [px[int(ox) + dx, int(oy) + dy][1]
               for dx in (-2, 0, 2) for dy in (-4, 0, 4)]
        if sorted(acc)[len(acc) // 2] > 128:
            bits |= (1 << b)
    return bits


if __name__ == "__main__":
    if not os.path.exists(SRC):
        build()
    r = sh(['ffmpeg', '-i', SRC, '-f', 'null', '-'], text=True).stderr
    import re
    print("المصدر:", re.findall(r'frame=\s*(\d+)', r)[-1], "إطار")
    # تحقّق: نقرا الباركود من المصدر نفسه بزوم ١.٠
    os.makedirs("/tmp/realrun/_g2chk", exist_ok=True)
    sh(['ffmpeg', '-y', '-v', 'error', '-i', SRC, '-vf', 'select=lt(n\\,40)',
        '-vsync', '0', '/tmp/realrun/_g2chk/%05d.png'])
    bad = 0
    for n in range(40):
        p = f"/tmp/realrun/_g2chk/{n+1:05d}.png"
        got = read_barcode(Image.open(p).convert("RGB"), 1.0)
        if got != n:
            bad += 1
            if bad <= 5:
                print(f"   ❌ إطار {n} انقرا {got}")
    print(f"تحقّق القارئ على المصدر: {40-bad}/40 "
          + ("✅" if bad == 0 else "❌ القارئ مش موثوق"))

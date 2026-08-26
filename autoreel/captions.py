"""
رسم الكابشن العربي.

⚠️ المطبّ الأهم بالمشروع كله — اقرأ قبل ما تعدّل:
لا تستخدم arabic_reshaper ولا python-bidi هون. Pillow المبني مع libraqm
بيعمل التشكيل (shaping) والاتجاه (bidi) لحاله. لو عملت reshape قبله
بيصير انعكاس مزدوج والنص بيطلع مقلوب، ولو الخط ما بيدعم صيغ العرض
القديمة (Tajawal ما بيدعمها) بتطلع مربعات فاضية أو خلفية سودا.

الصح: مرّر النص الخام + direction="rtl" + language="ar".
تحقق: from PIL import features; features.check("raqm")  ->  لازم True
"""
from PIL import Image, ImageDraw, ImageFont, features
import os

if not features.check("raqm"):
    raise RuntimeError(
        "Pillow بدون دعم raqm — الكابشن العربي رح يطلع غلط.\n"
        "Termux:  pkg install libraqm harfbuzz fribidi && pip install --no-binary :all: --force-reinstall Pillow"
    )

_FC = {}


def _font(path, size):
    k = (path, size)
    if k not in _FC:
        _FC[k] = ImageFont.truetype(path, size)
    return _FC[k]


def group_words(words, max_words=4, max_gap=0.55):
    """يجمّع الكلمات لمجموعات كابشن قصيرة حسب العدد والفجوة الزمنية."""
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > max_gap):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return [
        {"start": g[0]["start"], "end": g[-1]["end"],
         "words": [w["word"].strip() for w in g], "raw": g}
        for g in groups if g
    ]


def render_caption(text, cfg, W, highlight_idx=None):
    """يرجّع PNG شفاف فيه سطر الكابشن مع خلفية مدوّرة."""
    size = cfg["size"]
    f = _font(cfg["font"], size)
    pad_x, pad_y = int(size * 0.55), int(size * 0.34)

    probe = Image.new("RGBA", (10, 10))
    d = ImageDraw.Draw(probe)

    words = text.split()
    widths = []
    for w in words:
        bb = d.textbbox((0, 0), w, font=f, direction="rtl", language="ar")
        widths.append((bb[2] - bb[0], bb[0]))
    gap = int(size * 0.28)
    total = sum(w for w, _ in widths) + gap * (len(words) - 1)

    bb_full = d.textbbox((0, 0), text, font=f, direction="rtl", language="ar")
    th = bb_full[3] - bb_full[1]
    top = bb_full[1]

    img_w = min(W - 60, total + pad_x * 2)
    img_h = th + pad_y * 2
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle([0, 0, img_w - 1, img_h - 1],
                         radius=int(img_h * 0.30), fill=tuple(cfg["box"]))

    # ترتيب RTL: أول كلمة أقصى اليمين
    xr = (img_w + total) / 2
    for i, (w, (wpx, ox)) in enumerate(zip(words, widths)):
        col = tuple(cfg["highlight"]) if i == highlight_idx else tuple(cfg["color"])
        dr.text((xr - wpx - ox, pad_y - top), w, font=f, fill=col + (255,),
                direction="rtl", language="ar")
        xr -= wpx + gap
    return img


def build_caption_pngs(groups, cfg, W, outdir, karaoke=True):
    """
    يولّد ملفات PNG للكابشن.
    karaoke=True -> نسخة لكل كلمة عشان تتلوّن وقت نطقها.
    يرجّع [(png_path, start, end)]
    """
    os.makedirs(outdir, exist_ok=True)
    out, n = [], 0
    for g in groups:
        text = " ".join(g["words"])
        if not text.strip():
            continue
        if karaoke and len(g["words"]) > 1:
            for i, w in enumerate(g["raw"]):
                p = os.path.join(outdir, f"cap{n:05d}.png")
                render_caption(text, cfg, W, highlight_idx=i).save(p)
                s = w["start"]
                e = w["end"] if i < len(g["raw"]) - 1 else g["end"]
                if e - s > 0.02:
                    out.append((p, s, e))
                n += 1
        else:
            p = os.path.join(outdir, f"cap{n:05d}.png")
            render_caption(text, cfg, W).save(p)
            out.append((p, g["start"], g["end"]))
            n += 1
    return out

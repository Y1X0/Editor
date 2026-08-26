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


_MEASURE = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

# حدود التصغير التلقائي (نسبة من `captions.size`)
_WRAP_BELOW = 0.75   # لو ما زبط سطر واحد لحد هون -> لفّ سطرين بالحجم الكامل
_HARD_MIN = 0.45     # أصغر حجم مسموح فيه إطلاقًا قبل الاستسلام
_MAX_LINES = 2

_FIT_CACHE = {}


def _margins(size):
    """كل الأبعاد مشتقّة من حجم الخط حتى تتناسق لما نصغّره."""
    return int(size * 0.55), int(size * 0.34), int(size * 0.28)   # pad_x, pad_y, gap


def _widths(words, f):
    """عرض كل كلمة + إزاحة الحبر عن نقطة الرسم (bb[0])."""
    out = []
    for w in words:
        bb = _MEASURE.textbbox((0, 0), w, font=f, direction="rtl", language="ar")
        out.append((bb[2] - bb[0], bb[0]))
    return out


def _wrap(words, widths, gap, avail):
    """
    يوزّع الكلمات على أسطر بحيث ما يتعدّى أي سطر `avail`.
    يرجّع None لو في كلمة لحالها أعرض من السطر — يعني لازم تصغير أكتر،
    لأن قصّ الكلمة ممنوع.
    """
    lines, cur, cur_w = [], [], 0
    for w, (wpx, _) in zip(words, widths):
        if wpx > avail:
            return None
        nxt = wpx if not cur else cur_w + gap + wpx
        if nxt > avail and cur:
            lines.append(cur)
            cur, cur_w = [w], wpx
        else:
            cur.append(w)
            cur_w = nxt
    if cur:
        lines.append(cur)
    return lines


def _fit(words, font_path, base_size, avail_outer):
    """
    يلاقي أكبر حجم خط بيخلّي النص يزبط بدون ما ننقص ولا حرف.

    الترتيب مقصود:
      ١. سطر واحد بأكبر حجم من ١٠٠٪ لحد ٧٥٪.
      ٢. ما زبط؟ ارجع للحجم الكامل ولفّه سطرين (سطرين بحجم كبير أوضح
         من سطر واحد بخط زغير).
      ٣. لسا ما زبط؟ كمّل تصغير بسطرين لحد ٤٥٪.
      ٤. آخر ملجأ: أصغر حجم — بيطلع أسطر أكتر بس ولا كلمة بتنقص.

    يرجّع (size, lines).
    """
    lo = max(8, int(base_size * _WRAP_BELOW))
    hard = max(8, int(base_size * _HARD_MIN))

    def try_size(size, max_lines):
        f = _font(font_path, size)
        pad_x, _, gap = _margins(size)
        lines = _wrap(words, _widths(words, f), gap, avail_outer - pad_x * 2)
        if lines is not None and len(lines) <= max_lines:
            return lines
        return None

    for size in range(base_size, lo - 1, -1):          # ١
        lines = try_size(size, 1)
        if lines:
            return size, lines

    for size in range(base_size, hard - 1, -1):        # ٢ و ٣
        lines = try_size(size, _MAX_LINES)
        if lines:
            return size, lines

    f = _font(font_path, hard)                         # ٤ — لا نقصّ أبدًا
    _, _, gap = _margins(hard)
    pad_x, _, _ = _margins(hard)
    lines = _wrap(words, _widths(words, f), gap, avail_outer - pad_x * 2)
    return hard, lines or [words]


def render_caption(text, cfg, W, highlight_idx=None):
    """
    يرجّع PNG شفاف فيه الكابشن مع خلفية مدوّرة.

    بيصغّر الخط تلقائيًا ويلفّ سطرين وقت اللزوم — النص ما بينقصّ أبدًا.
    شوف `_fit` لترتيب المحاولات.
    """
    words = text.split()
    if not words:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    key = (text, cfg["font"], cfg["size"], W)
    if key not in _FIT_CACHE:                # نفس الجملة بتنرسم مرة لكل كلمة
        _FIT_CACHE[key] = _fit(words, cfg["font"], cfg["size"], W - 60)
    size, lines = _FIT_CACHE[key]

    f = _font(cfg["font"], size)
    pad_x, pad_y, gap = _margins(size)

    # ارتفاع السطر من bbox النص الكامل — بيثبّت خط الأساس لكل الأسطر
    # ولكل إطارات الكاريوكي لنفس الجملة.
    bb_full = _MEASURE.textbbox((0, 0), text, font=f, direction="rtl", language="ar")
    th, top = bb_full[3] - bb_full[1], bb_full[1]
    leading = int(size * 0.22)

    per_line = [_widths(ln, f) for ln in lines]
    totals = [sum(w for w, _ in ws) + gap * (len(ws) - 1) for ws in per_line]

    img_w = max(totals) + pad_x * 2
    img_h = th * len(lines) + leading * (len(lines) - 1) + pad_y * 2
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle([0, 0, img_w - 1, img_h - 1],
                         radius=int(img_h * 0.30), fill=tuple(cfg["box"]))

    gi = 0
    for li, ln in enumerate(lines):
        y = pad_y - top + li * (th + leading)
        # ترتيب RTL: أول كلمة بالسطر أقصى اليمين، وبننقص لليسار
        xr = (img_w + totals[li]) / 2
        for w, (wpx, ox) in zip(ln, per_line[li]):
            col = tuple(cfg["highlight"]) if gi == highlight_idx else tuple(cfg["color"])
            dr.text((xr - wpx - ox, y), w, font=f, fill=col + (255,),
                    direction="rtl", language="ar")
            xr -= wpx + gap
            gi += 1
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

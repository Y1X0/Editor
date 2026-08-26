"""
رسم الكابشن العربي.

⚠️ المطبّ الأهم بالمشروع كله — اقرأ قبل ما تعدّل:
لا تستخدم arabic_reshaper ولا python-bidi هون. Pillow المبني مع libraqm
بيعمل التشكيل (shaping) والاتجاه (bidi) لحاله. لو عملت reshape قبله
بيصير انعكاس مزدوج والنص بيطلع مقلوب، ولو الخط ما بيدعم صيغ العرض
القديمة (Tajawal ما بيدعمها) بتطلع مربعات فاضية أو خلفية سودا.

الصح: مرّر النص الخام + direction="rtl" + language="ar".
تحقق: from PIL import features; features.check("raqm")  ->  لازم True

فحص raqm بينعمل عند أول رسم كابشن، مش وقت الاستيراد — هيك `--no-captions`
بيضل يشتغل على بيئة بلا raqm بدل ما يفشل قبل ما يبلّش.
"""
from PIL import Image, ImageDraw, ImageFont, features
import os, sys

_FC = {}


def _require_raqm():
    """
    بينداء عند أول رسم كابشن فقط.

    لا تنقله لمستوى الموديول: `cli.py` بتستورد هالملف دايمًا، فالرفع
    وقت الاستيراد كان بيكسر حتى `--no-captions` — وهي الطريق الوحيد
    لتشغيل الأداة على بيئة بلا raqm.
    """
    if not features.check("raqm"):
        raise RuntimeError(
            "Pillow بدون دعم raqm — الكابشن العربي رح يطلع غلط.\n"
            "Termux:  pkg install libraqm harfbuzz fribidi && "
            "pip install --no-binary :all: --force-reinstall Pillow\n"
            "أو شغّل بدون كابشن:  python -m autoreel.cli in.mp4 --no-captions -o out.mp4"
        )


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
_HARD_MIN = 0.45     # أصغر حجم مسموح فيه إطلاقًا قبل الاستسلام
_SMALL_WARN = 55     # تحت هيك النص كامل بس ما بينقرا على الموبايل
_MAX_LINES = 2

_LAYOUT_CACHE = {}


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
    يلاقي التخطيط اللي بيعطي **أكبر حجم خط**، وعند التعادل أقل أسطر.

    مسح تنازلي من `base_size` لحد أرضية ٤٥٪، وأول حجم بيسع بسطرين أو
    أقل بيفوز. تفضيل "أقل أسطر" بيتحقق لحاله: `_wrap` جشعة فبتعطي أقل
    عدد أسطر ممكن لكل حجم — لو النص بيسع بسطر واحد بترجّع سطر واحد.

    آخر ملجأ عند الأرضية: بنقبل أي عدد أسطر. النص ما بينقصّ بأي مسار.

    يرجّع (size, lines).
    """
    hard = max(8, int(base_size * _HARD_MIN))

    def try_size(size, max_lines):
        f = _font(font_path, size)
        pad_x, _, gap = _margins(size)
        lines = _wrap(words, _widths(words, f), gap, avail_outer - pad_x * 2)
        if lines is not None and len(lines) <= max_lines:
            return lines
        return None

    for size in range(base_size, hard - 1, -1):
        lines = try_size(size, _MAX_LINES)
        if lines:
            return size, lines

    f = _font(font_path, hard)                    # الأرضية — لا نقصّ أبدًا
    pad_x, _, gap = _margins(hard)
    lines = _wrap(words, _widths(words, f), gap, avail_outer - pad_x * 2)
    return hard, lines or [words]


def available_width(W):
    """
    العرض المتاح للكابشن داخل إطار عرضه W.

    نسبة مش رقم ثابت: `W - 60` كان يعطي هامش ٥.٦٪ على ١٠٨٠، وعلى
    ١٩٢٠ بيصير ٣.١٪ يعني هامش تافه. `W/18` بيعطي ٦٠ **بالضبط** عند
    ١٠٨٠ فالصور المرجعية ما بتتأثر، وبيتوسّع صح لباقي المقاسات.
    """
    return W - round(W / 18)


def _layout(text, cfg, W):
    """
    كل هندسة الكابشن بدون رسم — المصدر الوحيد للأبعاد.

    `render_caption` بترسم منها، و`caption_size` بتقرا المقاس منها،
    فما بتنفرق حسبة الارتفاع عن الرسم الفعلي.
    """
    key = (text, cfg["font"], cfg["size"], W)
    if key in _LAYOUT_CACHE:
        return _LAYOUT_CACHE[key]

    words = text.split()
    size, lines = _fit(words, cfg["font"], cfg["size"], available_width(W))
    # شرط التصغير الفعلي مقصود: `captions.size` بينداهس لكل مقاس (٤٤
    # للمربع والعريض)، فبدونه كان التحذير بيطلع «انصغّر لحجم ٤٤ (الأصلي
    # ٤٤)» على كل كابشن بهدول المقاسين. التحذير عن تصغير **غير متوقّع**،
    # مش عن حجم اخترته أنت.
    if size < cfg["size"] and size < _SMALL_WARN:
        print(f"⚠️  الكابشن انصغّر من {cfg['size']} لـ{size} — كامل بس صعب "
              f"يتقرا على الموبايل: «{text}»\n"
              f"    جرّب تصغير captions.max_words أو captions.size.",
              file=sys.stderr)

    f = _font(cfg["font"], size)
    pad_x, pad_y, gap = _margins(size)

    # ارتفاع السطر من bbox النص الكامل — بيثبّت خط الأساس لكل الأسطر
    # ولكل إطارات الكاريوكي لنفس الجملة.
    bb = _MEASURE.textbbox((0, 0), text, font=f, direction="rtl", language="ar")
    th, top = bb[3] - bb[1], bb[1]
    leading = int(size * 0.22)

    per_line = [_widths(ln, f) for ln in lines]
    totals = [sum(w for w, _ in ws) + gap * (len(ws) - 1) for ws in per_line]

    lay = {
        "size": size, "lines": lines, "font": f, "per_line": per_line,
        "totals": totals, "gap": gap, "pad_y": pad_y, "th": th, "top": top,
        "leading": leading,
        "w": max(totals) + pad_x * 2,
        "h": th * len(lines) + leading * (len(lines) - 1) + pad_y * 2,
    }
    _LAYOUT_CACHE[key] = lay
    return lay


def caption_size(text, cfg, W):
    """مقاس الكابشن (عرض، ارتفاع) بدون ما نرسمه."""
    _require_raqm()
    if not text.split():
        return (1, 1)
    lay = _layout(text, cfg, W)
    return lay["w"], lay["h"]


def assert_fits_frame(texts, cfg, W, H, label=""):
    """
    بيرفع لو أطول كابشن بيطلع برّا الإطار عند `y_ratio` المعطاة.

    خطأ مش تحذير: كابشن مقصوص مخرَج تالف، والمستخدم بيكتشفه بعد الرفع
    مش قبله. الحجم الصغير بيضل تحذير — هاداك مقروئية مش تلف.
    """
    y = int(H * cfg["y_ratio"])
    worst, tallest = None, 0
    for t in texts:
        h = caption_size(t, cfg, W)[1]
        if h > tallest:
            worst, tallest = t, h
    if worst is None:
        return
    top, bot = y - tallest // 2, y - tallest // 2 + tallest
    if top < 0 or bot > H:
        where = f"[{label}] " if label else ""
        raise ValueError(
            f"{where}الكابشن بيطلع برّا الإطار: ارتفاعه {tallest}px بمركز "
            f"y={y}، فبيمتد {top}..{bot} والإطار {H}px.\n"
            f"    أطول كابشن: «{worst}»\n"
            f"    صغّر captions.size أو captions.max_words، أو حرّك "
            f"captions.y_ratio (حاليًا {cfg['y_ratio']}).")


def render_caption(text, cfg, W, highlight_idx=None):
    """
    يرجّع PNG شفاف فيه الكابشن مع خلفية مدوّرة.

    بيصغّر الخط تلقائيًا ويلفّ سطرين وقت اللزوم — النص ما بينقصّ أبدًا.
    شوف `_fit` لترتيب المحاولات.
    """
    _require_raqm()
    if not text.split():
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    lay = _layout(text, cfg, W)
    f, gap, pad_y = lay["font"], lay["gap"], lay["pad_y"]
    th, top, leading = lay["th"], lay["top"], lay["leading"]
    lines, per_line, totals = lay["lines"], lay["per_line"], lay["totals"]

    img_w, img_h = lay["w"], lay["h"]
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


# عتبة جسر الفجوة بين مجموعتين. لازم تساوي `cuts.min_gap` — القص بيشيل
# أي صمت **أطول** من min_gap، يعني كل فجوة بتنجى بعد القص ≤ min_gap.
# `cli.py` بتمرّرها من الconfig؛ هاي بس القيمة الافتراضية لو حدا ناداها
# مباشرة. شوف CLAUDE.md.
DEFAULT_BRIDGE_GAP = 0.45

# تسامح للمقارنة عند الحد بالضبط. توقيتات الكلمات بتيجي من جمع وطرح
# عائم، فالفجوة اللي المفروض تكون 0.45 بتطلع 0.45000000000000007.
# بنميل للجسر عند الشك — الطفي أوضح للعين من امتداد زيادة بجزء من الألف.
_EPS = 1e-6


def build_caption_pngs(groups, cfg, W, outdir, karaoke=True,
                       bridge_gap=DEFAULT_BRIDGE_GAP):
    """
    يولّد ملفات PNG للكابشن.
    karaoke=True -> نسخة لكل كلمة عشان تتلوّن وقت نطقها.

    التوقيت: كل إطار بيضل معروض لحد ما يبلّش اللي بعده — ما في فراغ جوا
    المجموعة. آخر إطار بيمتد لبداية المجموعة الجاية لو الفجوة <=
    `bridge_gap`، وإلا بينتهي عند نهاية المجموعة.

    مرّر `bridge_gap=cfg["cuts"]["min_gap"]` حتى كل فجوة ناجية من القص
    تنجسر. المقارنة `<=` مش `<` عشان الفجوة اللي بتساوي min_gap بالضبط
    بتنجى من القص (الشرط هناك `> min_gap`) فلازم تنجسر كمان، مع تسامح
    `_EPS` لأن جمع/طرح العائمة بيعطي 0.45000000000000007 عند الحد.

    يرجّع [(png_path, start, end)]
    """
    os.makedirs(outdir, exist_ok=True)
    out, n = [], 0
    for gi, g in enumerate(groups):
        text = " ".join(g["words"])
        if not text.strip():
            continue

        # نهاية آخر إطار بهالمجموعة. الفجوة السالبة (مجموعات متداخلة)
        # بتنقص كمان لـ nxt فما بيتراكبوا كابشنين.
        nxt = groups[gi + 1]["start"] if gi + 1 < len(groups) else None
        tail = (nxt if (nxt is not None and nxt - g["end"] <= bridge_gap + _EPS)
                else g["end"])

        if karaoke and len(g["words"]) > 1:
            raw = g["raw"]
            for i, w in enumerate(raw):
                s = w["start"]
                # لحد ما تبلّش الكلمة الجاية — مش لحد ما تخلص هاي الكلمة،
                # وإلا الكابشن بيطفي بالفراغ اللي بينهن.
                e = raw[i + 1]["start"] if i < len(raw) - 1 else tail
                if e - s <= 0.02:
                    continue
                p = os.path.join(outdir, f"cap{n:05d}.png")
                render_caption(text, cfg, W, highlight_idx=i).save(p)
                out.append((p, s, e))
                n += 1
        else:
            p = os.path.join(outdir, f"cap{n:05d}.png")
            render_caption(text, cfg, W).save(p)
            out.append((p, g["start"], tail))
            n += 1
    return out

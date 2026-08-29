"""Phase 0.5 spike A — رسم العربي: نقيس، ما منفترض.

يجاوب على أربع أسئلة قبل ما ينكتب أي كود إنتاج:
  Q1  هل libraqm موجودة وشغّالة؟                       (R1)
  Q2  كم بتتجاوز علامات التشكيل الـfont metrics؟        (R10)
  Q3  هل صيغ العرض القديمة (اللي بيطلّعها reshaper)
      بتخسر الليجاتورات؟                                (R1)
  Q4  هل ترتيب الـruns المختلطة صح بلا تدخّل؟           (R1)
"""
from PIL import Image, ImageDraw, ImageFont, features
import json, sys

FONT = "fonts/Amiri-Bold.ttf"
SIZE = 72
AYAH = "وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ"
PLAIN = "ومن يتوكل على الله فهو حسبه"
MIXED = "تحديث iOS 18 نزل على App Store"

out = {}

# ── Q1 ────────────────────────────────────────────────────────────────
out["raqm"] = features.check("raqm")
if not out["raqm"]:
    sys.exit("❌ Pillow بلا libraqm — الرسم العربي مش مضمون")

f = ImageFont.truetype(FONT, SIZE)
asc, desc = f.getmetrics()
out["metrics"] = {"ascent": asc, "descent": desc, "line_h": asc + desc}


def ink(text, pad=400):
    """يرسم النص ويرجّع صندوق الحبر الفعلي منسوبًا لخطّ الأساس."""
    W, H = 3000, 1000
    base_y = 500                      # الأساس (baseline)
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    d.text((W - pad, base_y), text, font=f, fill=255,
           direction="rtl", language="ar", anchor="rs")
    bb = im.getbbox()
    if bb is None:
        return None
    x0, y0, x1, y1 = bb
    return {"above_baseline": base_y - y0, "below_baseline": y1 - base_y,
            "w": x1 - x0, "h": y1 - y0}


# ── Q2 ────────────────────────────────────────────────────────────────
a, p = ink(AYAH), ink(PLAIN)
out["ink_with_tashkeel"] = a
out["ink_plain"] = p
out["tashkeel_overflow_px"] = a["above_baseline"] - asc
out["tashkeel_vs_plain_px"] = a["above_baseline"] - p["above_baseline"]

# ── Q3 ── صيغ العرض القديمة: هيك بيطلّع arabic_reshaper النص ──────────
# "الله" بصيغ العرض المعزولة/المتصلة بدل المحارف الأصلية
ALLAH_SRC = "الله"
ALLAH_PRES = "ﻟﻠﻠﻀﻡ"[:0] + "ﻟﻜﻠﻧ"  # تقريب لصيغ عرض
out["q3"] = {}
for name, s in (("source_codepoints", ALLAH_SRC), ("presentation_forms", ALLAH_PRES)):
    i = ink(s)
    out["q3"][name] = {"codepoints": [hex(ord(c)) for c in s],
                       "n_chars": len(s), "ink": i}

# ── Q4 ────────────────────────────────────────────────────────────────
im = Image.new("RGB", (1400, 200), (18, 18, 20))
ImageDraw.Draw(im).text((1350, 100), MIXED, font=f, fill=(243, 229, 171),
                        direction="rtl", language="ar", anchor="rm")
im.save("experiments/ai_pipeline/out/q4_mixed.png")

# صورة شاهدة للعين
im2 = Image.new("RGB", (1400, 320), (18, 18, 20))
d2 = ImageDraw.Draw(im2)
d2.text((1350, 90), AYAH, font=f, fill=(243, 229, 171),
        direction="rtl", language="ar", anchor="rm")
d2.text((1350, 230), PLAIN, font=f, fill=(243, 229, 171),
        direction="rtl", language="ar", anchor="rm")
im2.save("experiments/ai_pipeline/out/q2_tashkeel.png")

print(json.dumps(out, ensure_ascii=False, indent=2))

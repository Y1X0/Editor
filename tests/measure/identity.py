"""هوية الإطار: أي إطار مصدر ظهر بأي إطار مخرَج."""
from PIL import Image

from .source import ID_CAPACITY, id_color

_TABLE = [id_color(n) for n in range(ID_CAPACITY)]
assert len(set(_TABLE)) == ID_CAPACITY, "ألوان الهوية متكرّرة — القياس بينكسر"


def frame_id(img, tol=9):
    """
    رقم إطار المصدر من صورة مخرَج، أو None لو ما في تطابق قريب.

    `tol` مسافة قصوى لكل قناة. خطوة الألوان ٢٠، فتسامح ٩ بيقبل انحراف
    الترميز وبيرفض الجار. **بلا `tol` القياس بيكذب**: أقرب لون دايمًا
    بينلاقى، حتى لو الرقعة انقصّت وصرنا نقرا خلفية.
    """
    if isinstance(img, str):
        img = Image.open(img)
    img = img.convert("RGB")
    w, h = img.size
    px = img.load()
    # عيّنة وسيطة من ٩ نقاط — بتتجاهل بكسل شاذ على حافة الرقعة
    pts = [px[w // 2 + dx, h // 2 + dy]
           for dx in (-8, 0, 8) for dy in (-8, 0, 8)]
    c = tuple(sorted(p[k] for p in pts)[4] for k in range(3))
    best, bd = None, 10 ** 9
    for n, ref in enumerate(_TABLE):
        d = max(abs(a - b) for a, b in zip(c, ref))
        if d < bd:
            best, bd = n, d
    return best if bd <= tol else None


def read_identities(png_paths):
    """[رقم إطار المصدر] لكل إطار مخرَج، بنفس الترتيب."""
    return [frame_id(p) for p in png_paths]


def identity_report(got, want):
    """
    مقارنة تسلسل الهويات بالمتوقَّع.

    بترجّع dict فيه: mismatches, duplicates, missing.
    الثلاثة لازمين: **العدد الصح ما بينفي إسقاط إطار مع تكرار تاني** —
    الاتنين بيلغوا بعض بالعدّ. هاد بالضبط لغم `setpts=N/FPS/TB`.
    """
    n = min(len(got), len(want))
    seen = [x for x in got if x is not None]
    return {
        "mismatches": [(i, want[i], got[i]) for i in range(n) if got[i] != want[i]],
        "duplicates": len(seen) - len(set(seen)),
        "missing": sorted(set(want) - set(seen)),
        "unreadable": [i for i, x in enumerate(got) if x is None],
        "count": len(got),
    }

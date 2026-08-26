"""
`_bidi_runs` — ترتيب التوكنات بالنص المختلط.

الحقيقة المرجعية مش رأيي: بنرسم السطر كامل بنداء واحد فيخلي raqm
يطبّق bidi كامل، وبنقارن ترتيب `_bidi_runs` فيه.

⚠️ أداة القياس نفسها عليها فحص — `test_comparator_catches_a_known_inversion`.
تسامح متساهل بلع حالة مقلوبة فعلًا وقت التشخيص، فالعتبة ٣٪ مش زينة.
"""
import pytest
from PIL import Image, ImageDraw

from autoreel import captions as CAP
from conftest import needs_raqm

TOL = 0.03          # نسبة الفرق المسموحة بعرض التوكن


# ------------------------------------------------------- أداة القياس

def _split_at_widest_gaps(img, n_tokens):
    """
    عرض كل توكن من اليسار لليمين.

    **عتبة ثابتة ما بتزبط:** الحروف العربية غير المتصلة (ر، و، ا، د)
    بتترك فجوات داخل الكلمة الواحدة، وبعضها أوسع من أي عتبة معقولة —
    فالتوكن بينقسم لقطعتين والقياس بيكذب. بس احنا بنعرف عدد التوكنات
    مسبقًا، فبناخد **أوسع n-1 فجوة** كفواصل. حتمية وما إلها عتبة تنضبط.
    """
    a = img.split()[-1]
    w, h = a.size
    px = a.load()
    on = [any(px[x, y] > 40 for y in range(h)) for x in range(w)]

    gaps, start = [], None                    # (عرض، بداية، نهاية)
    for x, ink in enumerate(on + [True]):
        if not ink and start is None:
            start = x
        elif ink and start is not None:
            gaps.append((x - start, start, x))
            start = None
    inner = [g for g in gaps if g[1] > 0 and g[2] < w]     # بلا هوامش الأطراف
    cuts = sorted(g[1] + (g[0] // 2) for g in
                  sorted(inner, key=lambda g: -g[0])[:n_tokens - 1])

    edges = [0] + cuts + [w]
    out = []
    for lo, hi in zip(edges, edges[1:]):
        cols = [x for x in range(lo, hi) if on[x]]
        out.append(max(cols) - min(cols) if cols else 0)
    return out


def reference_widths(text, cfg, size):
    """عرض التوكنات من اليسار لليمين كما رسمها raqm بـbidi كامل."""
    f = CAP._font(cfg["font"], size)
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb = d.textbbox((0, 0), text, font=f, direction="rtl", language="ar")
    im = Image.new("RGBA", (bb[2] - bb[0] + 8, bb[3] - bb[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - bb[0], 4 - bb[1]), text, font=f,
                            fill=(255, 255, 255, 255), direction="rtl", language="ar")
    return _split_at_widest_gaps(im, len(text.split()))


def matches(seq_a, seq_b, tol=TOL):
    """هل تسلسلا العرض متطابقان بعد التطبيع؟"""
    if len(seq_a) != len(seq_b) or not seq_a:
        return False
    sa, sb = sum(seq_a), sum(seq_b)
    return all(abs(x / sa - y / sb) < tol for x, y in zip(seq_a, seq_b))


def visual_widths(tokens, order, cfg, size):
    f = CAP._font(cfg["font"], size)
    w = [x for x, _ in CAP._widths(tokens, f)]
    return [w[i] for i in order]


# ------------------------------------------ فحص أداة القياس على حالها

@needs_raqm
def test_comparator_catches_a_known_inversion(caps):
    """
    الشرط اللي وقعنا فيه مرتين: أداة قياس متساهلة بتقول «كله تمام»
    وهو مكسور. هون بنعطيها ترتيب مقلوب معروف ونتأكد إنها بتصرخ.
    """
    text = "حمّل من App Store هلأ"
    tokens = text.split()
    size = 74
    ref = reference_widths(text, caps, size)
    good = visual_widths(tokens, CAP._bidi_runs(tokens), caps, size)
    # الترتيب المكسور: RTL بحت (اللي كان قبل التصليح)
    bad = visual_widths(tokens, list(reversed(range(len(tokens)))), caps, size)

    assert matches(good, ref), f"الترتيب الصح ما طابق المرجع: {good} vs {ref}"
    assert not matches(bad, ref), (
        f"❌ أداة القياس بلعت انقلابًا معروفًا — العتبة {TOL} متساهلة.\n"
        f"    المقلوب {bad}\n    المرجع  {ref}")


@needs_raqm
def test_comparator_tolerance_is_tight_enough(caps):
    """العتبة لازم ترفض تبادل عنصرين متجاورين مختلفي العرض."""
    a = [100, 300, 120, 90]
    assert matches(a, list(a))
    swapped = [100, 120, 300, 90]
    assert not matches(a, swapped)


# ----------------------------------------------- التصنيف والمحايدات

@pytest.mark.parametrize("tok,want", [
    ("مرحبا", "R"), ("Flutter", "L"), ("iOS", "L"),
    ("2024", "N"), ("٢٠٢٤", "N"), ("+", "N"), ("...", "N"),
    ("README.md", "L"), ("v2", "L"), ("د.أ", "R"),
])
def test_token_direction(tok, want):
    assert CAP._token_dir(tok) == want


def test_neutral_joins_a_latin_run():
    """`iOS 18` -> الرقم بينضم للـrun اللاتيني."""
    tokens = "تحديث iOS 18 نزل".split()
    assert [tokens[i] for i in CAP._bidi_runs(tokens)] == \
           ["نزل", "iOS", "18", "تحديث"]


def test_neutral_after_arabic_stays_rtl():
    """`رقم 2024 و 2025` -> كل رقم خانة RTL لحاله."""
    tokens = "رقم 2024 و 2025 سوا".split()
    assert [tokens[i] for i in CAP._bidi_runs(tokens)] == \
           ["سوا", "2025", "و", "2024", "رقم"]


def test_neutral_at_line_start_is_rtl():
    tokens = "+ مرحبا".split()
    assert [tokens[i] for i in CAP._bidi_runs(tokens)] == ["مرحبا", "+"]


def test_symbol_between_two_latin_joins_them():
    """`Flutter + Dart` -> run لاتيني واحد، الرمز جوّاه."""
    tokens = "Flutter + Dart".split()
    assert [tokens[i] for i in CAP._bidi_runs(tokens)] == ["Flutter", "+", "Dart"]


def test_arabic_between_two_latin_splits_the_runs():
    tokens = "افتح Google ثم Play Store".split()
    assert [tokens[i] for i in CAP._bidi_runs(tokens)] == \
           ["Play", "Store", "ثم", "Google", "افتح"]


def test_all_latin_line_reads_left_to_right():
    tokens = "Flutter Web and Dart".split()
    assert CAP._bidi_runs(tokens) == [0, 1, 2, 3]


def test_all_arabic_line_reads_right_to_left():
    tokens = "هاد المشروع بيقص الفيديو".split()
    assert CAP._bidi_runs(tokens) == [3, 2, 1, 0]


def test_empty_and_single():
    assert CAP._bidi_runs([]) == []
    assert CAP._bidi_runs(["مرحبا"]) == [0]
    assert CAP._bidi_runs(["Flutter"]) == [0]


def test_every_token_appears_exactly_once():
    """ضمانة أساسية: الترتيب تبديل، مش حذف ولا تكرار."""
    for text in ["افتح Google ثم Play Store", "رقم 2024 و 2025 سوا",
                 "Flutter + Dart", "هاد المشروع"]:
        tokens = text.split()
        assert sorted(CAP._bidi_runs(tokens)) == list(range(len(tokens)))


# ----------------------------------- المطابقة مع raqm: كل الحالات

CASES = [
    # نصوص المستخدم — كانت سليمة قبل التصليح كمان
    "شغال على Flutter من ٢٠٢٤",
    "سعره ١٢ د.أ بس",
    "الـ AI غيّر كل شي",
    # كانت مكسورة: كلمتان لاتينيتان متجاورتان
    "بنستخدم Flutter Web هون",
    "حمّل من App Store هلأ",
    "افتح Google Play Store",
    "نسخة v2 beta جاهزة",
    "تحديث iOS 18 نزل",
    # كانت سليمة
    "رقم 2024 و 2025 سوا",
    "خليط ABC ثم DEF ثم GHI",
    "شوف README.md هون",
    # الحالات الإضافية المطلوبة
    "افتح Google ثم Play Store",
    "Flutter + Dart",
    "Flutter Web and Dart",
]


@needs_raqm
@pytest.mark.parametrize("text", CASES)
def test_order_matches_raqm(caps, text):
    tokens = text.split()
    size = 74
    got = visual_widths(tokens, CAP._bidi_runs(tokens), caps, size)
    ref = reference_widths(text, caps, size)
    assert matches(got, ref), (
        f"ترتيب مختلف عن bidi الكامل\n"
        f"    عنا   {got}\n    المرجع {ref}\n"
        f"    الترتيب: {[tokens[i] for i in CAP._bidi_runs(tokens)]}")


BROKEN = [
    "بنستخدم Flutter Web هون",
    "حمّل من App Store هلأ",
    "افتح Google Play Store",
    "نسخة v2 beta جاهزة",
    "تحديث iOS 18 نزل",
]


@needs_raqm
@pytest.mark.parametrize("text", BROKEN)
def test_the_broken_cases_are_no_longer_pure_rtl(caps, text):
    """توثيق للانحدار: هدول كان الترتيب فيهن RTL بحت وهو غلط."""
    tokens = text.split()
    assert CAP._bidi_runs(tokens) != list(reversed(range(len(tokens))))


@needs_raqm
@pytest.mark.parametrize("text", BROKEN)
def test_comparator_rejects_the_old_broken_order(caps, text):
    """
    الضمانة اللي بتخلي `test_order_matches_raqm` إلها معنى: لازم
    المقارنة تفرّق بين الترتيب الجديد والقديم. بدون هالفحص، مقارنة
    متساهلة كانت بتقبل الاتنين وبتقول «نجح» على كود مكسور.

    ملاحظة عن حدود الأداة: المقارنة بالعروض، فتوكنان بعرض متقارب ممكن
    يتبادلوا بدون ما تنكشف. بتميّز نمط الفشل اللي بيهمنا — انقلاب
    الـrun اللاتيني — مش كل تبديل ممكن.
    """
    tokens = text.split()
    ref = reference_widths(text, caps, 74)
    good = visual_widths(tokens, CAP._bidi_runs(tokens), caps, 74)
    pure_rtl = visual_widths(tokens, list(reversed(range(len(tokens)))), caps, 74)
    assert matches(good, ref)
    assert not matches(pure_rtl, ref), "المقارنة ما فرّقت الجديد عن المكسور"

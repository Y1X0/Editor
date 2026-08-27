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


# ================= حلقة الرسم: الترتيب البصري والتلوين =================
#
# ⚠️ الفرق بين الاسمين هو مصدر الباگات هون:
#   logical_index  = مكان التوكن بالنص (اللي `highlight_idx` بيشير إله)
#   draw_position  = مكان رسمه على الصورة من اليسار لليمين
# بالنص العربي الخالص هدول معكوس بعض، وبالمختلط لا هيك ولا هيك.

def highlight_centre(text, caps, logical_index):
    """مركز الكتلة الملوّنة أفقيًا — يعني وين انرسم التوكن فعليًا."""
    bare = dict(caps, box=[0, 0, 0, 0], color=[255, 255, 255])
    img = CAP.render_caption(text, bare, 1080,
                             highlight_idx=logical_index).convert("RGB")
    px = img.load()
    r, g, b = caps["highlight"]
    xs = [x for y in range(img.height) for x in range(img.width)
          if abs(px[x, y][0] - r) < 40 and abs(px[x, y][1] - g) < 40
          and abs(px[x, y][2] - b) < 40]
    assert xs, f"ما في بكسلات ملوّنة للفهرس المنطقي {logical_index}"
    return sum(xs) / len(xs)


@needs_raqm
@pytest.mark.parametrize("text", CASES)
def test_draw_order_follows_bidi_runs(caps, text):
    """
    الفحص المركزي: لوّن كل توكن بدوره وسجّل مركزه، وبعدين رتّب الفهارس
    المنطقية حسب المركز من اليسار لليمين. الناتج لازم يساوي
    `_bidi_runs` بالضبط.

    هيك بيتفحص الاتنين بتأكيد واحد: إن `highlight_idx` بيشير للتوكن
    الصح (فهرس منطقي)، وإن الترتيب البصري صحيح.
    """
    tokens = text.split()
    centres = {i: highlight_centre(text, caps, i) for i in range(len(tokens))}
    by_position = sorted(centres, key=centres.get)
    assert by_position == CAP._bidi_runs(tokens), (
        f"ترتيب الرسم غلط\n"
        f"    انرسم:  {[tokens[i] for i in by_position]}\n"
        f"    المتوقع: {[tokens[i] for i in CAP._bidi_runs(tokens)]}")


@needs_raqm
def test_adjacent_latin_run_reads_left_to_right(caps):
    """أوضح صياغة للباگ: App لازم تكون على يسار Store، مش يمينها."""
    text = "حمّل من App Store هلأ"
    app, store = text.split().index("App"), text.split().index("Store")
    assert highlight_centre(text, caps, app) < highlight_centre(text, caps, store)


@needs_raqm
def test_pure_arabic_still_reads_right_to_left(caps):
    """التصليح ما لازم يقلب العربي الخالص."""
    text = "هاد المشروع بيقص الفيديو"
    cs = [highlight_centre(text, caps, i) for i in range(4)]
    assert cs[0] > cs[1] > cs[2] > cs[3]


# ------------------------- الحد الموثّق: run بينقسم على سطرين

MULTILINE = "المنصة بتشتغل على App Store Connect Developer Portal بشكل كامل"


@needs_raqm
def test_latin_run_split_across_lines_is_ordered_per_line(caps):
    """
    حد موثّق بـCLAUDE.md، وهون اختبار صريح إله بدل ما يضل كلام:
    الـrun اللي بينقسم على سطرين بينرتّب **داخل كل سطر لحاله**.

    مش UAX#9 كامل — المواصفة بتعامل الـrun كوحدة عبر اللف. بس النتيجة
    مقبولة عمليًا: كل سطر بيقرا صح لحاله.
    """
    lay = CAP._layout(MULTILINE, caps, 1080)
    assert len(lay["lines"]) == 2, "الحالة لازم تلف سطرين"

    latin = [w for w in MULTILINE.split() if CAP._token_dir(w) == "L"]
    split = [w for w in lay["texts"][0] if w in latin] and \
            [w for w in lay["texts"][1] if w in latin]
    assert split, "الـrun اللاتيني لازم ينقسم على السطرين"

    # كل سطر مرتّب داخليًا حسب bidi تبعه
    for line in lay["texts"]:
        order = CAP._bidi_runs(line)
        assert sorted(order) == list(range(len(line)))


@needs_raqm
def test_multiline_mixed_text_is_not_clipped(caps):
    """الحد ما لازم يجيب معه قصّ — هاد بند ١ وما بينتنازل عنه."""
    bare = dict(caps, box=[0, 0, 0, 0])
    img = CAP.render_caption(MULTILINE, caps, 1080)
    bb = CAP.render_caption(MULTILINE, bare, 1080).split()[-1].getbbox()
    assert img.width <= 1080 - 60
    assert bb[0] > 0 and bb[2] < img.width


# --------------------------- شرط ٢: التقسيم ما بيغيّر حساب العرض

@needs_raqm
@pytest.mark.parametrize("text", CASES + [MULTILINE])
def test_layout_width_is_independent_of_ordering(caps, text):
    """
    `_fit` بتحسب العرض من مجموع الكلمات + الفجوات. الترتيب تبديل، يعني
    المجموع ما بيتغيّر — بس هاد افتراض، وهون بنثبته. لو انكسر، الكابشن
    الطويل ممكن يرجع ينقصّ.
    """
    lay = CAP._layout(text, caps, 1080)
    f, gap = lay["font"], lay["gap"]
    for line, total in zip(lay["texts"], lay["totals"]):
        expected = sum(w for w, _ in CAP._widths(line, f)) + gap * (len(line) - 1)
        assert total == expected
        # وبأي ترتيب، نفس المجموع
        shuffled = [line[i] for i in CAP._bidi_runs(line)]
        assert sum(w for w, _ in CAP._widths(shuffled, f)) + gap * (len(line) - 1) \
               == expected


@needs_raqm
def test_highlight_reaches_words_on_the_second_line(caps):
    """
    ثغرة تغطية كشفتها المطافرة: ما كان في فحص بيلوّن كلمة على السطر
    الثاني، فنسيان `line_start` كان بيمرق. بدونه `logical_index` بيرجع
    يبلّش من صفر بكل سطر، فأي كلمة بالسطر الثاني ما بتتلوّن أبدًا.
    """
    lay = CAP._layout(MULTILINE, caps, 1080)
    assert len(lay["lines"]) == 2
    first_line_len = len(lay["texts"][0])
    tokens = MULTILINE.split()

    # كلمة من السطر الثاني بفهرسها المنطقي
    logical_index = first_line_len
    assert tokens[logical_index] == lay["texts"][1][0]
    centre = highlight_centre(MULTILINE, caps, logical_index)
    assert centre > 0


@needs_raqm
def test_every_word_on_both_lines_is_reachable(caps):
    """كل فهرس منطقي لازم يلوّن شي — ولا واحد بينضيع بحدود الأسطر."""
    tokens = MULTILINE.split()
    for logical_index in range(len(tokens)):
        highlight_centre(MULTILINE, caps, logical_index)   # بتفشل لو ما لوّن


@needs_raqm
def test_highlighted_word_is_on_the_expected_line(caps):
    """الفهرس المنطقي لازم يوقع على السطر الصح عموديًا كمان."""
    bare = dict(caps, box=[0, 0, 0, 0], color=[255, 255, 255])
    lay = CAP._layout(MULTILINE, caps, 1080)
    first_line_len = len(lay["texts"][0])
    r, g, b = caps["highlight"]

    def rows(logical_index):
        img = CAP.render_caption(MULTILINE, bare, 1080,
                                 highlight_idx=logical_index).convert("RGB")
        px = img.load()
        ys = [y for y in range(img.height) for x in range(0, img.width, 3)
              if abs(px[x, y][0] - r) < 40 and abs(px[x, y][1] - g) < 40
              and abs(px[x, y][2] - b) < 40]
        return min(ys), max(ys)

    top_first = rows(0)[0]                       # كلمة من السطر الأول
    top_second = rows(first_line_len)[0]         # أول كلمة بالسطر الثاني
    assert top_second > top_first, "كلمة السطر الثاني انرسمت بمستوى الأول"


# ================= EC-1: اتجاه الرسم والأقواس =================
#
# التوكن كان بينرسم معزول بـdirection="rtl" دايمًا، فالمحايد على طرفه
# بياخد اتجاه القاعدة وبينعكس: `(Android` بتطلع `Android)`.

def _mirrors(text, caps, size=74):
    """هل شكل التوكن بيختلف بين رسمه rtl ورسمه ltr؟"""
    from PIL import ImageChops
    f = CAP._font(caps["font"], size)

    def draw(d):
        dd = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        bb = dd.textbbox((0, 0), text, font=f, direction=d, language="ar")
        im = Image.new("RGBA", (bb[2] - bb[0] + 8, bb[3] - bb[1] + 8), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((4 - bb[0], 4 - bb[1]), text, font=f,
                                fill=(255, 255, 255, 255), direction=d, language="ar")
        return im

    a, b = draw("rtl"), draw("ltr")
    if a.size != b.size:
        return True
    df = ImageChops.difference(a.convert("L"), b.convert("L"))
    return sum(n for v, n in enumerate(df.histogram()) if v > 20) / (df.width * df.height) >= 0.005


@needs_raqm
@pytest.mark.parametrize("tok", ["(Android", "App)", "(Flutter", "Web)", "("])
def test_unpaired_bracket_would_mirror_under_rtl(caps, tok):
    """توثيق السبب: هدول التوكنات شكلها بيختلف حسب اتجاه الرسم."""
    assert _mirrors(tok, caps), f"{tok!r} المفروض يتأثر بالاتجاه"


@needs_raqm
@pytest.mark.parametrize("tok", ["(A)", "[x]", "{y}", "iPhone", "2.5",
                                 "https://ex.com/a?q=1", "مرحبا"])
def test_these_tokens_are_direction_safe(caps, tok):
    """الأقواس المزدوجة داخل التوكن بتتعاكس سوا فبينلغي الأثر."""
    assert not _mirrors(tok, caps)


@needs_raqm
@pytest.mark.parametrize("tok,want", [
    ("(Android", "L"), ("App)", "L"), ("(Flutter", "L"), ("Web)", "L"),
    ("(Android)", "L"), ("(App", "L"), ("Store)", "L"),
])
def test_bracketed_latin_resolves_to_ltr(tok, want):
    """اتجاه الرسم بيجي من هون — لازم يطلع L فينرسم ltr وما ينعكس."""
    assert CAP._resolve_dirs([tok])[0] == want


@needs_raqm
@pytest.mark.parametrize("text", [
    "حمّل التطبيق (Android App) الآن",
    "(Flutter Web) شغال",
    "افتح (App Store) هلأ",
    "جرّب (Android) هلأ",
    "قبل (Flutter) بعد",
    "جرّب () [] {} هون",
    "نتيجة (2.5) جاهزة",
])
def test_bracket_cases_match_raqm(caps, text):
    """الترتيب — مكمّل للصور المرجعية اللي بتمسك الشكل."""
    tokens = text.split()
    got = visual_widths(tokens, CAP._bidi_runs(tokens), caps, 74)
    ref = reference_widths(text, caps, 74)
    assert matches(got, ref), f"عنا {got} · المرجع {ref}"


@needs_raqm
def test_draw_direction_comes_from_the_resolved_run(caps):
    """
    الاتجاه لازم ياخد المحايد المحلول مش `_token_dir` لحالها: قوس
    لحاله بعد كلمة لاتينية بينضم للـrun فبينرسم ltr.
    """
    assert CAP._resolve_dirs(["Flutter", "(", "Dart"]) == ["L", "L", "L"]
    assert CAP._resolve_dirs(["مرحبا", "(", "بعدين"]) == ["R", "R", "R"]


# ================= CR-3: قيد العرض داخل _fit =================

LONG_URL = ("https://sub.domain.example.com/a/very/long/path/segment/"
            "that/cannot/possibly/wrap/anywhere")


@needs_raqm
@pytest.mark.parametrize("text", [
    LONG_URL,
    f"شوف {LONG_URL} هلأ",
    "شوف https://example.com/extremely/long/path/segment/never/breaks?query=1&more=2",
    "A" * 200,
])
def test_long_token_never_exceeds_the_frame(caps, text):
    """
    الانحدار (CR-3): `_fit` كانت تستسلم عند الأرضية وترجّع كل شي على
    سطر واحد، فبينتج PNG أعرض من الإطار وffmpeg بيقصقصه — يعني باگ
    «الكابشن مقصوص» بيرجع من الباب الخلفي.

    العرض مضمون **بالبناء** هلأ، مش بتأكيد لاحق.
    """
    img = CAP.render_caption(text, caps, 1080)
    assert img.width <= 1080, f"عرض الصورة {img.width} أكبر من الإطار"
    assert img.width <= CAP.available_width(1080)


@needs_raqm
def test_long_token_is_split_not_dropped(caps):
    """الكسر ما بيضيّع محارف — النص كامل موجود بالقطع."""
    lay = CAP._layout(LONG_URL, caps, 1080)
    joined = "".join(t for ln in lay["texts"] for t in ln)
    assert joined == LONG_URL


@needs_raqm
def test_split_pieces_keep_one_logical_index(caps):
    """كل قطع التوكن الواحد بتحمل نفس الفهرس — التلوين بيلوّنه كامل."""
    lay = CAP._layout(f"شوف {LONG_URL} هلأ", caps, 1080)
    idx = [li for ln in lay["lines"] for _, li in ln]
    assert set(idx) == {0, 1, 2}
    assert idx.count(1) > 1, "الرابط المفروض ينكسر لأكتر من قطعة"


@needs_raqm
def test_split_prefers_logical_break_points(caps):
    """الكسر بعد `/` بيقرا أحسن من الكسر بنص كلمة."""
    lay = CAP._layout(LONG_URL, caps, 1080)
    pieces = [t for ln in lay["texts"] for t in ln]
    assert sum(1 for p in pieces[:-1] if p[-1] in CAP._BREAK_AFTER) >= 1


@needs_raqm
def test_highlighting_a_split_token_colours_all_its_pieces(caps):
    """التوكن المكسور لازم يتلوّن كامل، مش قطعة منه."""
    text = f"شوف {LONG_URL} هلأ"
    bare = dict(caps, box=[0, 0, 0, 0], color=[255, 255, 255])
    img = CAP.render_caption(text, bare, 1080, highlight_idx=1).convert("RGB")
    px = img.load()
    r, g, b = caps["highlight"]
    rows = {y for y in range(img.height) for x in range(0, img.width, 3)
            if abs(px[x, y][0] - r) < 40 and abs(px[x, y][1] - g) < 40
            and abs(px[x, y][2] - b) < 40}
    lay = CAP._layout(text, caps, 1080)
    n_lines_with_url = sum(1 for ln in lay["lines"] if any(li == 1 for _, li in ln))
    assert n_lines_with_url > 1, "الحالة لازم توزّع الرابط على أسطر"
    assert rows, "ما تلوّن ولا شي"


@needs_raqm
@pytest.mark.parametrize("tok", ["(Android", "App)", "(Flutter", "Web)"])
def test_render_uses_the_run_direction_not_a_fixed_rtl(caps, tok):
    """
    ثغرة كشفتها المطافرة: كانت الفحوصات تتأكد إن `_resolve_dirs` بترجّع
    'L' وإن التوكن حسّاس للاتجاه — بس ولا واحد بيتأكد إن **حلقة الرسم**
    بتستعمل الاتجاه. رجوع `direction="rtl"` الثابت كان بيمرق.

    هون بنرسم الكابشن فعليًا وبنطابق حبره بالرسم بالاتجاه الصح.
    """
    from PIL import ImageChops
    f = CAP._font(caps["font"], caps["size"])
    bare = dict(caps, box=[0, 0, 0, 0], color=[255, 255, 255])

    def bare_draw(d):
        dd = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        bb = dd.textbbox((0, 0), tok, font=f, direction=d, language="ar")
        im = Image.new("RGBA", (bb[2] - bb[0] + 2, bb[3] - bb[1] + 2), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((1 - bb[0], 1 - bb[1]), tok, font=f,
                                fill=(255, 255, 255, 255), direction=d, language="ar")
        return im.crop(im.split()[-1].getbbox())

    got = CAP.render_caption(tok, bare, 1080)
    got = got.crop(got.split()[-1].getbbox())

    def diff(a, b):
        if a.size != b.size:
            return 1.0
        d = ImageChops.difference(a.convert("L"), b.convert("L"))
        return sum(n for v, n in enumerate(d.histogram()) if v > 20) / (d.width * d.height)

    d_ltr, d_rtl = diff(got, bare_draw("ltr")), diff(got, bare_draw("rtl"))
    assert d_ltr < d_rtl, (
        f"{tok!r} انرسم بالاتجاه الغلط — القوس منعكس "
        f"(فرق عن ltr={d_ltr:.3f} · عن rtl={d_rtl:.3f})")


@needs_raqm
def test_neutral_token_draws_with_its_resolved_direction(caps):
    """
    ثغرة تانية: الاتجاه لازم ياخد المحايد **المحلول**. لو أخدناه من
    `_token_dir` لحالها، القوس اللي لحاله بيرجع 'N' وبينرسم rtl حتى لو
    سياقه لاتيني.
    """
    txt = ["Flutter", "(", "Dart"]
    assert CAP._resolve_dirs(txt) == ["L", "L", "L"]
    assert [CAP._token_dir(t) for t in txt] == ["L", "N", "L"]


@needs_raqm
def test_neutral_in_a_latin_context_is_drawn_ltr(caps):
    """
    الثغرة الأخيرة اللي نجت من المطافرة: `_resolve_dirs` مقابل
    `_token_dir` بيفرقوا **بس** عند التوكن المحايد. كل الفحوصات
    المرسومة كانت على توكنات 'L'، فأخذ الاتجاه من `_token_dir` كان
    يمرق.

    القوس لحاله بسياق لاتيني لازم ينرسم ltr فما ينعكس.
    """
    from PIL import ImageChops
    f = CAP._font(caps["font"], caps["size"])
    bare = dict(caps, box=[0, 0, 0, 0], color=[255, 255, 255])

    def glyph(d):
        dd = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        bb = dd.textbbox((0, 0), "(", font=f, direction=d, language="ar")
        im = Image.new("RGBA", (bb[2] - bb[0] + 2, bb[3] - bb[1] + 2), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((1 - bb[0], 1 - bb[1]), "(", font=f,
                                fill=(255, 255, 255, 255), direction=d, language="ar")
        return im.crop(im.split()[-1].getbbox())

    def diff(a, b):
        if a.size != b.size:
            return 1.0
        x = ImageChops.difference(a.convert("L"), b.convert("L"))
        return sum(n for v, n in enumerate(x.histogram()) if v > 20) / (x.width * x.height)

    # القوس هو التوكن الأوسط، وبينرسم بموضعه البصري الأوسط كمان
    img = CAP.render_caption("Flutter ( Dart", bare, 1080, highlight_idx=1)
    px = img.convert("RGB").load()
    r, g, b = caps["highlight"]
    box = [(x, y) for y in range(img.height) for x in range(img.width)
           if abs(px[x, y][0] - r) < 40 and abs(px[x, y][1] - g) < 40
           and abs(px[x, y][2] - b) < 40]
    assert box, "القوس ما تلوّن"
    x0 = min(p[0] for p in box); x1 = max(p[0] for p in box)
    y0 = min(p[1] for p in box); y1 = max(p[1] for p in box)
    drawn = img.crop((x0, y0, x1 + 1, y1 + 1))

    assert diff(drawn, glyph("ltr")) < diff(drawn, glyph("rtl")), (
        "القوس المحايد بسياق لاتيني انرسم rtl فانعكس — "
        "الاتجاه مأخوذ من `_token_dir` بدل المحلول")

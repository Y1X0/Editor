"""تجميع الكلمات، الملاءمة، وتوقيت إطارات الكاريوكي."""
import pytest

from autoreel import captions as CAP
from conftest import needs_raqm, text_bbox, words

W = 1080


# ------------------------------------------------------------ group_words

def test_splits_on_max_words():
    w = words(*[(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(9)])
    assert [len(g["words"]) for g in CAP.group_words(w, max_words=4)] == [4, 4, 1]


def test_splits_on_time_gap():
    w = words(("a", 0.0, 0.3), ("b", 1.2, 1.5))     # فجوة ٠.٩ > ٠.٥٥
    assert len(CAP.group_words(w, max_words=4)) == 2


def test_group_bounds_come_from_first_and_last_word():
    w = words(("a", 0.2, 0.5), ("b", 0.6, 1.1))
    g = CAP.group_words(w, max_words=4)[0]
    assert (g["start"], g["end"]) == pytest.approx((0.2, 1.1))


def test_words_are_stripped_and_raw_is_kept():
    g = CAP.group_words(words((" آه ", 0.0, 0.4)), max_words=4)[0]
    assert g["words"] == ["آه"] and g["raw"][0]["word"] == " آه "


def test_empty_input():
    assert CAP.group_words([], max_words=4) == []


# ------------------------------------------------------------------ _wrap

def test_wrap_packs_greedily():
    ws = ["aa", "bb", "cc"]
    widths = [(100, 0)] * 3
    assert CAP._wrap(ws, widths, 10, 210) == [["aa", "bb"], ["cc"]]


def test_wrap_gives_one_line_when_everything_fits():
    assert CAP._wrap(["a", "b"], [(50, 0), (50, 0)], 10, 500) == [["a", "b"]]


def test_wrap_refuses_when_a_single_word_is_too_wide():
    """الرفض هو اللي بيخلي `_fit` تكمّل تصغير بدل ما تقصّ الكلمة."""
    assert CAP._wrap(["hugeword"], [(900, 0)], 10, 400) is None


# ------------------------------------------------------------------- _fit

@needs_raqm
@pytest.mark.parametrize("text", [
    "وبيحط كابشن عربي بالاتجاه",
    "الاستراتيجية المسؤوليات الاستثمارات المشروعات",
    "المسؤوليات الاستراتيجية والاستثمارات الاجتماعية بالمستشفيات",
    "الأنثروبولوجيا",
])
def test_fit_never_exceeds_available_width(caps, text):
    size, lines = CAP._fit(text.split(), caps["font"], caps["size"], W - 60)
    pad_x, _, gap = CAP._margins(size)
    f = CAP._font(caps["font"], size)
    for ln in lines:
        total = sum(w for w, _ in CAP._widths(ln, f)) + gap * (len(ln) - 1)
        assert total <= (W - 60) - pad_x * 2


@needs_raqm
def test_fit_keeps_every_word(caps):
    text = "المسؤوليات الاستراتيجية والاستثمارات الاجتماعية بالمستشفيات"
    _, lines = CAP._fit(text.split(), caps["font"], caps["size"], W - 60)
    assert [w for ln in lines for w in ln] == text.split()


@needs_raqm
def test_fit_prefers_the_largest_size(caps):
    """ما في حجم أكبر من المختار بيسع بسطرين — وإلا الاختيار مش الأكبر."""
    text = "المسؤوليات الاستراتيجية والاستثمارات الاجتماعية بالمستشفيات"
    size, _ = CAP._fit(text.split(), caps["font"], caps["size"], W - 60)
    if size < caps["size"]:
        bigger = size + 1
        f = CAP._font(caps["font"], bigger)
        pad_x, _, gap = CAP._margins(bigger)
        lines = CAP._wrap(text.split(), CAP._widths(text.split(), f), gap,
                          (W - 60) - pad_x * 2)
        assert lines is None or len(lines) > CAP._MAX_LINES


@needs_raqm
def test_fit_uses_one_line_when_it_fits_at_that_size(caps):
    _, lines = CAP._fit("وبيعمل زوم عند كل".split(), caps["font"], caps["size"], W - 60)
    assert len(lines) == 1


@needs_raqm
def test_fit_respects_the_floor(caps):
    text = " ".join(["الاستراتيجية"] * 12)
    size, _ = CAP._fit(text.split(), caps["font"], caps["size"], W - 60)
    assert size >= int(caps["size"] * CAP._HARD_MIN)


# --------------------------------------------------------- render_caption

@needs_raqm
@pytest.mark.parametrize("text", [
    "قطة",
    "وبيحط كابشن عربي بالاتجاه",
    "الاستراتيجية المسؤوليات الاستثمارات المشروعات",
    "المسؤوليات الاستراتيجية والاستثمارات الاجتماعية بالمستشفيات",
])
def test_caption_never_clips(caps, text):
    """
    الانحدار الأصلي: النص كان يمتد من -341 لحد 1361 داخل صورة 1020.

    المقارنة `> 0` و`< width` مقصودة مش `>=`: الحبر اللي برّا حدود
    الصورة ما بينكتب أصلًا، فالـbbox عمرها ما بتطلع سالبة. الدليل على
    القصّ هو **ملامسة** العمود صفر أو الأخير — حرف مقصوص بينتهي عند
    الحافة بالضبط، بينما النص السليم وراه هامش `pad_x`.
    """
    img = CAP.render_caption(text, caps, W)
    assert img.width <= W - 60
    bare = dict(caps, box=[0, 0, 0, 0])
    bb = text_bbox(CAP.render_caption(text, bare, W))
    assert bb is not None
    assert bb[0] > 0, "النص ملامس الحافة اليسرى — مقصوص"
    assert bb[2] < img.width, "النص ملامس الحافة اليمنى — مقصوص"


@needs_raqm
def test_first_word_is_drawn_rightmost(caps):
    """
    أهم خاصية بالمشروع كله. بنقيسها بمركز ثقل البكسلات الملوّنة:
    الكلمة الأولى لازم يكون مركزها يمين مركز الكلمة الأخيرة.
    """
    text = "واحد اثنين ثلاثة"
    bare = dict(caps, box=[0, 0, 0, 0], color=[255, 255, 255])

    def hl_centre(i):
        img = CAP.render_caption(text, bare, W, highlight_idx=i).convert("RGB")
        px = img.load()
        r, g, b = caps["highlight"]
        xs = [x for y in range(img.height) for x in range(img.width)
              if abs(px[x, y][0] - r) < 40 and abs(px[x, y][1] - g) < 40
              and abs(px[x, y][2] - b) < 40]
        assert xs, f"ما لقينا بكسلات ملوّنة للكلمة {i}"
        return sum(xs) / len(xs)

    assert hl_centre(0) > hl_centre(1) > hl_centre(2)


@needs_raqm
def test_highlight_lands_on_the_right_word(caps):
    """
    الفحص اللي فوق بيتأكد إن الفهرس ٠ أقصى اليمين — بس لو انعكس النص
    والفهرس سوا (باگ «العربي مقلوب») العلاقة بتضل صحيحة وبيمرق.

    فهون بنقيس **عرض** الكتلة الملوّنة ونطابقه بالكلمة المقصودة.
    الكلمتين مختلفتين بالعرض عمدًا، فالخلط بينهن بينكشف.

    المقارنة نسبية مش بعتبة مطلقة: قياس البكسلات بيقصّ حواف التنعيم
    فبيطلع أضيق ~10px بشكل منهجي. المهم إن العرض المرسوم يكون **أقرب**
    لعرض الكلمة المقصودة منه لأي كلمة تانية — وهاد مستقل عن إصدار الخط.
    """
    words_ = ["مي", "الاستراتيجية"]           # فرق عرض كبير عمدًا
    text = " ".join(words_)
    bare = dict(caps, box=[0, 0, 0, 0], color=[255, 255, 255])
    size, _ = CAP._fit(words_, caps["font"], caps["size"], W - 60)
    f = CAP._font(caps["font"], size)
    expected = [CAP._widths([w], f)[0][0] for w in words_]
    r, g, b = caps["highlight"]

    for i, word in enumerate(words_):
        img = CAP.render_caption(text, bare, W, highlight_idx=i).convert("RGB")
        px = img.load()
        xs = [x for y in range(img.height) for x in range(img.width)
              if abs(px[x, y][0] - r) < 40 and abs(px[x, y][1] - g) < 40
              and abs(px[x, y][2] - b) < 40]
        assert xs, f"ما في بكسلات ملوّنة للفهرس {i}"
        drawn = max(xs) - min(xs)
        nearest = min(range(len(words_)), key=lambda j: abs(drawn - expected[j]))
        assert nearest == i, (
            f"الفهرس {i} المفروض يلوّن «{word}» (~{expected[i]}px) بس الكتلة "
            f"الملوّنة عرضها {drawn}px، وهاد أقرب لـ«{words_[nearest]}» "
            f"(~{expected[nearest]}px) — الكلمات مرسومة بترتيب مقلوب")


@needs_raqm
def test_karaoke_frames_share_one_size(caps):
    """لو المقاس تغيّر بين الإطارات، الكابشن بيرقص بالفيديو."""
    text = "الاستراتيجية المسؤوليات الاستثمارات المشروعات"
    sizes = {CAP.render_caption(text, caps, W, highlight_idx=i).size for i in range(4)}
    assert len(sizes) == 1


@needs_raqm
def test_each_karaoke_frame_differs(caps):
    text = "واحد اثنين ثلاثة"
    frames = {CAP.render_caption(text, caps, W, highlight_idx=i).tobytes()
              for i in range(3)}
    assert len(frames) == 3


@needs_raqm
def test_fit_cache_key_covers_size_and_width(caps):
    """الكاش لازم يميّز الحجم والعرض، وإلا تغيير الconfig بيرجّع نتيجة قديمة."""
    text = "الاستراتيجية المسؤوليات الاستثمارات المشروعات"
    warm = CAP._fit(text.split(), caps["font"], caps["size"],
                    CAP.available_width(W))
    CAP.render_caption(text, caps, W)
    CAP.render_caption(text, dict(caps, size=40), W)
    CAP.render_caption(text, caps, 1440)
    lay = CAP._LAYOUT_CACHE[(text, caps["font"], caps["size"], W)]
    assert (lay["size"], lay["lines"]) == warm
    assert len(CAP._LAYOUT_CACHE) == 3


@needs_raqm
def test_blank_text_does_not_crash(caps):
    assert CAP.render_caption("   ", caps, W).size == (1, 1)


# ------------------------------------------------------ build_caption_pngs

def _frames(caps, w, outdir, bridge_gap=CAP.DEFAULT_BRIDGE_GAP, max_words=4):
    groups = CAP.group_words(w, max_words)
    return groups, CAP.build_caption_pngs(groups, caps, W, str(outdir),
                                          bridge_gap=bridge_gap)


@needs_raqm
def test_no_dead_air_inside_a_group(caps, tmp_path):
    """الانحدار: الإطار كان بينتهي عند نهاية كلمته فبيطفي الكابشن بالفراغ."""
    w = words(("هاد", 0.00, 0.30), ("المشروع", 0.35, 0.70),
              ("بيقص", 1.20, 1.55), ("الفيديو", 1.60, 2.00))
    groups, frames = _frames(caps, w, tmp_path)
    assert len(groups) == 1
    for (_, _, e), (_, s2, _) in zip(frames, frames[1:]):
        assert e == pytest.approx(s2)


@needs_raqm
@pytest.mark.parametrize("gap,bridged", [
    (0.30, True), (0.40, True), (0.42, True), (0.44, True),
    (0.45, True),        # بتساوي min_gap بالضبط -> بتنجى من القص فلازم تنجسر
    (0.46, False), (1.00, False),
])
def test_bridging_window(caps, tmp_path, gap, bridged):
    w = words(("واحد", 0.0, 0.4), ("اثنين", 0.45, 0.9),
              ("ثلاثة", 0.9 + gap, 1.3 + gap), ("أربعة", 1.35 + gap, 1.7 + gap))
    groups, frames = _frames(caps, w, tmp_path, bridge_gap=0.45, max_words=2)
    assert len(groups) == 2
    end_of_first = frames[1][2]
    assert (end_of_first == pytest.approx(groups[1]["start"])) is bridged


@needs_raqm
def test_single_word_group_also_bridges(caps, tmp_path):
    w = words(("واحد", 0.0, 0.4), ("اثنين", 0.6, 1.0))
    groups, frames = _frames(caps, w, tmp_path, bridge_gap=0.45, max_words=1)
    assert frames[0][2] == pytest.approx(groups[1]["start"])


@needs_raqm
def test_last_group_is_never_extended(caps, tmp_path):
    w = words(("واحد", 0.0, 0.4), ("اثنين", 0.5, 0.9))
    groups, frames = _frames(caps, w, tmp_path)
    assert frames[-1][2] == pytest.approx(groups[-1]["end"])


@needs_raqm
def test_frames_never_overlap(caps, tmp_path):
    w = words(*[(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(10)])
    _, frames = _frames(caps, w, tmp_path)
    for (_, _, e), (_, s2, _) in zip(frames, frames[1:]):
        assert e <= s2 + 1e-9


@needs_raqm
def test_no_orphan_png_files(caps, tmp_path):
    """الإطار المرفوض (مدته ≈ صفر) ما لازم يخلّف ملف على القرص."""
    w = words(("آه", 1.0, 1.0), ("تمام", 1.0, 1.6))
    _, frames = _frames(caps, w, tmp_path)
    assert len(list(tmp_path.iterdir())) == len(frames)


@needs_raqm
def test_every_frame_has_positive_duration(caps, tmp_path):
    w = words(*[(f"w{i}", i * 0.4, i * 0.4 + 0.3) for i in range(8)])
    _, frames = _frames(caps, w, tmp_path)
    assert frames and all(e > s for _, s, e in frames)


@needs_raqm
def test_empty_groups_produce_nothing(caps, tmp_path):
    assert CAP.build_caption_pngs([], caps, W, str(tmp_path)) == []

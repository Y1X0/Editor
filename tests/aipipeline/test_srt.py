"""SRT ──► `Alignment` **على النص المصدر**.

المسؤولية هون مش تقطيع SRT — هي **الربط والتحقّق**. فمعظم الفحوص عن
الرفض: أي SRT ما بيطابق المصدر بيوقف المسار، لأن التقريب بينتج فيديو
نصّه مزحلق عن صوته، وهاد بينكتشف بعد الرفع مش قبله.
"""
import pytest

from ai_pipeline.errors import AlignmentError
from ai_pipeline.srt import alignment_from_srt, parse_cues

SRT = """\
1
00:00:00,500 --> 00:00:02,500
الحمد لله

2
00:00:03,000 --> 00:00:05,000
رب العالمين
"""
TOKENS = ("الحمد", "لله", "رب", "العالمين")


@pytest.fixture
def srt(tmp_path):
    def write(text):
        p = tmp_path / "s.srt"
        p.write_text(text, encoding="utf-8")
        return p
    return write


# ── الحالة الصحيحة ───────────────────────────────────────────────────
def test_a_matching_srt_becomes_an_alignment(srt):
    a = alignment_from_srt(srt(SRT), TOKENS)
    assert [w.text for w in a.words] == list(TOKENS)
    assert [w.i for w in a.words] == [0, 1, 2, 3]
    # التوزيع المتساوي داخل الكتلة: ٢ ثانية على كلمتين
    assert (a.words[0].start, a.words[0].end) == (0.5, 1.5)
    assert (a.words[1].start, a.words[1].end) == (1.5, 2.5)
    assert (a.words[2].start, a.words[3].end) == (3.0, 5.0)


def test_cue_boundaries_survive_exactly(srt):
    """حدود الجُمل **مضبوطة**، وحدود الكلمات جوّاها تقريبية.

    وهاد اللي بيخلي التقريب مقبولًا: الوكيل بيقسم عند حدود معنى، فبداية
    أول كلمة ونهاية آخر وحدة بكل مقطع بتيجي من الـSRT كما هي.
    """
    a = alignment_from_srt(srt(SRT), TOKENS)
    assert a.words[0].start == 0.5 and a.words[1].end == 2.5
    assert a.words[2].start == 3.0 and a.words[3].end == 5.0


def test_dot_separated_timestamps_are_accepted(srt):
    a = alignment_from_srt(srt(SRT.replace(",", ".")), TOKENS)
    assert a.words[0].start == 0.5


# ── الرفض: المطابقة مع المصدر ────────────────────────────────────────
def test_a_word_count_mismatch_fails(srt):
    with pytest.raises(AlignmentError, match="المحاذاة لازم تكون على المصدر"):
        alignment_from_srt(srt(SRT), TOKENS + ("زيادة",))


def test_a_single_changed_letter_fails(srt):
    """§19 على مستوى المحاذاة: ولا حرف بيتغيّر.

    `العالمين` -> `العالمون` — نفس عدد الكلمات ونفس التوقيت، وحرف واحد
    مختلف. لو مرقت، الكابشن بينرسم من المصدر والصوت من نصّ تاني.
    """
    bad = SRT.replace("العالمين", "العالمون")
    with pytest.raises(AlignmentError, match="ولا حرف بيتغيّر"):
        alignment_from_srt(srt(bad), TOKENS)


def test_reordered_words_fail(srt):
    bad = SRT.replace("الحمد لله", "لله الحمد")
    with pytest.raises(AlignmentError, match="كلمة 0"):
        alignment_from_srt(srt(bad), TOKENS)


# ── الرفض: بنية الـSRT ───────────────────────────────────────────────
def test_a_reversed_cue_fails(srt):
    bad = SRT.replace("00:00:00,500 --> 00:00:02,500",
                      "00:00:02,500 --> 00:00:00,500")
    with pytest.raises(AlignmentError, match="مدة غير صالحة"):
        alignment_from_srt(srt(bad), TOKENS)


def test_overlapping_cues_fail(srt):
    bad = SRT.replace("00:00:03,000 -->", "00:00:01,000 -->")
    with pytest.raises(AlignmentError, match="متداخلة"):
        alignment_from_srt(srt(bad), TOKENS)


def test_a_cue_too_short_for_its_words_fails(srt):
    """مدة أقصر من أن تنمثّل بتفشل **باسم الكتلة**، مش باسم كلمة.

    `Word` بترفض `end <= start` على أي حال، بس رسالتها بتحكي عن كلمة
    وبتوجّه القارئ لمكان غلط — السبب بالكتلة اللي فيها كلمات أكتر من
    وقتها.
    """
    bad = "1\n00:00:01,000 --> 00:00:01,001\n" + " ".join(TOKENS) + "\n"
    with pytest.raises(AlignmentError, match="أقصر من أن تنمثّل"):
        alignment_from_srt(srt(bad), TOKENS)


def test_a_missing_file_fails(tmp_path):
    with pytest.raises(AlignmentError, match="مفقود"):
        alignment_from_srt(tmp_path / "nope.srt", TOKENS)


def test_a_file_with_no_cues_fails(srt):
    with pytest.raises(AlignmentError, match="ولا كتلة صالحة"):
        alignment_from_srt(srt("مجرد نص بلا توقيت\n"), TOKENS)


# ── الفخّ الموثَّق: كتلة بلا نص ───────────────────────────────────────
def test_an_empty_cue_does_not_swallow_the_next_block(srt):
    """الفخّ اللي التقسيم على السطر الفاضي موجود عشانه.

    الشكل القديم (regex وحدة بتمتد للملف كله) كان بيخلّي كتلة نصّها
    فاضي تبلع سطر الرقم وسطر التوقيت للكتلة الجاية، فبيصيروا «كلمات»:
    `2` · `00:00:03,000` · `-->`. الفحص هون بيثبت إنهن ما بيوصلوا
    للمحاذاة.
    """
    text = ("1\n00:00:00,500 --> 00:00:02,000\n\n"
            "2\n00:00:03,000 --> 00:00:05,000\nرب العالمين\n")
    cues = parse_cues(text)
    assert len(cues) == 1                       # الفاضية انتجاهلت
    assert cues[0][2] == ["رب", "العالمين"]
    a = alignment_from_srt(srt(text), ("رب", "العالمين"))
    assert [w.text for w in a.words] == ["رب", "العالمين"]
    assert not {"2", "00:00:03,000", "-->"} & {w.text for w in a.words}

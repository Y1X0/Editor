"""قراءة SRT — البديل عن Whisper."""
import pytest

from autoreel.transcribe import from_srt

BASIC = """1
00:00:00,300 --> 00:00:02,300
كلمة كلمتين

2
00:00:05,000 --> 00:00:06,000
ثلاثة
"""


def write(tmp_path, text, newline="\n", name="s.srt"):
    p = tmp_path / name
    p.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return str(p)


def test_parses_blocks_and_splits_words(tmp_path):
    out = from_srt(write(tmp_path, BASIC))
    assert [w["word"] for w in out] == ["كلمة", "كلمتين", "ثلاثة"]


def test_time_is_split_evenly_across_words(tmp_path):
    out = from_srt(write(tmp_path, BASIC))
    assert out[0]["start"] == pytest.approx(0.3)
    assert out[0]["end"] == pytest.approx(1.3)      # نص المدة
    assert out[1]["start"] == pytest.approx(1.3)
    assert out[1]["end"] == pytest.approx(2.3)


def test_single_word_block_spans_full_duration(tmp_path):
    out = from_srt(write(tmp_path, BASIC))
    assert (out[2]["start"], out[2]["end"]) == pytest.approx((5.0, 6.0))


def test_crlf_line_endings(tmp_path):
    """الفتح بالوضع النصي بيوحّد نهايات السطور، فملفات ويندوز بتشتغل."""
    assert from_srt(write(tmp_path, BASIC, newline="\r\n")) == \
           from_srt(write(tmp_path, BASIC, name="lf.srt"))


def test_dot_decimal_separator(tmp_path):
    out = from_srt(write(tmp_path, BASIC.replace(",", ".")))
    assert out[0]["start"] == pytest.approx(0.3)


def test_multiline_caption_is_joined(tmp_path):
    src = "1\n00:00:00,000 --> 00:00:04,000\nسطر أول\nسطر تاني\n"
    assert [w["word"] for w in from_srt(write(tmp_path, src))] == \
           ["سطر", "أول", "سطر", "تاني"]


@pytest.mark.parametrize("blank", ["   ", "", "\t"])
def test_blocks_with_no_text_are_skipped(tmp_path, blank):
    """الكتلة الفاضية ما لازم تبلع سطر الرقم والتوقيت للكتلة اللي بعدها."""
    src = (f"1\n00:00:00,000 --> 00:00:01,000\n{blank}\n\n"
           "2\n00:00:02,000 --> 00:00:03,000\nآه\n")
    assert [w["word"] for w in from_srt(write(tmp_path, src))] == ["آه"]


def test_timestamps_never_leak_into_words(tmp_path):
    """أوضح عرَض للباگ القديم: `-->` بتطلع ككلمة كابشن."""
    src = ("1\n00:00:00,000 --> 00:00:01,000\n\n\n"
           "2\n00:00:02,000 --> 00:00:03,000\nنعم\n")
    got = [w["word"] for w in from_srt(write(tmp_path, src))]
    assert "-->" not in got and not any(":" in w for w in got)


def test_block_with_reversed_times_is_skipped(tmp_path):
    src = "1\n00:00:05,000 --> 00:00:02,000\nمقلوب\n"
    assert from_srt(write(tmp_path, src)) == []


def test_trailing_blank_lines_do_not_add_words(tmp_path):
    src = "1\n00:00:00,000 --> 00:00:01,000\nآه\n\n\n\n"
    assert [w["word"] for w in from_srt(write(tmp_path, src))] == ["آه"]


def test_indented_and_padded_text_still_parses(tmp_path):
    """الفراغات حوالين النص سليمة — المشكلة بس لما الكتلة بلا نص إطلاقًا."""
    src = ("1\n00:00:00,000 --> 00:00:01,000\n  آه\n\n"
           "2\n00:00:02,000 --> 00:00:03,000\nنعم\n")
    assert [w["word"] for w in from_srt(write(tmp_path, src))] == ["آه", "نعم"]


def test_hours_are_honoured(tmp_path):
    src = "1\n01:02:03,500 --> 01:02:04,500\nبعيد\n"
    assert from_srt(write(tmp_path, src))[0]["start"] == pytest.approx(3723.5)


def test_empty_file(tmp_path):
    assert from_srt(write(tmp_path, "")) == []


def test_words_are_ordered(tmp_path):
    out = from_srt(write(tmp_path, BASIC))
    assert [w["start"] for w in out] == sorted(w["start"] for w in out)
    for w in out:
        assert w["end"] > w["start"]


# --------------------------------------------------------- cache_path

def test_cache_path_includes_model_and_language():
    """
    الانحدار: المفتاح كان مسار الملف بس، فتغيير whisper_model أو
    language بيرجّع تفريغ قديم بصمت.
    """
    from autoreel.transcribe import cache_path
    a = cache_path("/v/raw.mp4", "small", "ar")
    assert cache_path("/v/raw.mp4", "medium", "ar") != a
    assert cache_path("/v/raw.mp4", "small", "en") != a
    assert cache_path("/v/other.mp4", "small", "ar") != a


def test_cache_path_is_still_gitignored():
    from autoreel.transcribe import cache_path
    assert cache_path("/v/raw.mp4", "small", "ar").endswith(".words.json")


def test_cache_path_sits_next_to_the_video():
    import os
    from autoreel.transcribe import cache_path
    assert os.path.dirname(cache_path("/v/raw.mp4", "small", "ar")) == "/v"

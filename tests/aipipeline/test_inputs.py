"""§1 صوت مفقود · §19 بلا تيار صوت."""
import subprocess

import pytest

from ai_pipeline.errors import AlignmentError, AssetError, ContractError
from ai_pipeline.validation.inputs import (
    check_audio_matches_alignment, check_script, probe_audio,
)
from shared.ffmpeg import exe


@pytest.fixture(scope="module")
def wav(tmp_path_factory):
    p = tmp_path_factory.mktemp("in") / "a.wav"
    subprocess.run([exe(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "sine=f=440:d=3", "-ar", "48000", str(p)], check=True)
    return p


@pytest.mark.ffmpeg
def test_a_real_audio_file_probes(wav):
    dur, codec, sr = probe_audio(wav)
    assert abs(dur - 3.0) < 0.05 and sr == 48000 and codec.startswith("pcm")


def test_missing_audio_fails(tmp_path):
    with pytest.raises(AssetError, match="ملف الصوت مفقود"):
        probe_audio(tmp_path / "nope.wav")


def test_zero_byte_audio_fails(tmp_path):
    p = tmp_path / "empty.wav"; p.write_bytes(b"")
    with pytest.raises(AssetError, match="فاضي"):
        probe_audio(p)


@pytest.mark.ffmpeg
def test_a_file_with_no_audio_stream_fails(tmp_path):
    p = tmp_path / "silent.mp4"
    subprocess.run([exe(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc=d=1:r=30", "-an", str(p)], check=True)
    with pytest.raises(AssetError, match="ولا تيار صوت"):
        probe_audio(p)


@pytest.mark.ffmpeg
def test_a_file_that_is_not_media_fails(tmp_path):
    p = tmp_path / "junk.wav"; p.write_bytes(b"NOT MEDIA" * 40)
    with pytest.raises(AssetError):
        probe_audio(p)


def test_alignment_may_not_outrun_the_audio(alignment):
    check_audio_matches_alignment(alignment.words[-1].end + 0.5, alignment)
    with pytest.raises(AlignmentError, match="بتتجاوز الصوت"):
        check_audio_matches_alignment(alignment.words[-1].end - 0.5, alignment)


def test_missing_script_fails(tmp_path):
    with pytest.raises(ContractError, match="النص المصدر مفقود"):
        check_script(tmp_path / "script.txt")


def test_empty_script_fails(tmp_path):
    p = tmp_path / "script.txt"; p.write_text("  \n\n")
    with pytest.raises(ContractError, match="النص المصدر فاضي"):
        check_script(p)


def test_script_is_returned_verbatim(tmp_path):
    """ولا تطبيع عند القراءة — النص المقروء هو النص المرسوم."""
    text = "وَمَن يَتَوَكَّلْ\tعَلَى  اللَّهِ\n"
    p = tmp_path / "script.txt"; p.write_text(text, encoding="utf-8")
    assert check_script(p) == text

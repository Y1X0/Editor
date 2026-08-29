"""
`graph.music_chain` — الموسيقى الخلفية.

مسار الصوت هو أخطر مسار بالمشروع: كل خلل فيه صامت. فالفحوص هون على
نفس القواعد اللي فرضها `sfx_chain`، مش على الشكل.
"""
import pytest

from autoreel import graph as G

TOTAL = 48000 * 5


def chain(**kw):
    return "\n".join(G.music_chain(2, total_samples=TOTAL, **kw))


def test_aformat_comes_before_any_sample_index():
    """
    `atrim`/`afade` بيعدّوا عيّنات بمعدّل **المدخَل**. أصل 44.1k بلا
    `aformat` قبلهن بينزاح +٨٨ms بلا أي تحذير من ffmpeg.
    """
    c = chain()
    assert c.index("aformat") < c.index("atrim")
    assert c.index("aformat") < c.index("afade")


def test_normalize_is_off():
    """بدونها `amix` بتقسّم على عدد المدخلات فالكلام بيخفت للنص."""
    assert "normalize=0" in chain()


def test_length_is_pinned_by_construction():
    """
    الطول قرارنا مش قرار `amix` — نفس الحادثة اللي كسرت ٤ فحوص على
    ffmpeg 6.1.1 (`duration=first` بتعطي ١٢٨٠ عيّنة أقل).
    """
    c = chain()
    assert c.count(f"atrim=end_sample={TOTAL}") >= 2
    assert "apad" in c


def test_fades_use_sample_indices_not_seconds():
    """الفهرس هو الزمن بهالمشروع — وما في سبب نكسر القاعدة للتلاشي."""
    c = chain(fade=1.0)
    assert "start_sample=0:nb_samples=48000" in c
    assert f"start_sample={TOTAL - 48000}" in c
    assert ":st=" not in c and ":d=" not in c


def test_headroom_guard_rejects_a_clipping_pair():
    """الهامش بالحساب مش بالحظ: مجموع الكسبين لازم < ١.٠."""
    with pytest.raises(ValueError, match="هامش"):
        G.music_chain(2, total_samples=TOTAL, gain=0.5, speech_gain=0.6)
    with pytest.raises(ValueError, match="هامش"):
        G.music_chain(2, total_samples=TOTAL, gain=0.3, speech_gain=0.7)


def test_default_gains_leave_real_headroom():
    s = G.DEFAULT_MUSIC_SPEECH_GAIN + G.DEFAULT_MUSIC_GAIN
    assert s < 1.0, s
    # والناقل مع المؤثرات ≤ ٠.٩٢٥، فالمجموع الفعلي أقل كمان
    assert 0.925 * G.DEFAULT_MUSIC_SPEECH_GAIN + G.DEFAULT_MUSIC_GAIN < 1.0


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_gains_outside_zero_one_are_rejected(bad):
    with pytest.raises(ValueError):
        G.music_chain(2, total_samples=TOTAL, gain=bad)
    with pytest.raises(ValueError):
        G.music_chain(2, total_samples=TOTAL, speech_gain=bad)


def test_a_fade_longer_than_the_clip_does_not_go_negative():
    """`start_sample` سالبة = تعبير فلتر مكسور."""
    c = "\n".join(G.music_chain(2, total_samples=1000, fade=99.0))
    assert "start_sample=-" not in c


def test_audio_chain_leaves_the_path_untouched_without_music():
    """بلا موسيقى ما بينضاف ولا فلتر — المخرَج متطابق مع ما قبل الميزة."""
    a = G.audio_chain(30, [0], [150], ["ao0"])
    b = G.audio_chain(30, [0], [150], ["ao0"], music_input=None)
    assert a == b
    assert not any("amix" in p for p in a)


def test_music_mixes_onto_the_bus_after_sfx():
    """
    الموسيقى بعد المؤثرات: الهامش بينحسب على ناقل واحد معروف بدل
    مجموع فروع متفرّقة.
    """
    from autoreel.sfx import Cue
    cues = [Cue(frame=0, sample=0, kind="start", asset="impact", gain=0.3)]
    parts = G.audio_chain(30, [0], [150], ["ao0"], cues=cues,
                          sfx_inputs={"impact": 3}, music_input=2)
    txt = "\n".join(parts)
    assert txt.index("[amixed]") < txt.index("[amus]")

import pytest

from ai_pipeline.models.alignment import Alignment, Word
from ai_pipeline.models.assets import Asset, AssetsContract, Probe
from ai_pipeline.models.project import Output
from ai_pipeline.models.segments import Segment, SegmentsContract
from ai_pipeline.source import tokenize

SCRIPT = "وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ إِنَّ اللَّهَ بَالِغُ أَمْرِهِ"
# 0    1        2      3       4      5       6    7        8      9


@pytest.fixture
def tokens():
    return tokenize(SCRIPT)


@pytest.fixture
def alignment(tokens):
    """توقيت واقعي: كل كلمة ~0.55s مع فراغ صغير."""
    ws, t = [], 0.82
    for i, w in enumerate(tokens):
        ws.append(Word(i=i, text=w, start=round(t, 3), end=round(t + 0.48, 3), conf=0.9))
        t += 0.55
    return Alignment(method="test", words=tuple(ws))


@pytest.fixture
def segments(tokens):
    def seg(sid, a, b):
        return Segment(
            segment_id=sid, word_start=a, word_end=b,
            text_arabic=" ".join(tokens[a:b]),
            visual_mood_prompt="dark moody rain on a window, charcoal and gold",
        )
    return SegmentsContract(segments=(seg(1, 0, 4), seg(2, 4, 7), seg(3, 7, 10)))


@pytest.fixture
def assets(tmp_path):
    out = []
    for sid in (1, 2, 3):
        p = tmp_path / f"seg{sid}.mp4"
        p.write_bytes(b"\0")
        out.append(Asset(
            segment_id=sid, source_type="local", provider="fixture",
            provider_ref=f"f{sid}", file_path=p, sha256="a" * 64,
            license="test", probe=Probe(width=3840, height=2160, fps=25.0, duration=30.0),
            in_point=0.0, fit="cover", motion="none",
        ))
    return AssetsContract(assets=tuple(out))


@pytest.fixture
def output():
    return Output()


@pytest.fixture
def audio_duration(alignment):
    return alignment.words[-1].end + 0.5

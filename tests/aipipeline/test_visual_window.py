"""النافذة البصرية — مين بيملك المدة.

الجواب اللي بينثبت هون: **`alignment.json` عبر `quantize`**. مش الوكيل،
ولا الـfixture، ولا الـResolver، ولا فهارس الكلمات معاملة كثواني.
"""
import ast
import json
import pathlib

import pytest

from ai_pipeline.agents.expand import ThemeView
from ai_pipeline.agents.resolver import Catalog, CatalogEntry, resolve_assets
from ai_pipeline.agents.schemas import AssetIntent, SegmentsProposal
from ai_pipeline.agents.expand import expand_segments_proposal
from ai_pipeline.errors import AssetError, TimelineError
from ai_pipeline.models.alignment import Alignment, Word
from ai_pipeline.models.assets import Probe
from ai_pipeline.models.project import Output
from ai_pipeline.source import tokenize
from ai_pipeline.timeline.quantize import quantize
from ai_pipeline.window import required_seconds, visual_windows

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = "وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ إِنَّ اللَّهَ بَالِغُ أَمْرِهِ"
TOKENS = tokenize(SRC)
OUT = Output()


def alignment(start=0.82, step=0.55, span=0.48) -> Alignment:
    return Alignment(method="t", words=tuple(
        Word(i=i, text=w, start=round(start + i * step, 3),
             end=round(start + i * step + span, 3))
        for i, w in enumerate(TOKENS)))


def segments(*spans):
    spans = spans or ((0, 4), (4, 7), (7, 10))
    return expand_segments_proposal(SegmentsProposal.model_validate_json(
        json.dumps({"segments": [
            {"segment_id": i, "word_start": a, "word_end": b,
             "visual_mood_prompt": f"mood {i}"}
            for i, (a, b) in enumerate(spans, 1)]})), TOKENS)


def audio(al):
    return round(max(w.end for w in al.words) + 0.5, 3)


# ══ الحتمية ═════════════════════════════════════════════════════════
def test_the_same_alignment_gives_the_same_durations():
    al, seg = alignment(), segments()
    a = required_seconds(OUT, seg, al, audio(al))
    b = required_seconds(OUT, seg, al, audio(al))
    assert a == b
    assert set(a) == {1, 2, 3} and all(v > 0 for v in a.values())


def test_a_different_alignment_gives_different_durations():
    seg = segments()
    a = required_seconds(OUT, seg, al1 := alignment(step=0.55), audio(al1))
    b = required_seconds(OUT, seg, al2 := alignment(step=0.90), audio(al2))
    assert a != b, "المدة ما بتتبع المحاذاة"
    assert b[1] > a[1]


def test_shifting_the_start_moves_only_the_first_window():
    """المقطع الأول بيبلّش من الإطار صفر، فتأخير الكلام بيمدّده هو."""
    seg = segments()
    a = required_seconds(OUT, seg, al1 := alignment(start=0.82), audio(al1))
    b = required_seconds(OUT, seg, al2 := alignment(start=2.00), audio(al2))
    assert b[1] > a[1]
    assert round(b[1] - a[1], 3) == pytest.approx(2.00 - 0.82, abs=1 / 30)


# ══ النافذة البصرية ≠ نافذة النطق ══════════════════════════════════
def test_the_first_window_starts_at_zero_not_at_the_first_word():
    al = alignment(start=0.82)
    w = visual_windows(OUT, segments(), al, audio(al))
    assert w[1][0] == 0.0, "النافذة بلّشت مع الكلام بدل ما تبلّش من الصفر"
    assert al.words[0].start > 0.5


def test_the_last_window_ends_at_the_end_of_the_strip():
    al = alignment()
    dur = audio(al)
    w = visual_windows(OUT, segments(), al, dur)
    assert w[3][1] == pytest.approx(round(dur * 30) / 30, abs=1e-6)


def test_the_windows_tile_the_whole_strip_without_gaps():
    al = alignment()
    w = visual_windows(OUT, segments(), al, audio(al))
    edges = [w[i] for i in sorted(w)]
    for (_, end), (start, _) in zip(edges, edges[1:]):
        assert end == start, "فجوة بين نافذتين"


def test_a_window_is_longer_than_its_spoken_span():
    al, seg = alignment(), segments()
    need = required_seconds(OUT, seg, al, audio(al))
    for s in seg.segments:
        t0, t1 = al.span_time(s.word_start, s.word_end)
        assert need[s.segment_id] >= t1 - t0 - 1 / 30
    assert need[1] > al.span_time(0, 4)[1] - al.span_time(0, 4)[0]


# ══ السلطة: نفس أرقام quantize ═════════════════════════════════════
def test_the_durations_match_quantize_frame_for_frame():
    """**الحارس الأهم.** لو صار تعريفان للقاعدة، هون بينكشف الفرق."""
    al, seg = alignment(), segments()
    dur = audio(al)
    need = required_seconds(OUT, seg, al, dur)
    cat_probe = Probe(width=1920, height=1080, fps=25.0, duration=dur + 5)
    from ai_pipeline.models.assets import Asset, AssetsContract
    assets = AssetsContract(assets=tuple(
        Asset(segment_id=s.segment_id, source_type="local", provider="p",
              provider_ref=f"r{s.segment_id}", file_path=pathlib.Path("x.mp4"),
              sha256="1" * 64, license="L", probe=cat_probe)
        for s in seg.segments))
    tl = quantize(OUT, seg, al, assets, dur)
    for span in tl.visual_spans:
        assert need[span.segment_id] == pytest.approx(
            span.n_frames / OUT.fps, abs=1e-6), (
            f"مقطع {span.segment_id}: النافذة {need[span.segment_id]} "
            f"و`quantize` {span.n_frames} إطار")


def test_the_windows_do_not_depend_on_the_assets():
    """الأصول الاستقصائية داخلية — تغييرها ما بيغيّر النافذة."""
    al, seg = alignment(), segments()
    a = required_seconds(OUT, seg, al, audio(al))
    import ai_pipeline.window as W
    orig = W._PROBE_MARGIN_S
    try:
        W._PROBE_MARGIN_S = 99.0
        assert required_seconds(OUT, seg, al, audio(al)) == a
    finally:
        W._PROBE_MARGIN_S = orig


# ══ المدة ما بتيجي من الوكيل ═══════════════════════════════════════
def test_the_proposal_cannot_change_the_duration():
    """نفس المدى، نيّة بصرية مختلفة تمامًا = نفس المدة."""
    al = alignment()
    a = required_seconds(OUT, segments(), al, audio(al))
    other = expand_segments_proposal(SegmentsProposal.model_validate_json(
        json.dumps({"segments": [
            {"segment_id": i, "word_start": s, "word_end": e,
             "visual_mood_prompt": "x" * 300}
            for i, (s, e) in enumerate(((0, 4), (4, 7), (7, 10)), 1)]})),
        TOKENS)
    assert required_seconds(OUT, other, al, audio(al)) == a


def test_the_window_module_never_reads_an_intent_or_a_provider():
    src = (ROOT / "ai_pipeline/window.py").read_text("utf-8")
    for node in ast.walk(ast.parse(src)):
        mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                else [node.module] if isinstance(node, ast.ImportFrom)
                and node.module else [])
        for m in mods:
            for bad in ("agents", "anthropic", "schemas", "providers"):
                assert bad not in m, f"window مربوط بطبقة النموذج — {m}"


def test_the_resolver_never_recomputes_the_duration():
    src = (ROOT / "ai_pipeline/agents/resolver.py").read_text("utf-8")
    for node in ast.walk(ast.parse(src)):
        mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                else [node.module] if isinstance(node, ast.ImportFrom)
                and node.module else [])
        for m in mods:
            for bad in ("window", "quantize", "alignment"):
                assert bad not in m, f"الـresolver بيعيد حساب المدة — {m}"


# ══ الفشل المقفول ═══════════════════════════════════════════════════
@pytest.mark.parametrize("dur", [0.0, -1.0])
def test_a_non_positive_audio_duration_fails(dur):
    with pytest.raises(TimelineError, match="غير صالحة"):
        required_seconds(OUT, segments(), alignment(), dur)


def test_an_audio_shorter_than_a_frame_fails():
    with pytest.raises(TimelineError, match="أقصر من إطار"):
        required_seconds(OUT, segments(), alignment(), 0.01)


def test_word_bounds_beyond_the_alignment_fail():
    al = Alignment(method="t", words=alignment().words[:5])
    with pytest.raises(ValueError, match="خارج الحدود"):
        required_seconds(OUT, segments(), al, 6.0)


def test_two_segments_starting_in_the_same_frame_fail():
    """نافذة بمدة صفر ما بتمرق — ولا تمديد صامت."""
    ws = list(alignment().words)
    t = ws[4].start
    for i in (5, 6, 7):
        ws[i] = ws[i].model_copy(update={"start": t,
                                         "end": max(ws[i].end, t + 0.1)})
    al = Alignment(method="t", words=tuple(ws))
    with pytest.raises(TimelineError):
        required_seconds(OUT, segments(), al, audio(al))


# ══ الوصلة للـResolver ══════════════════════════════════════════════
def _catalog(root, dur):
    body = b"CLIP"
    (root / "rain.mp4").write_bytes(body)
    import hashlib
    return Catalog(entries=(CatalogEntry(
        provider="local", provider_ref="cat_rain", path="rain.mp4",
        license="CC0", sha256=hashlib.sha256(body).hexdigest(),
        probe=Probe(width=3840, height=2160, fps=25.0, duration=dur),
        keywords=("rain", "night"), shot_type="macro", palette="charcoal"),))


def _intent(seg):
    return AssetIntent.model_validate_json(json.dumps({"intents": [
        {"segment_id": s.segment_id, "query": "rain at night",
         "shot_type": "macro", "palette": "charcoal"}
        for s in seg.segments]}))


def test_the_computed_duration_feeds_the_resolver(tmp_path):
    """المدة المحسوبة بتوصل لـ`in_point` فعلًا.

    **الأول بيتوسّط، واللي بعده بيكمّل** — التلاتة بهالـfixture بياخدوا
    نفس الأصل (كتالوج بصفّ واحد)، فالمتتاليان بيكمّلوا نافذة سابقهم
    بدل ما يتوسّطوا. القياس على السلسلة لا على صيغة التوسيط: نافذة كل
    مقطع بتساوي مدّته المطلوبة، ولا وحدة بتتجاوز الأصل.
    """
    al, seg = alignment(), segments()
    need = required_seconds(OUT, seg, al, audio(al))
    got = resolve_assets(_intent(seg), need, _catalog(tmp_path, 30.0), tmp_path)
    assert set(got) == {1, 2, 3}
    assert got[1].in_point == round((30.0 - need[1]) / 2, 3)   # الأول: توسيط
    for a, b in ((1, 2), (2, 3)):                              # الباقي: تتابع
        assert got[b].in_point == round(got[a].in_point + need[a], 3)
    for sid, a in got.items():
        assert a.in_point + need[sid] <= 30.0


def test_a_longer_window_moves_the_in_point(tmp_path):
    """**المدة هي اللي بتحرّك `in_point`، مش الترتيب.**

    الفحص فوق صار يقيس التتابع، فلو المدة انفصلت عن النافذة كليًّا
    بيضل أخضر. هون بنغيّر المدة المطلوبة وبنتأكّد إن الناتج بيتغيّر —
    وهاد الادّعاء اللي اسم الفحص السابق بيعد فيه.
    """
    al, seg = alignment(), segments()
    need = required_seconds(OUT, seg, al, audio(al))
    base = resolve_assets(_intent(seg), need, _catalog(tmp_path, 30.0),
                          tmp_path)
    wider = {k: v + 2.0 for k, v in need.items()}
    got = resolve_assets(_intent(seg), wider, _catalog(tmp_path, 30.0),
                         tmp_path)
    assert got[1].in_point != base[1].in_point


def test_an_asset_too_short_for_the_computed_window_fails(tmp_path):
    al, seg = alignment(), segments()
    need = required_seconds(OUT, seg, al, audio(al))
    short = max(need.values()) - 0.5
    with pytest.raises(AssetError, match="ولا تمديد صامت"):
        resolve_assets(_intent(seg), need, _catalog(tmp_path, short), tmp_path)


def test_positivity_is_guaranteed_by_quantize_not_by_a_local_check():
    """`required_seconds` بلا فحص إيجابية **بقصد**.

    `quantize` بترفض أي حدّ بصري غير متزايد، فالشرط المحلي كان ما
    بينوصل إله أبدًا — ومرقت الطفرة عليه، وهيك انكشف. حارس ما بينقدر
    ينفشل بيوهم بأمان مش موجودًا.
    """
    src = (ROOT / "ai_pipeline/window.py").read_text("utf-8")
    assert "need <= 0" not in src, "رجع حارس ميت"
    q = (ROOT / "ai_pipeline/timeline/quantize.py").read_text("utf-8")
    assert "حدّ بصري غير متزايد" in q, "السلطة على الإيجابية اختفت"
    al, seg = alignment(), segments()
    assert all(v > 0 for v in required_seconds(OUT, seg, al, audio(al)).values())

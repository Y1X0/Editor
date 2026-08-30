"""الراسم الإنتاجي — كل رقم بالأمر بيجي من عقد، وولا واحد بينخترع.

الفحوص هون بتسأل سؤالًا واحدًا بأشكال: **لو غيّرت العقد، بيتغيّر الأمر؟**
حقل بالعقد ما بيغيّر المخرَج هو إما ميت أو مفصول — نفس قاعدة
`test_config_wiring` بالمحرر، واللي انولدت من حادثة `motion.pan_px`.

والقائمة السالبة (ما بيحسب مدة · ما بينادي نموذجًا · ما بيعيد المحاولة)
مفحوصة كمان، لأنها جزء من عقد الموديول مش من توثيقه.
"""
import ast
import pathlib
import subprocess

import pytest

from ai_pipeline.errors import ContractError, FfmpegError
from ai_pipeline.models.assets import Asset, AssetsContract, Probe
from ai_pipeline.models.timeline import Span, Timeline
from ai_pipeline.models.typography import (
    StyleOverride, TypographyContract, TypographySegment,
)
from ai_pipeline.render import (
    MOTION, CaptionStyle, Encode, build_command, render,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
FONT = ROOT / "fonts" / "Amiri-Bold.ttf"


# ── عقود صغيرة ومباشرة ───────────────────────────────────────────────
@pytest.fixture
def timeline():
    """ثلاث مقاطع، و`asset_in_frame` **مختلفة عن الصفر ومختلفة عن بعضها**
    عشان أي خلط بينها وبين `in_point` ينكشف."""
    return Timeline(
        fps=30, sample_rate=48000, total_frames=300,
        visual_spans=(Span(segment_id=1, f_start=0, f_end=100),
                      Span(segment_id=2, f_start=100, f_end=190),
                      Span(segment_id=3, f_start=190, f_end=300)),
        text_spans=(Span(segment_id=1, f_start=10, f_end=90),
                    Span(segment_id=2, f_start=110, f_end=180),
                    Span(segment_id=3, f_start=200, f_end=290)),
        asset_in_frame={1: 45, 2: 90, 3: 150})


@pytest.fixture
def rassets(tmp_path):
    out = []
    for sid in (1, 2, 3):
        p = tmp_path / f"clip{sid}.mp4"
        p.write_bytes(b"\0")
        out.append(Asset(
            segment_id=sid, source_type="generated", provider="fixture",
            provider_ref=f"f{sid}", file_path=p, sha256="b" * 64,
            license="CC0",
            probe=Probe(width=1920, height=1080, fps=30.0, duration=30.0),
            # **`in_point` مضبوط على قيمة تانية عن `asset_in_frame`
            # بقصد**: لو الراسم قرأ منه بدل الـtimeline بينكشف فورًا.
            in_point=7.0, fit="cover", motion="none"))
    return AssetsContract(assets=tuple(out))


@pytest.fixture
def typo():
    return TypographyContract(
        theme="nur-dark",
        segments=tuple(TypographySegment(segment_id=i, animation="fade")
                       for i in (1, 2, 3)),
        overrides={i: StyleOverride(font_size=64, text_color="#FFFFFF",
                                    max_lines=2) for i in (1, 2, 3)})


def cmd_of(timeline, rassets, output, **kw):
    return build_command(timeline, rassets, output, "voice.wav",
                         "seq/%06d.png", "out.mp4", y_ratio=0.64, **kw)


def graph_of(cmd):
    return cmd[cmd.index("-filter_complex") + 1]


# ── الترتيب والفهرسة ─────────────────────────────────────────────────
def test_inputs_follow_the_visual_span_order(timeline, rassets, output):
    """فهارس الفلاتر مبنية على ترتيب المدخلات — فالترتيب جزء من العقد."""
    cmd = cmd_of(timeline, rassets, output)
    paths = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-i"]
    want = [str(rassets.by_segment(s.segment_id).file_path)
            for s in timeline.visual_spans]
    assert paths[:3] == want
    assert paths[3] == "seq/%06d.png" and paths[4] == "voice.wav"


def test_the_seek_comes_from_the_timeline_not_the_asset(timeline, rassets,
                                                        output):
    """`-ss` = `asset_in_frame / fps`، مش `asset.in_point`.

    الاتنان بيتّفقوا لما `quantize` تبنيهن سوا، بس السلطة على اللي
    بينرمّز هي الـtimeline. الـfixture حاطّة `in_point=7.0` لكل أصل
    وفهارس مختلفة (45·90·150)، فالخلط ما بيقدر يمرق بالصدفة.
    """
    cmd = cmd_of(timeline, rassets, output)
    seeks = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-ss"]
    assert seeks == ["1.500000", "3.000000", "5.000000"]     # 45/30 · 90/30 · 150/30
    assert "7.000000" not in seeks


def test_a_span_without_an_in_frame_fails_closed(timeline, rassets, output):
    """غياب الفهرس **فشل**، مش بداية من الإطار صفر.

    `Timeline.asset_in_frame` ما بيلزم يغطّي كل مقطع بالـschema، فالراسم
    هو اللي لازم يرفض — والافتراضي الصامت بيعطي لقطة من مكان غلط بلا
    ولا رسالة.
    """
    broken = timeline.model_copy(update={"asset_in_frame": {1: 45, 2: 90}})
    with pytest.raises(ContractError, match="asset_in_frame"):
        cmd_of(broken, rassets, output)


def test_a_span_without_an_asset_fails_closed(timeline, rassets, output):
    thin = AssetsContract(assets=tuple(a for a in rassets.assets
                                       if a.segment_id != 2))
    with pytest.raises(ContractError, match="بلا أصل"):
        cmd_of(timeline, thin, output)


# ── الأرقام: كلها من العقد ───────────────────────────────────────────
def test_every_number_in_the_command_comes_from_a_contract(timeline, rassets,
                                                           output):
    cmd = cmd_of(timeline, rassets, output)
    g = graph_of(cmd)
    # الطول: عدد الإطارات من الـtimeline، وعدد العيّنات مشتقّ منه
    assert cmd[cmd.index("-frames:v") + 1] == "300"
    assert f"atrim=end_sample={timeline.total_samples}" in g
    assert timeline.total_samples == 300 * (48000 // 30)
    # حدّ كل مقطع = عدد إطاراته، بالفهرس مش بالثواني
    for k, sp in enumerate(timeline.visual_spans):
        assert f"trim=start_frame=0:end_frame={sp.n_frames}" in g
    # الأبعاد والمعدلات من `Output`
    assert f"fps={output.fps}" in g and f"aresample={output.sample_rate}" in g
    assert f"crop={output.width}:{output.height}" in g


def test_the_frame_rate_is_normalised_before_any_trim(timeline, rassets,
                                                      output):
    """`fps=` **قبل** `trim` — وإلا الفهرس بينحسب على معدل المصدر.

    الأصل 25fps والمخرَج 30: نفس فخّ `graph.video_stem` بالمحرر.
    """
    for chain in graph_of(cmd_of(timeline, rassets, output)).split(";"):
        if "trim=" in chain and "atrim" not in chain:
            assert chain.index("fps=") < chain.index("trim=")


def test_the_sample_rate_is_normalised_before_the_audio_trim(timeline, rassets,
                                                             output):
    chain = [c for c in graph_of(cmd_of(timeline, rassets, output)).split(";")
             if "atrim" in c][0]
    assert chain.index("aresample=") < chain.index("atrim=")


def test_sar_is_pinned_after_the_crop(timeline, rassets, output):
    """`setsar=1` بعد القصّ — حادثة `SAR 10240:10239` الموثَّقة."""
    for chain in graph_of(cmd_of(timeline, rassets, output)).split(";"):
        if "crop=" in chain:
            assert chain.index("crop=") < chain.index("setsar=1")


# ── كل حقل بالعقد لازم يغيّر الأمر ───────────────────────────────────
@pytest.mark.parametrize("motion", sorted(MOTION))
def test_every_motion_value_changes_the_command(timeline, rassets, output,
                                                motion):
    """ولا قيمة `motion` بتنسقط بصمت.

    الفحص على **الجدول** مش على قائمة مكتوبة بالاختبار: قيمة جديدة
    بـ`MOTION` بتنضم تلقائيًا، وقيمة بلا أثر بتفشل هون.
    """
    base = cmd_of(timeline, rassets, output)
    swapped = AssetsContract(assets=tuple(
        a.model_copy(update={"motion": motion}) for a in rassets.assets))
    got = cmd_of(timeline, swapped, output)
    if motion == "none":
        assert got == base
    else:
        assert got != base, f"motion={motion!r} ما غيّر الأمر — حقل ميت"


def test_pan_left_and_pan_right_frame_differently(timeline, rassets, output):
    """الاتنان بيكبّروا نفس المقدار، فلو المرساة انسقطت بيتطابقوا."""
    def with_motion(m):
        return cmd_of(timeline, AssetsContract(assets=tuple(
            a.model_copy(update={"motion": m}) for a in rassets.assets)), output)
    assert with_motion("pan_left") != with_motion("pan_right")


def test_fit_changes_the_geometry(timeline, rassets, output):
    """`cover` بتقصّ و`contain` بتبطّن — والاتنان بالعقد."""
    cover = graph_of(cmd_of(timeline, rassets, output))
    contain = graph_of(cmd_of(timeline, AssetsContract(assets=tuple(
        a.model_copy(update={"fit": "contain"}) for a in rassets.assets)),
        output))
    assert "crop=" in cover and "increase" in cover
    assert "pad=" in contain and "decrease" in contain
    assert cover != contain


def test_the_encoder_settings_reach_the_command(timeline, rassets, output):
    base = cmd_of(timeline, rassets, output)
    other = cmd_of(timeline, rassets, output,
                   encode=Encode(preset="veryfast", crf=28))
    assert "medium" in base and "veryfast" in other and "28" in other


def test_the_caption_height_reaches_the_overlay(timeline, rassets, output):
    a = build_command(timeline, rassets, output, "a.wav", "s/%06d.png", "o.mp4",
                      y_ratio=0.64)
    b = build_command(timeline, rassets, output, "a.wav", "s/%06d.png", "o.mp4",
                      y_ratio=0.80)
    assert "0.64" in graph_of(a) and "0.8" in graph_of(b)


# ── القائمة السالبة: جزء من العقد ────────────────────────────────────
def _module_imports() -> set[str]:
    src = (ROOT / "ai_pipeline" / "render.py").read_text(encoding="utf-8")
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


@pytest.mark.parametrize("banned", [
    "anthropic",                      # ولا نموذج
    "ai_pipeline.agents",             # ولا وكيل ولا resolver
    ".agents",
    "shared.probe",                   # ولا قراءة مدة
])
def test_the_renderer_imports_nothing_it_is_forbidden_to_use(banned):
    """القائمة السالبة بـ`ast`، مش بالنص: تعليق فيه الاسم مش استيرادًا."""
    hits = {n for n in _module_imports()
            if n == banned or n.startswith(banned + ".")}
    assert not hits, f"`render.py` بتستورد {sorted(hits)} — ممنوع بالعقد"


def test_the_renderer_never_measures_a_duration(timeline, rassets, output,
                                               monkeypatch):
    """ولا نداء عملية فرعية أثناء بناء الأمر.

    الفرضية اللي القرار قايم عليها: المدة انقيست عند نقطة الدخول.
    فلو الراسم عمل `probe` هون، بيصير في قارئان للمدة — وهاد بالضبط
    اللي Commit 11 حطّ عليه حارسًا.
    """
    import ai_pipeline.render as R

    def boom(*a, **k):                                  # pragma: no cover
        raise AssertionError("الراسم شغّل عملية فرعية أثناء بناء الأمر")

    # `monkeypatch` مش إسنادًا يدويًا: `R.subprocess` **هو** الموديول
    # العام، فالإسناد بيتسرّب لباقي الطقم لو الفحص فشل قبل الإرجاع.
    monkeypatch.setattr(R.subprocess, "run", boom)
    cmd = cmd_of(timeline, rassets, output)
    assert "voice.wav" in cmd


def test_a_failing_ffmpeg_is_not_retried(timeline, rassets, typo, output,
                                         segments, tmp_path, monkeypatch):
    """**ولا إعادة محاولة.** نداء واحد بالضبط، وبعده `FfmpegError`."""
    import ai_pipeline.render as R
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "boom: bad input")

    monkeypatch.setattr(R.subprocess, "run", fake)
    tl = timeline.model_copy(update={
        "text_spans": (Span(segment_id=1, f_start=10, f_end=90),)})
    with pytest.raises(FfmpegError, match="boom"):
        render(tl, segments, rassets, typo, output, audio="a.wav",
               out_path=tmp_path / "o.mp4", workdir=tmp_path / "w",
               style=CaptionStyle(font=FONT))
    assert len(calls) == 1, f"ffmpeg انندى {len(calls)} مرات — القائمة السالبة"


def test_rendering_does_not_mutate_the_timeline(timeline, rassets, output):
    before = timeline.model_dump_json()
    cmd_of(timeline, rassets, output)
    assert timeline.model_dump_json() == before


# ── الكابشن: العقد بيوصل للصورة ──────────────────────────────────────
@pytest.mark.ffmpeg
def test_the_caption_sequence_has_one_file_per_frame(timeline, segments, typo,
                                                     output, tmp_path):
    """فهرس ناقص بيوقّف التسلسل عنده — مقيس بهالمستودع (١٢ إطار -> ٥)."""
    from ai_pipeline.render import rasterise_captions
    tl = timeline.model_copy(update={"total_frames": 60, "fps": 30,
        "visual_spans": (Span(segment_id=1, f_start=0, f_end=60),),
        "text_spans": (Span(segment_id=1, f_start=10, f_end=40),),
        "asset_in_frame": {1: 0}})
    pattern = rasterise_captions(tl, segments, typo, output,
                                 CaptionStyle(font=FONT), tmp_path)
    seq = pathlib.Path(pattern).parent
    assert sorted(p.name for p in seq.glob("*.png")) == \
        [f"{n:06d}.png" for n in range(60)]


@pytest.mark.ffmpeg
def test_every_sequence_image_has_the_same_size(timeline, segments, typo,
                                                output, tmp_path):
    """فرق بكسل واحد بيقطع المخرَج بصمت: ٤٠٧×٢٠٨ و٤٠٨×٢٠٨ -> ٧٣/١٤٤.

    الـfixture فيها نصوص بأطوال مختلفة، فالتبطين هو اللي بيوحّدهن.
    """
    from PIL import Image

    from ai_pipeline.render import rasterise_captions
    pattern = rasterise_captions(timeline, segments, typo, output,
                                 CaptionStyle(font=FONT), tmp_path)
    seq = pathlib.Path(pattern).parent
    sizes = {Image.open(p).size for p in seq.glob("*.png")}
    assert len(sizes) == 1, f"مقاسات مختلفة بالتسلسل: {sizes}"


def test_a_segment_without_typography_fails_closed(timeline, segments, output,
                                                   tmp_path):
    from ai_pipeline.render import rasterise_captions
    thin = TypographyContract(
        theme="nur-dark",
        segments=tuple(TypographySegment(segment_id=i) for i in (1, 2, 3)),
        overrides={1: StyleOverride(font_size=64, text_color="#FFFFFF")})
    with pytest.raises(ContractError, match="حجم/لون"):
        rasterise_captions(timeline, segments, thin, output,
                           CaptionStyle(font=FONT), tmp_path)


# ── على ناتج ffmpeg نفسه ─────────────────────────────────────────────
@pytest.fixture
def tiny(tmp_path):
    """ثلاث لقطات + صوت، صغار بقصد: الفحص عن **الصحّة** مش عن الجودة."""
    from shared.ffmpeg import exe
    clips = []
    for i, src in enumerate(("gradients=s=320x240:c0=0x102040:c1=0x4080C0:r=10",
                             "color=c=0x203020:s=320x240:r=10,noise=alls=20:allf=t",
                             "gradients=s=320x240:c0=0x402010:c1=0xC08040:r=10")):
        p = tmp_path / f"c{i}.mp4"
        subprocess.run([exe(), "-v", "error", "-f", "lavfi", "-i", src,
                        "-frames:v", "60", "-r", "10", "-pix_fmt", "yuv420p",
                        "-c:v", "libx264", "-preset", "ultrafast", "-an",
                        "-y", str(p)], check=True)
        clips.append(p)
    wav = tmp_path / "voice.wav"
    subprocess.run([exe(), "-v", "error", "-f", "lavfi",
                    "-i", "sine=f=220:r=48000", "-af", "atrim=end_sample=144000",
                    "-ac", "1", "-c:a", "pcm_s16le", "-y", str(wav)], check=True)
    return clips, wav


@pytest.fixture
def tiny_contracts(tiny, segments):
    from ai_pipeline.models.project import Output
    clips, wav = tiny
    out = Output(width=216, height=384, fps=10, sample_rate=48000)
    tl = Timeline(
        fps=10, sample_rate=48000, total_frames=30,
        visual_spans=(Span(segment_id=1, f_start=0, f_end=10),
                      Span(segment_id=2, f_start=10, f_end=20),
                      Span(segment_id=3, f_start=20, f_end=30)),
        text_spans=(Span(segment_id=1, f_start=2, f_end=9),
                    Span(segment_id=2, f_start=12, f_end=19),
                    Span(segment_id=3, f_start=22, f_end=29)),
        asset_in_frame={1: 0, 2: 10, 3: 20})
    motions = ("zoom_in", "none", "pan_left")
    assets = AssetsContract(assets=tuple(
        Asset(segment_id=i + 1, source_type="generated", provider="lavfi",
              provider_ref=f"c{i}", file_path=clips[i], sha256="c" * 64,
              license="CC0",
              probe=Probe(width=320, height=240, fps=10.0, duration=6.0),
              in_point=0.0, fit="cover", motion=motions[i])
        for i in range(3)))
    typo = TypographyContract(
        theme="nur-dark",
        segments=tuple(TypographySegment(segment_id=i) for i in (1, 2, 3)),
        overrides={i: StyleOverride(font_size=22, text_color="#FFFFFF",
                                    max_lines=2) for i in (1, 2, 3)})
    return tl, assets, typo, out, wav


@pytest.mark.ffmpeg
def test_the_rendered_file_matches_the_timeline(tiny_contracts, segments,
                                                tmp_path):
    """**`exit code 0` مش إثباتًا** — القياس هو عدّ اللي طلع فعلًا.

    نفس حارس المخرَج تبع Phase 2، على ملف رسمه هالموديول: عدد الإطارات
    وعدد العيّنات والدقّة و`SAR` والوسوم.
    """
    from ai_pipeline.qa.output import verify_output
    tl, assets, typo, out, wav = tiny_contracts
    dst = tmp_path / "out.mp4"
    render(tl, segments, assets, typo, out, audio=wav, out_path=dst,
           workdir=tmp_path / "w", style=CaptionStyle(font=FONT))
    pr = verify_output(dst, tl, out)
    assert pr.frames == tl.total_frames == 30
    assert (pr.width, pr.height) == (216, 384)


@pytest.mark.ffmpeg
def test_two_runs_of_the_same_contracts_give_the_same_bytes(tiny_contracts,
                                                            segments, tmp_path):
    """حتمية على مستوى البايت — ولا ساعة ولا عشوائية بالمسار.

    بلاها ما بتقدر تقول «نفس العقود = نفس الفيديو»، وهاد أساس أي مقارنة
    بين تشغيلتين.
    """
    import hashlib
    tl, assets, typo, out, wav = tiny_contracts
    digests = []
    for run in ("a", "b"):
        dst = tmp_path / f"{run}.mp4"
        render(tl, segments, assets, typo, out, audio=wav, out_path=dst,
               workdir=tmp_path / f"w{run}", style=CaptionStyle(font=FONT))
        digests.append(hashlib.sha256(dst.read_bytes()).hexdigest())
    assert digests[0] == digests[1]


@pytest.mark.ffmpeg
def test_dry_run_writes_the_captions_but_encodes_nothing(tiny_contracts,
                                                         segments, tmp_path):
    """`dry_run` بيوقف قبل ffmpeg **وبعد** رسم الكابشن.

    فالمطبوع هو الأمر الحقيقي مش تقريبًا إله — نفس قرار
    `autoreel.render`، وهو اللي بيخلي الشكل قابلًا للفحص بلا ترميز.
    """
    tl, assets, typo, out, wav = tiny_contracts
    dst = tmp_path / "never.mp4"
    cmd = render(tl, segments, assets, typo, out, audio=wav, out_path=dst,
                 workdir=tmp_path / "w", style=CaptionStyle(font=FONT),
                 dry_run=True)
    assert not dst.exists()
    seq = tmp_path / "w" / "seq"
    assert len(list(seq.glob("*.png"))) == tl.total_frames
    assert cmd[-1] == str(dst) and "-filter_complex" in cmd

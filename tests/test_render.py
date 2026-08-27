"""
طبقة الفيديو عبر `--dry-run`.

هاي أول تغطية آلية لـ`render.py`. الفكرة إن `dry_run` بيوقف نداء ffmpeg
بس — خطة القص وسلسلة الفلاتر وأسماء الملفات كلها بتنحسب عادي — فاللي
بينطبع هو الأمر الحقيقي، وفحصه فحص للطبقة نفسها مش لبديل وهمي عنها.
"""
import json
import re
import shlex

import pytest

from autoreel import render as R
from conftest import ROOT


def cmds(capsys):
    """
    أوامر ffmpeg المطبوعة، كل واحدة مقسّمة لوسائطها.
    نادِها مرة وحدة لكل تشغيل — `readouterr` بتفضّي المخزَن.
    """
    out = capsys.readouterr().out
    return [shlex.split(ln[2:]) for ln in out.splitlines() if ln.startswith("$ ")]


def arg(cmd, flag):
    """قيمة العلم من أمر ffmpeg."""
    return cmd[cmd.index(flag) + 1]


def fake_caps(n, tmp_path):
    d = tmp_path / "caps"
    d.mkdir(exist_ok=True)
    out = []
    for i in range(n):
        p = d / f"c{i:04d}.png"
        p.write_bytes(b"x")
        out.append((str(p), i * 0.5, i * 0.5 + 0.4))
    return out


@pytest.fixture
def full_cfg():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _no_probe(monkeypatch):
    """
    `build_video` بتقرا أبعاد المصدر (لازمة لحساب مرساة القصّ). هون
    مصدر وهمي، فبنثبّت الأبعاد ونضل بلا ffmpeg — نفس فلسفة `--dry-run`.
    """
    monkeypatch.setattr(R, "probe_source", lambda p: (640, 1138, True))


# --------------------------------------------------------------- الأساسيات

def test_preview_round_trips_through_the_shell():
    """الأمر المطبوع لازم يرجع لنفس الوسائط بالضبط لو نسخته للترمنال."""
    cmd = ["ffmpeg", "-vf", "crop=1:2:3:4,scale=5:6", "ملف فيه فراغ.mp4"]
    assert shlex.split(R.preview(cmd)) == cmd


def test_dry_run_produces_no_video(tmp_path, full_cfg, capsys):
    R.build_base("in.mp4", [(0.0, 2.0), (3.0, 4.0)], full_cfg, str(tmp_path),
                 dry_run=True)
    assert not list(tmp_path.glob("*.mp4"))


def test_dry_run_returns_the_path_it_would_have_written(tmp_path, full_cfg, capsys):
    base = R.build_base("in.mp4", [(0.0, 2.0)], full_cfg, str(tmp_path), dry_run=True)
    assert base == str(tmp_path / "base.mp4")


def test_dry_run_does_not_touch_the_real_ffmpeg(tmp_path, full_cfg, monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("subprocess.run انندهت مع dry_run")
    monkeypatch.setattr(R.subprocess, "run", boom)
    R.build_base("in.mp4", [(0.0, 1.0)], full_cfg, str(tmp_path), dry_run=True)
    R.burn_captions("b.mp4", fake_caps(3, tmp_path), full_cfg,
                    str(tmp_path / "o.mp4"), workdir=str(tmp_path), dry_run=True)


# -------------------------------------------------------- build_base

def graph_of(tmp_path):
    """الرسم اللي انكتب للملف — `-filter_complex_script` ما بيطبعه بالأمر."""
    return (tmp_path / "graph.txt").read_text(encoding="utf-8")


def test_video_is_one_ffmpeg_pass_whatever_the_segment_count(tmp_path, full_cfg,
                                                             capsys):
    """
    المقطع الواحد والعشرة بينرمّزوا بتشغيلة وحدة. قبل هيك كان ترميز لكل
    مقطع ثم `concat` — وهو مصدر CR-5 (أول إطار بكل مقطع بينكرّر).
    """
    for n in (1, 3, 10):
        R.build_base("in.mp4", [(i, i + 0.5) for i in range(n)], full_cfg,
                      str(tmp_path), dry_run=True)
        assert len(cmds(capsys)) == 1


def test_video_pass_never_seeks_by_time(tmp_path, full_cfg, capsys):
    """
    **حارس CR-5.** `-ss` بزمن برّا شبكة الإطارات بتخلّي ffmpeg يكرّر أول
    إطار ليعبّي `t=0`. القصّ صار بفهرس الإطار، فما بيصير يرجع `-ss`
    ولا `-to` ولا `-t` لهالتشغيلة.
    """
    R.build_base("in.mp4", [(1.25, 3.5), (9.0, 10.0)], full_cfg,
                  str(tmp_path), dry_run=True)
    c = cmds(capsys)[0]
    for flag in ("-ss", "-to", "-t", "-frames:v"):
        assert flag not in c, f"{flag} رجعت لمسار الفيديو"


def test_select_ranges_are_frame_indices_from_the_plan(tmp_path, full_cfg,
                                                       capsys):
    """كل مدى `between(n,s,e)` لازم يعطي `frame_plan[i]` إطار بالضبط."""
    from autoreel.cuts import frame_plan
    from autoreel.graph import start_frames
    segs = [(0.0, 1.0), (2.0, 3.37), (5.0, 6.123)]
    fps = full_cfg["output"]["fps"]
    R.build_base("in.mp4", segs, full_cfg, str(tmp_path), dry_run=True)
    got = [(int(a), int(b)) for a, b in
           re.findall(r"between\(n,(\d+),(\d+)\)", graph_of(tmp_path))]
    assert [b - a + 1 for a, b in got] == frame_plan(segs, fps)
    assert [a for a, _ in got] == start_frames(segs, fps)


def test_stem_orders_the_filters_the_only_way_that_works(tmp_path, full_cfg,
                                                         capsys):
    """
    ترتيب الجذع مش تجميليًا. كل خطوة ثمن لغم مقاس:
    `fps` قبل `select` (فهرس شبكة مش فهرس فكّ)، `settb`+`setpts=N`
    (بلا عائمة)، و`fps` بعد `setpts` (اللي بتمسح معدّل الإطارات).
    """
    fps = full_cfg["output"]["fps"]
    R.build_base("in.mp4", [(0.0, 1.0)], full_cfg, str(tmp_path), dry_run=True)
    g = graph_of(tmp_path)
    assert g.index(f"fps={fps},select") < g.index("settb=")
    assert g.index("settb=") < g.index("setpts=N,")
    assert g.index("setpts=N,") < g.index(f"setpts=N,fps={fps}") + 1
    assert "/TB" not in g


def test_graph_goes_through_a_script_file_not_the_command_line(tmp_path,
                                                               full_cfg, capsys):
    """٣٠٠ مقطع = عشرات الكيلوبايتات، وحدود سطر الأوامر على أندرويد أضيق."""
    R.build_base("in.mp4", [(0.0, 1.0)], full_cfg, str(tmp_path), dry_run=True)
    c = cmds(capsys)[0]
    assert "-filter_complex_script" in c
    assert "-filter_complex" not in c
    assert arg(c, "-filter_complex_script") == str(tmp_path / "graph.txt")


def test_crop_matches_configured_output_size(tmp_path, full_cfg, capsys):
    W = full_cfg["output"]["width"]; H = full_cfg["output"]["height"]
    R.build_base("in.mp4", [(0.0, 1.0)], full_cfg, str(tmp_path), dry_run=True)
    assert f"crop={W}:{H}:" in graph_of(tmp_path)


def test_zoom_cycles_across_segments(tmp_path, full_cfg, capsys):
    """كل مقطع بياخد زوم من الدورة بالترتيب — هاد شكل الريلز المقصود."""
    cycle = full_cfg["motion"]["zoom_cycle"]
    segs = [(i, i + 0.5) for i in range(len(cycle) + 1)]
    R.build_base("in.mp4", segs, full_cfg, str(tmp_path), dry_run=True)
    g = graph_of(tmp_path)
    w = re.search(r"scale=w='([^']+)'", g).group(1)
    vals = [int(v) for v in re.findall(r"(\d+)\*between", w)]
    assert len(vals) == len(segs)
    assert vals[0] == vals[len(cycle)]              # الدورة بتلف
    assert len(set(vals)) == len(set(cycle))


def test_motion_disabled_gives_every_segment_the_same_zoom(tmp_path, full_cfg,
                                                           capsys):
    full_cfg["motion"]["enabled"] = False
    R.build_base("in.mp4", [(i, i + 0.5) for i in range(4)], full_cfg,
                  str(tmp_path), dry_run=True)
    w = re.search(r"scale=w='([^']+)'", graph_of(tmp_path)).group(1)
    assert len({int(v) for v in re.findall(r"(\d+)\*between", w)}) == 1


def test_zoom_is_evaluated_per_frame(tmp_path, full_cfg, capsys):
    """بدون `eval=frame` الزوم بينتقيّم مرة وحدة وبيثبت على أول مقطع."""
    R.build_base("in.mp4", [(0, 1), (2, 3)], full_cfg, str(tmp_path),
                  dry_run=True)
    assert "eval=frame" in graph_of(tmp_path)


def test_overlapping_segments_raise_instead_of_losing_frames(tmp_path, full_cfg):
    """
    `select` بتمرّر إطار المصدر مرة وحدة، فالتداخل بيقصّر المخرَج بصمت.
    """
    with pytest.raises(ValueError, match="متداخلة"):
        R.build_base("in.mp4", [(0.0, 2.0), (1.0, 3.0)], full_cfg,
                      str(tmp_path), dry_run=True)


# ------------------------------------------------------------- build_base

def test_audio_is_cut_in_the_same_single_pass(tmp_path, full_cfg, capsys):
    """
    صورة وصوت بتشغيلة وحدة. قبل المرحلة ٦ كان الصوت ترميز AAC لكل مقطع
    ثم `concat -c copy`، والـpriming بيتراكم — ١٥٢ms عند ٨ مقاطع.
    """
    segs = [(0.0, 1.0), (2.0, 3.0), (5.0, 6.5)]
    R.build_base("in.mp4", segs, full_cfg, str(tmp_path), dry_run=True)
    c = cmds(capsys)
    assert len(c) == 1, f"توقّعنا تشغيلة وحدة، طلعوا {len(c)}"
    g = graph_of(tmp_path)
    assert g.count("atrim=") == len(segs)
    assert "concat=n=3:v=0:a=1" in g


def test_audio_boundaries_come_from_the_same_frame_plan(tmp_path, full_cfg,
                                                        capsys):
    """
    حدود الصوت مشتقّة من نفس خطة الإطارات اللي بيقصّ عليها الفيديو —
    وإلا رجع الانزياح من الباب الخلفي.
    """
    from autoreel.cuts import frame_plan
    from autoreel.graph import start_frames, DEFAULT_SR
    segs = [(0.0, 1.0), (2.0, 3.37)]
    fps = full_cfg["output"]["fps"]
    R.build_base("in.mp4", segs, full_cfg, str(tmp_path), dry_run=True)
    spf = DEFAULT_SR // fps
    pairs = [(int(a), int(b)) for a, b in re.findall(
        r"atrim=start_sample=(\d+):end_sample=(\d+)", graph_of(tmp_path))]
    for (a, b), s, n in zip(pairs, start_frames(segs, fps), frame_plan(segs, fps)):
        assert (a, b) == (s * spf, (s + n) * spf)


def test_audio_is_encoded_once_at_the_output(tmp_path, full_cfg, capsys):
    R.build_base("in.mp4", [(0.0, 1.0)], full_cfg, str(tmp_path), dry_run=True)
    c = cmds(capsys)[0]
    assert arg(c, "-c:a") == "aac"
    assert graph_of(tmp_path).count("aac") == 0, "ترميز جوا الرسم"


def test_a_silent_source_produces_no_audio_chain(tmp_path, full_cfg, capsys,
                                                 monkeypatch):
    """
    `[0:a]` بتفشّل التشغيلة على مصدر بلا صوت، فلازم ينشال المسار كله.
    """
    monkeypatch.setattr(R, "probe_source", lambda p: (640, 1138, False))
    R.build_base("in.mp4", [(0.0, 1.0)], full_cfg, str(tmp_path), dry_run=True)
    assert "[0:a]" not in graph_of(tmp_path)
    assert "-c:a" not in cmds(capsys)[0]


def test_no_intermediate_segment_files_are_written(tmp_path, full_cfg, capsys):
    """سقالة المرحلة ٥ انشالت: ولا `seg*.mp4` ولا `concat.txt`."""
    R.build_base("in.mp4", [(0.0, 1.0), (2.0, 3.0)], full_cfg, str(tmp_path),
                 dry_run=True)
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["graph.txt"], f"ملفات وسيطة: {left}"


# ---------------------------------------------------------- burn_captions

def test_no_captions_is_a_single_stream_copy(tmp_path, full_cfg, capsys):
    R.burn_captions("base.mp4", [], full_cfg, str(tmp_path / "o.mp4"),
                    workdir=str(tmp_path), dry_run=True)
    c = cmds(capsys)
    assert len(c) == 1 and arg(c[0], "-c") == "copy"


@pytest.mark.parametrize("n,passes", [(1, 1), (60, 1), (61, 2), (150, 3)])
def test_one_pass_per_batch(tmp_path, full_cfg, capsys, n, passes):
    R.burn_captions("base.mp4", fake_caps(n, tmp_path), full_cfg,
                    str(tmp_path / "o.mp4"), workdir=str(tmp_path), dry_run=True)
    assert len(cmds(capsys)) == passes


def test_passes_chain_and_only_the_last_writes_the_output(tmp_path, full_cfg, capsys):
    out = str(tmp_path / "o.mp4")
    R.burn_captions("base.mp4", fake_caps(150, tmp_path), full_cfg, out,
                    workdir=str(tmp_path), dry_run=True)
    c = cmds(capsys)
    assert [x[-1] for x in c][-1] == out
    for prev, nxt in zip(c, c[1:]):
        assert arg(nxt, "-i") == prev[-1]          # كل تمريرة بتقرا اللي قبلها


def test_intermediate_passes_live_in_the_workdir(tmp_path, full_cfg, capsys):
    outdir = tmp_path / "out"; outdir.mkdir()
    work = tmp_path / "work"; work.mkdir()
    R.burn_captions("base.mp4", fake_caps(150, tmp_path), full_cfg,
                    str(outdir / "o.mp4"), workdir=str(work), dry_run=True)
    inter = [x[-1] for x in cmds(capsys)][:-1]
    assert inter and all(p.startswith(str(work)) for p in inter)


def test_overlay_carries_the_caption_window(tmp_path, full_cfg, capsys):
    caps = [(str(tmp_path / "a.png"), 1.5, 2.25)]
    R.burn_captions("base.mp4", caps, full_cfg, str(tmp_path / "o.mp4"),
                    workdir=str(tmp_path), dry_run=True)
    fc = arg(cmds(capsys)[0], "-filter_complex")
    assert "between(t,1.500,2.250)" in fc


def test_overlay_y_follows_y_ratio(tmp_path, full_cfg, capsys):
    y = int(full_cfg["output"]["height"] * full_cfg["captions"]["y_ratio"])
    R.burn_captions("base.mp4", fake_caps(2, tmp_path), full_cfg,
                    str(tmp_path / "o.mp4"), workdir=str(tmp_path), dry_run=True)
    assert f"y={y}-h/2" in arg(cmds(capsys)[0], "-filter_complex")


def test_every_caption_png_is_an_input(tmp_path, full_cfg, capsys):
    caps = fake_caps(5, tmp_path)
    R.burn_captions("base.mp4", caps, full_cfg, str(tmp_path / "o.mp4"),
                    workdir=str(tmp_path), dry_run=True)
    c = cmds(capsys)[0]
    for p, _, _ in caps:
        assert p in c


def test_overlay_chain_is_wired_head_to_tail(tmp_path, full_cfg, capsys):
    """كل overlay بياخد مخرَج اللي قبله — سلسلة مكسورة = كابشن مفقود."""
    R.burn_captions("base.mp4", fake_caps(4, tmp_path), full_cfg,
                    str(tmp_path / "o.mp4"), workdir=str(tmp_path), dry_run=True)
    c = cmds(capsys)[0]
    steps = arg(c, "-filter_complex").split(";")
    assert steps[0].startswith("[0:v][1:v]")
    for k, step in enumerate(steps[1:], start=2):
        assert step.startswith(f"[v{k-1}][{k}:v]")
    assert arg(c, "-map") == f"[v{len(steps)}]"

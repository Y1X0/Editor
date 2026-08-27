"""
طبقة الفيديو عبر `--dry-run`.

هاي أول تغطية آلية لـ`render.py`. الفكرة إن `dry_run` بيوقف نداء ffmpeg
بس — خطة القص وسلسلة الفلاتر وأسماء الملفات كلها بتنحسب عادي — فاللي
بينطبع هو الأمر الحقيقي، وفحصه فحص للطبقة نفسها مش لبديل وهمي عنها.
"""
import json
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


# ------------------------------------------------------------- build_base

def test_one_encode_per_segment_plus_one_concat(tmp_path, full_cfg, capsys):
    segs = [(0.0, 1.0), (2.0, 3.0), (5.0, 6.5)]
    R.build_base("in.mp4", segs, full_cfg, str(tmp_path), dry_run=True)
    c = cmds(capsys)
    assert len(c) == len(segs) + 1
    assert arg(c[-1], "-f") == "concat"


def test_segment_start_reaches_ffmpeg(tmp_path, full_cfg, capsys):
    R.build_base("in.mp4", [(1.25, 3.5)], full_cfg, str(tmp_path), dry_run=True)
    assert arg(cmds(capsys)[0], "-ss") == "1.250"


def test_segment_length_is_a_frame_count_not_a_time(tmp_path, full_cfg, capsys):
    """
    الانحدار (CR-1): `-to` بيخلي ffmpeg يقرّر عدد الإطارات، والمقاس
    طلع +112ms على ٥ مقاطع. `-frames:v` بينقل القرار لعنا.
    """
    fps = full_cfg["output"]["fps"]
    R.build_base("in.mp4", [(1.25, 3.5)], full_cfg, str(tmp_path), dry_run=True)
    c = cmds(capsys)[0]
    assert "-to" not in c, "لسا بيعتمد على الزمن"
    assert arg(c, "-frames:v") == str(round((3.5 - 1.25) * fps))


def test_frame_counts_match_the_plan(tmp_path, full_cfg, capsys):
    from autoreel.cuts import frame_plan
    segs = [(0.0, 1.0), (2.0, 3.37), (5.0, 6.123)]
    fps = full_cfg["output"]["fps"]
    R.build_base("in.mp4", segs, full_cfg, str(tmp_path), dry_run=True)
    got = [int(arg(c, "-frames:v")) for c in cmds(capsys) if "-frames:v" in c]
    assert got == frame_plan(segs, fps)


def test_crop_matches_configured_output_size(tmp_path, full_cfg, capsys):
    W = full_cfg["output"]["width"]; H = full_cfg["output"]["height"]
    R.build_base("in.mp4", [(0.0, 1.0)], full_cfg, str(tmp_path), dry_run=True)
    vf = arg(cmds(capsys)[0], "-vf")
    assert f"crop={W}:{H}:" in vf
    assert f"fps={full_cfg['output']['fps']}" in vf


def test_zoom_cycles_across_segments(tmp_path, full_cfg, capsys):
    """كل مقطع بياخد زوم من الدورة بالترتيب — هاد شكل الريلز المقصود."""
    cycle = full_cfg["motion"]["zoom_cycle"]
    segs = [(i, i + 0.5) for i in range(len(cycle) + 1)]
    R.build_base("in.mp4", segs, full_cfg, str(tmp_path), dry_run=True)
    scales = [arg(c, "-vf").split(":")[0] for c in cmds(capsys)[:-1]]
    assert scales[0] == scales[len(cycle)]        # الدورة بتلف
    assert len(set(scales)) == len(set(cycle))


def test_motion_disabled_gives_every_segment_the_same_frame(tmp_path, full_cfg, capsys):
    full_cfg["motion"]["enabled"] = False
    segs = [(i, i + 0.5) for i in range(4)]
    R.build_base("in.mp4", segs, full_cfg, str(tmp_path), dry_run=True)
    vfs = {arg(c, "-vf") for c in cmds(capsys)[:-1]}
    assert len(vfs) == 1


def test_concat_list_holds_absolute_paths(tmp_path, full_cfg, capsys):
    R.build_base("in.mp4", [(0.0, 1.0), (2.0, 3.0)], full_cfg, str(tmp_path),
                 dry_run=True)
    lines = (tmp_path / "concat.txt").read_text().splitlines()
    assert len(lines) == 2
    assert all(ln.startswith("file '/") for ln in lines)


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

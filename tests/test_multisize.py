"""
حلقة المقاسات من طرف لطرف عبر `--dry-run`.

بننادي `cli.main()` الحقيقي — بس `probe_duration` مبدّلة لأن ffprobe
بده ملف فيديو. كل الباقي حقيقي: القص، الكابشن، سلسلة الفلاتر، الأسماء.
"""
import json
import shlex
import sys

import pytest

from autoreel import cli as CLI, cuts as C
from conftest import ROOT, needs_raqm

DUR = 16.5


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """config حقيقي بمسارات مطلقة، وcwd مؤقت."""
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg["captions"]["font"] = str(ROOT / cfg["captions"]["font"])
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(C, "probe_duration", lambda _: DUR)
    monkeypatch.chdir(tmp_path)
    return tmp_path, str(p)


def run_cli(*args):
    sys.argv = ["autoreel.cli", *args]
    return CLI.main()


def ffmpeg_cmds(capsys):
    out = capsys.readouterr().out
    return [shlex.split(ln[2:]) for ln in out.splitlines() if ln.startswith("$ ")]


def base_args(cfgpath, out="out.mp4"):
    return ["raw.mp4", "--srt", str(ROOT / "test.srt"), "-c", cfgpath,
            "-o", out, "--dry-run"]


# ------------------------------------------------------------- التسمية

@needs_raqm
def test_default_run_keeps_the_plain_name(workdir, capsys):
    tmp, cfgp = workdir
    assert run_cli(*base_args(cfgp)) == 0
    targets = [c[-1] for c in ffmpeg_cmds(capsys)]
    assert any(t.endswith("/out.mp4") or t == "out.mp4" for t in targets)
    assert not any(".reel.mp4" in t for t in targets)


@needs_raqm
def test_multi_size_suffixes_every_output(workdir, capsys):
    tmp, cfgp = workdir
    assert run_cli(*base_args(cfgp), "--sizes", "all") == 0
    targets = [c[-1] for c in ffmpeg_cmds(capsys)]
    for name in ("reel", "square", "wide"):
        assert any(t.endswith(f"out.{name}.mp4") for t in targets), name


@needs_raqm
def test_output_directory_is_created(workdir, capsys):
    tmp, cfgp = workdir
    assert run_cli(*base_args(cfgp, out="نشر/reel.mp4"), "--sizes", "square") == 0
    assert (tmp / "نشر").is_dir()


# --------------------------------------------------- المشترَك يتحسب مرة

@needs_raqm
def test_shared_stages_run_once_for_three_sizes(workdir, capsys, monkeypatch):
    tmp, cfgp = workdir
    calls = {"probe": 0, "segs": 0, "remap": 0}

    monkeypatch.setattr(C, "probe_duration",
                        lambda _: (calls.__setitem__("probe", calls["probe"] + 1), DUR)[1])
    real_segs, real_remap = C.segments_from_words, C.remap_words
    monkeypatch.setattr(C, "segments_from_words",
                        lambda *a, **k: (calls.__setitem__("segs", calls["segs"] + 1),
                                         real_segs(*a, **k))[1])
    monkeypatch.setattr(C, "remap_words",
                        lambda *a, **k: (calls.__setitem__("remap", calls["remap"] + 1),
                                         real_remap(*a, **k))[1])

    assert run_cli(*base_args(cfgp), "--sizes", "all") == 0
    assert calls == {"probe": 1, "segs": 1, "remap": 1}, calls


@needs_raqm
def test_every_size_gets_its_own_encodes(workdir, capsys):
    tmp, cfgp = workdir
    run_cli(*base_args(cfgp), "--sizes", "reel")
    one = len(ffmpeg_cmds(capsys))
    run_cli(*base_args(cfgp), "--sizes", "all")
    three = len(ffmpeg_cmds(capsys))
    assert three == one * 3


# ------------------------------------------------- الهندسة لكل مقاس

@needs_raqm
def test_each_size_uses_its_own_geometry(workdir, capsys):
    tmp, cfgp = workdir
    run_cli(*base_args(cfgp), "--sizes", "all")
    vfs = [c[c.index("-vf") + 1] for c in ffmpeg_cmds(capsys) if "-vf" in c]
    assert any("crop=1080:1920:" in v for v in vfs)          # reel
    assert any("crop=1080:1080:" in v and "*0.3000" in v for v in vfs)   # square
    assert any("split[bg][fg]" in v for v in vfs)            # wide -> pad


@needs_raqm
def test_caption_overlay_y_differs_per_size(workdir, capsys):
    tmp, cfgp = workdir
    run_cli(*base_args(cfgp), "--sizes", "all")
    import re
    # `overlay=` بينتهي بـ"y=" كمان، فلازم regex مش split ساذجة
    ys = {m for c in ffmpeg_cmds(capsys) if "-filter_complex" in c
          for m in re.findall(r"y=(\d+)-h/2", c[c.index("-filter_complex") + 1])}
    assert len(ys) == 3, ys


# ----------------------------------------------------------- الفشل الجزئي

@needs_raqm
def test_one_bad_size_does_not_stop_the_others(workdir, capsys):
    tmp, cfgp = workdir
    cfg = json.loads(open(cfgp, encoding="utf-8").read())
    cfg["exports"]["square"]["geometry"] = {"fit": "stretch"}   # مرفوض
    open(cfgp, "w", encoding="utf-8").write(json.dumps(cfg))

    code = run_cli(*base_args(cfgp), "--sizes", "all")
    targets = [c[-1] for c in ffmpeg_cmds(capsys)]
    assert code == 1                                   # كود الخروج بيبلّغ
    assert any("out.reel.mp4" in t for t in targets)   # الباقي كمّل
    assert any("out.wide.mp4" in t for t in targets)
    assert not any("out.square.mp4" in t for t in targets)


@needs_raqm
def test_unknown_size_fails_before_any_work(workdir, capsys):
    tmp, cfgp = workdir
    with pytest.raises(KeyError, match="tiktok"):
        run_cli(*base_args(cfgp), "--sizes", "tiktok")
    assert not ffmpeg_cmds(capsys)


# ------------------------------------------- الكابشن الخارج عن الإطار

@needs_raqm
def test_caption_outside_the_frame_aborts_that_size(workdir, capsys):
    """خطأ مش تحذير: كابشن مقصوص مخرَج تالف بينكتشف بعد الرفع."""
    tmp, cfgp = workdir
    cfg = json.loads(open(cfgp, encoding="utf-8").read())
    cfg["exports"]["square"]["captions"] = {"size": 44, "y_ratio": 0.99}
    open(cfgp, "w", encoding="utf-8").write(json.dumps(cfg))

    code = run_cli(*base_args(cfgp), "--sizes", "reel,square")
    err = capsys.readouterr().err
    assert code == 1
    assert "برّا الإطار" in err


@needs_raqm
def test_captions_are_rendered_per_size_not_shared(workdir, capsys):
    """
    الكابشن لازم ينرسم بعرض كل مقاس. لو انشارك، ملفات الPNG بتكون
    نفسها — وهاد بالضبط الاشتقاق اللي رفضناه.
    """
    tmp, cfgp = workdir
    run_cli(*base_args(cfgp), "--sizes", "all")
    pngs = {p for c in ffmpeg_cmds(capsys) for p in c if p.endswith(".png")}
    dirs = {p.rsplit("/", 2)[-2] for p in pngs}
    assert dirs == {"caps_reel", "caps_square", "caps_wide"}, dirs


# ============================ --preview-frames ============================

@needs_raqm
def test_preview_writes_one_png_per_size(workdir, capsys):
    tmp, cfgp = workdir
    assert run_cli(*base_args(cfgp), "--sizes", "all", "--preview-frames") == 0
    targets = [c[-1] for c in ffmpeg_cmds(capsys)]
    for name in ("reel", "square", "wide"):
        assert f"out.{name}.preview.png" in " ".join(targets), name


@needs_raqm
def test_preview_does_no_encoding(workdir, capsys):
    """
    الهدف كله: تشوف نافذة القص قبل ما تصرف ترميز. أمر واحد لكل مقاس،
    وما في ولا libx264.
    """
    tmp, cfgp = workdir
    run_cli(*base_args(cfgp), "--sizes", "all", "--preview-frames")
    cmds = ffmpeg_cmds(capsys)
    assert len(cmds) == 3                       # واحد لكل مقاس
    for c in cmds:
        assert "libx264" not in c
        assert c[c.index("-frames:v") + 1] == "1"


@needs_raqm
def test_preview_seeks_the_middle_of_the_first_segment(workdir, capsys):
    tmp, cfgp = workdir
    run_cli(*base_args(cfgp), "--sizes", "reel", "--preview-frames")
    c = ffmpeg_cmds(capsys)[0]
    words = __import__("autoreel.transcribe", fromlist=["t"]).from_srt(
        str(ROOT / "test.srt"))
    import json as _json
    cfg = _json.loads(open(cfgp, encoding="utf-8").read())
    segs = C.segments_from_words(words, DUR, **cfg["cuts"])
    a0, b0 = segs[0]
    assert c[c.index("-ss") + 1] == f"{(a0 + b0) / 2:.3f}"


@needs_raqm
def test_preview_uses_each_size_geometry(workdir, capsys):
    tmp, cfgp = workdir
    run_cli(*base_args(cfgp), "--sizes", "all", "--preview-frames")
    chains = " ".join(" ".join(c) for c in ffmpeg_cmds(capsys))
    assert "crop=1080:1920:" in chains
    assert "*0.3000" in chains                  # crop_bias تبع المربع
    assert "split[bg][fg]" in chains            # pad تبع العريض


@needs_raqm
def test_preview_single_size_keeps_the_plain_name(workdir, capsys):
    tmp, cfgp = workdir
    run_cli(*base_args(cfgp), "--preview-frames")
    assert "out.preview.png" in " ".join(c[-1] for c in ffmpeg_cmds(capsys))


@needs_raqm
def test_preview_overlays_a_caption_when_there_is_one(workdir, capsys):
    tmp, cfgp = workdir
    run_cli(*base_args(cfgp), "--sizes", "reel", "--preview-frames")
    c = ffmpeg_cmds(capsys)[0]
    assert any(x.endswith(".png") and "caps_" in x for x in c)


# ================== تخطي Whisper لما ما إله لزوم ==================

def test_whisper_is_skipped_when_neither_cut_nor_captions(workdir, capsys, monkeypatch):
    tmp, cfgp = workdir
    from autoreel import transcribe as T

    def boom(*a, **k):
        raise AssertionError("Whisper انندهت بلا لزوم")
    monkeypatch.setattr(T, "transcribe", boom)
    monkeypatch.setattr(CLI, "T", T)

    args = ["raw.mp4", "-c", cfgp, "-o", "out.mp4", "--dry-run",
            "--no-cut", "--no-captions"]
    assert run_cli(*args) == 0
    assert "تخطّي" in capsys.readouterr().out


@needs_raqm
def test_whisper_still_runs_when_captions_are_on(workdir, capsys, monkeypatch):
    tmp, cfgp = workdir
    from autoreel import transcribe as T
    called = []
    monkeypatch.setattr(T, "transcribe",
                        lambda *a, **k: (called.append(1), [])[1])
    monkeypatch.setattr(CLI, "T", T)
    run_cli("raw.mp4", "-c", cfgp, "-o", "out.mp4", "--dry-run", "--no-cut")
    assert called, "الكابشن مفعّل فلازم يفرّغ"

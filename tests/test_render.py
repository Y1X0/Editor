"""
طبقة الفيديو عبر `--dry-run`.

هاي أول تغطية آلية لـ`render.py`. الفكرة إن `dry_run` بيوقف نداء ffmpeg
بس — خطة القص وسلسلة الفلاتر وأسماء الملفات كلها بتنحسب عادي — فاللي
بينطبع هو الأمر الحقيقي، وفحصه فحص للطبقة نفسها مش لبديل وهمي عنها.
"""
import json
import os
import re
import shlex

import pytest

from measure import sdr_probe

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
    """
    صور كابشن حقيقية بأحجام **مختلفة قليلًا** — زي الإنتاج بالضبط
    (عرض النص بيفرق ببكسل أو اتنين بين كابشن وكابشن).

    الاختلاف مقصود: هو اللي بيمسك انحدار توحيد المقاس.
    """
    from PIL import Image
    d = tmp_path / "caps"
    d.mkdir(exist_ok=True)
    out = []
    for i in range(n):
        p = d / f"c{i:04d}.png"
        Image.new("RGBA", (40 + i % 3, 12), (255, 0, 0, 255)).save(p)
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
    monkeypatch.setattr(R, "probe_source_full",
                        sdr_probe(640, 1138, True))


# --------------------------------------------------------------- الأساسيات

def test_preview_round_trips_through_the_shell():
    """الأمر المطبوع لازم يرجع لنفس الوسائط بالضبط لو نسخته للترمنال."""
    cmd = ["ffmpeg", "-vf", "crop=1:2:3:4,scale=5:6", "ملف فيه فراغ.mp4"]
    assert shlex.split(R.preview(cmd)) == cmd


def test_dry_run_produces_no_video(tmp_path, full_cfg, capsys):
    R.build_output("in.mp4", [(0.0, 2.0), (3.0, 4.0)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    assert not list(tmp_path.glob("*.mp4"))


def test_dry_run_returns_the_path_it_would_have_written(tmp_path, full_cfg, capsys):
    base = R.build_output("in.mp4", [(0.0, 2.0)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    assert base == str(tmp_path / "o.mp4")


def test_dry_run_does_not_touch_the_real_ffmpeg(tmp_path, full_cfg, monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("subprocess.run انندهت مع dry_run")
    monkeypatch.setattr(R.subprocess, "run", boom)
    R.build_output("in.mp4", [(0.0, 1.0)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    R.build_output("in.mp4", [(0.0, 1.0)], fake_caps(3, tmp_path), full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)


# ------------------------------------------------------ build_output

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
        R.build_output("in.mp4", [(i, i + 0.5) for i in range(n)], None,
                       full_cfg, str(tmp_path / "o.mp4"), str(tmp_path),
                       dry_run=True)
        assert len(cmds(capsys)) == 1


def test_video_pass_never_seeks_by_time(tmp_path, full_cfg, capsys):
    """
    **حارس CR-5.** `-ss` بزمن برّا شبكة الإطارات بتخلّي ffmpeg يكرّر أول
    إطار ليعبّي `t=0`. القصّ صار بفهرس الإطار، فما بيصير يرجع `-ss`
    ولا `-to` ولا `-t` لهالتشغيلة.
    """
    R.build_output("in.mp4", [(1.25, 3.5), (9.0, 10.0)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
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
    R.build_output("in.mp4", segs, None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
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
    R.build_output("in.mp4", [(0.0, 1.0)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    g = graph_of(tmp_path)
    assert g.index(f"fps={fps},select") < g.index("settb=")
    assert g.index("settb=") < g.index("setpts=N,")
    assert g.index("setpts=N,") < g.index(f"setpts=N,fps={fps}") + 1
    assert "/TB" not in g


def test_graph_goes_through_a_script_file_not_the_command_line(tmp_path,
                                                               full_cfg, capsys):
    """٣٠٠ مقطع = عشرات الكيلوبايتات، وحدود سطر الأوامر على أندرويد أضيق."""
    R.build_output("in.mp4", [(0.0, 1.0)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    c = cmds(capsys)[0]
    assert "-filter_complex_script" in c
    assert "-filter_complex" not in c
    assert arg(c, "-filter_complex_script") == str(tmp_path / "graph.txt")


def test_crop_matches_configured_output_size(tmp_path, full_cfg, capsys):
    W = full_cfg["output"]["width"]; H = full_cfg["output"]["height"]
    R.build_output("in.mp4", [(0.0, 1.0)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    assert f"crop={W}:{H}:" in graph_of(tmp_path)


def test_zoom_cycles_across_segments(tmp_path, full_cfg, capsys):
    """كل مقطع بياخد زوم من الدورة بالترتيب — هاد شكل الريلز المقصود."""
    cycle = full_cfg["motion"]["zoom_cycle"]
    segs = [(i, i + 0.5) for i in range(len(cycle) + 1)]
    R.build_output("in.mp4", segs, None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    g = graph_of(tmp_path)
    w = re.search(r"scale=w='([^']+)'", g).group(1)
    vals = [int(v) for v in re.findall(r"(\d+)\*between", w)]
    assert len(vals) == len(segs)
    assert vals[0] == vals[len(cycle)]              # الدورة بتلف
    assert len(set(vals)) == len(set(cycle))


def test_motion_disabled_gives_every_segment_the_same_zoom(tmp_path, full_cfg,
                                                           capsys):
    full_cfg["motion"]["enabled"] = False
    R.build_output("in.mp4", [(i, i + 0.5) for i in range(4)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    w = re.search(r"scale=w='([^']+)'", graph_of(tmp_path)).group(1)
    assert len({int(v) for v in re.findall(r"(\d+)\*between", w)}) == 1


def test_zoom_is_evaluated_per_frame(tmp_path, full_cfg, capsys):
    """بدون `eval=frame` الزوم بينتقيّم مرة وحدة وبيثبت على أول مقطع."""
    R.build_output("in.mp4", [(0, 1), (2, 3)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    assert "eval=frame" in graph_of(tmp_path)


def test_overlapping_segments_raise_instead_of_losing_frames(tmp_path, full_cfg):
    """
    `select` بتمرّر إطار المصدر مرة وحدة، فالتداخل بيقصّر المخرَج بصمت.
    """
    with pytest.raises(ValueError, match="متداخلة"):
        R.build_output("in.mp4", [(0.0, 2.0), (1.0, 3.0)], None, full_cfg,
                       str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)


# ------------------------------------------- الصوت بنفس التشغيلة

def test_audio_is_cut_in_the_same_single_pass(tmp_path, full_cfg, capsys):
    """
    صورة وصوت بتشغيلة وحدة. قبل المرحلة ٦ كان الصوت ترميز AAC لكل مقطع
    ثم `concat -c copy`، والـpriming بيتراكم — ١٥٢ms عند ٨ مقاطع.
    """
    segs = [(0.0, 1.0), (2.0, 3.0), (5.0, 6.5)]
    R.build_output("in.mp4", segs, None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
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
    R.build_output("in.mp4", segs, None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    spf = DEFAULT_SR // fps
    pairs = [(int(a), int(b)) for a, b in re.findall(
        r"atrim=start_sample=(\d+):end_sample=(\d+)", graph_of(tmp_path))]
    for (a, b), s, n in zip(pairs, start_frames(segs, fps), frame_plan(segs, fps)):
        assert (a, b) == (s * spf, (s + n) * spf)


def test_audio_is_encoded_once_at_the_output(tmp_path, full_cfg, capsys):
    R.build_output("in.mp4", [(0.0, 1.0)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    c = cmds(capsys)[0]
    assert arg(c, "-c:a") == "aac"
    assert graph_of(tmp_path).count("aac") == 0, "ترميز جوا الرسم"


def test_a_silent_source_produces_no_audio_chain(tmp_path, full_cfg, capsys,
                                                 monkeypatch):
    """
    `[0:a]` بتفشّل التشغيلة على مصدر بلا صوت، فلازم ينشال المسار كله.
    """
    monkeypatch.setattr(R, "probe_source_full",
                        sdr_probe(640, 1138, False))
    R.build_output("in.mp4", [(0.0, 1.0)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    assert "[0:a]" not in graph_of(tmp_path)
    assert "-c:a" not in cmds(capsys)[0]


def test_no_intermediate_segment_files_are_written(tmp_path, full_cfg, capsys):
    """سقالة المرحلة ٥ انشالت: ولا `seg*.mp4` ولا `concat.txt`."""
    R.build_output("in.mp4", [(0.0, 1.0), (2.0, 3.0)], None, full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["graph.txt"], f"ملفات وسيطة: {left}"


# ------------------------------------------------------------- الكابشن

def test_no_captions_means_no_caption_input_and_no_overlay(tmp_path, full_cfg,
                                                           capsys):
    R.build_output("in.mp4", [(0.0, 1.0)], [], full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    assert "overlay" not in graph_of(tmp_path)
    assert len([x for x in cmds(capsys)[0] if x == "-i"]) == 1


def test_every_frame_in_the_sequence_has_the_same_size(tmp_path):
    """
    **حارس انحدار على خلل مقاس.**

    تسلسل الصور بياخد أبعاد التيار من أول ملف، وأي تغيّر مقاس بالنص
    بيقطع المخرَج: صور ٤٠٧×٢٠٨ و٤٠٨×٢٠٨ — فرق **بكسل واحد** — أعطت
    ٧٣ إطار من ١٤٤. `fake_caps` بتولّد أحجامًا مختلفة عمدًا.
    """
    from PIL import Image
    caps = fake_caps(6, tmp_path)
    assert len({Image.open(p).size for p, _, _ in caps}) > 1, "المقدّمة ضعيفة"
    frames = [(p, i * 2, i * 2 + 2) for i, (p, _, _) in enumerate(caps)]
    d = tmp_path / "seq"
    R.materialise_captions(frames, 14, str(d))
    sizes = {Image.open(d / f"{n:06d}.png").size for n in range(14)}
    assert len(sizes) == 1, f"التسلسل فيه أحجام مختلفة: {sizes}"


def test_padding_keeps_the_caption_centred(tmp_path):
    """
    الoverlay بيوسّط الطبقة، فتوسيط الكابشن داخل الصندوق بيحافظ على
    مكانه بالضبط. لو انزاح، الكابشن بيتحرّك بالمخرَج.
    """
    from PIL import Image
    caps = fake_caps(3, tmp_path)
    frames = [(p, i, i + 1) for i, (p, _, _) in enumerate(caps)]
    d = tmp_path / "seq"
    R.materialise_captions(frames, 3, str(d))
    for n, (p, _, _) in enumerate(caps):
        big = Image.open(d / f"{n:06d}.png")
        bbox = big.getbbox()
        small = Image.open(p)
        left, right = bbox[0], big.width - bbox[2]
        top, bottom = bbox[1], big.height - bbox[3]
        assert abs(left - right) <= 1 and abs(top - bottom) <= 1
        assert (bbox[2] - bbox[0], bbox[3] - bbox[1]) == small.size


def test_captions_add_exactly_one_input_and_one_overlay(tmp_path, full_cfg,
                                                        capsys):
    """
    **overlay واحد مهما كان عدد الكابشنات.**

    السلسلة القديمة (overlay لكل كابشن) بتاكل الذاكرة مع العدد: قِسنا
    ٩٤١ MiB عند ٤٠ كابشن و٢٧٧١ MiB عند ٢٠٠. التسلسل المفهرس ثابت.
    """
    for n in (1, 60, 200):
        R.build_output("in.mp4", [(0.0, 4.0)], fake_caps(n, tmp_path), full_cfg,
                       str(tmp_path / "o.mp4"), str(tmp_path / f"w{n}"),
                       dry_run=True)
        g = (tmp_path / f"w{n}" / "graph.txt").read_text(encoding="utf-8")
        assert g.count("overlay") == 1, f"{n} كابشن -> {g.count('overlay')} overlay"
        c = cmds(capsys)[0]
        assert len([x for x in c if x == "-i"]) == 2


def test_caption_input_is_a_frame_indexed_sequence(tmp_path, full_cfg, capsys):
    R.build_output("in.mp4", [(0.0, 1.0)], fake_caps(2, tmp_path), full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    c = cmds(capsys)[0]
    assert arg(c, "-framerate") == str(full_cfg["output"]["fps"])
    assert arg(c, "-start_number") == "0"
    assert c[c.index("-start_number") + 3].endswith("%06d.png")


def test_no_concat_demuxer_and_no_loop_for_captions(tmp_path, full_cfg, capsys):
    """
    الاتنين مرفوضان بقياس: `concat` demuxer قاعدة زمنه ١/٢٥ فبيزحلق
    الكابشن نص إطار، و`-loop 1` بتولّد تيارًا بطول المخرَج لكل PNG
    (قِسنا ذروة ١٣.٥ GiB ثم SIGKILL).
    """
    R.build_output("in.mp4", [(0.0, 1.0)], fake_caps(3, tmp_path), full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    c = cmds(capsys)[0]
    assert "concat" not in c and "-loop" not in c


def test_overlay_y_follows_y_ratio(tmp_path, full_cfg, capsys):
    y = int(full_cfg["output"]["height"] * full_cfg["captions"]["y_ratio"])
    R.build_output("in.mp4", [(0.0, 1.0)], fake_caps(2, tmp_path), full_cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    assert f"y={y}-h/2" in graph_of(tmp_path)


# ------------------------------------------------- تسلسل الصور المفهرس

def test_sequence_has_a_file_for_every_output_frame(tmp_path):
    """
    فهرس ناقص بيوقّف التسلسل عنده — قِسناها: ١٢ إطار صاروا ٥ لما شلنا
    الملف رقم ٥. فالفجوات لازمها ملف شفاف مش لا شي.
    """
    caps = fake_caps(2, tmp_path)
    frames = [(caps[0][0], 2, 5), (caps[1][0], 7, 9)]
    d = tmp_path / "seq"
    R.materialise_captions(frames, 12, str(d))
    names = sorted(p.name for p in d.iterdir() if p.is_file() or p.is_symlink())
    assert names == [f"{n:06d}.png" for n in range(12)]


def test_every_sequence_entry_points_at_the_right_png(tmp_path):
    caps = fake_caps(2, tmp_path)
    frames = [(caps[0][0], 0, 3), (caps[1][0], 3, 6)]
    d = tmp_path / "seq"
    R.materialise_captions(frames, 6, str(d))
    got = [os.path.realpath(d / f"{n:06d}.png") for n in range(6)]
    assert len(set(got[:3])) == 1 and len(set(got[3:])) == 1
    assert got[0] != got[3], "الكابشنان بيأشّروا على نفس الملف"
    # الوصلة بتأشّر على النسخة المبطّنة، والمحتوى لازم يكون كابشنه
    from PIL import Image
    for src, link in ((caps[0][0], got[0]), (caps[1][0], got[3])):
        assert Image.open(link).getbbox() is not None
        assert Image.open(link).size >= Image.open(src).size


def test_gap_frames_point_at_a_transparent_png(tmp_path):
    caps = fake_caps(1, tmp_path)
    d = tmp_path / "seq"
    R.materialise_captions([(caps[0][0], 1, 2)], 3, str(d))
    from PIL import Image
    for n in (0, 2):
        img = Image.open(d / f"{n:06d}.png").convert("RGBA")
        assert img.getextrema()[3] == (0, 0), "إطار الفجوة مش شفاف"


def test_sequence_uses_links_not_copies_when_supported(tmp_path):
    """
    النسخ بيضاعف القرص بعدد الإطارات: PNG واحد بيتكرّر عبر كل إطاراته.
    """
    caps = fake_caps(1, tmp_path)
    d = tmp_path / "seq"
    R.materialise_captions([(caps[0][0], 0, 40)], 40, str(d))
    assert all((d / f"{n:06d}.png").is_symlink() for n in range(40))
    # نسخة مبطّنة **وحدة** بتخدم الأربعين إطار
    assert len({os.path.realpath(d / f"{n:06d}.png") for n in range(40)}) == 1


def test_sequence_falls_back_to_copying_when_symlink_is_unavailable(tmp_path,
                                                                    monkeypatch):
    """بعض تخزين أندرويد المشترك ما بيدعم الوصلات — لازم ينسخ مش يفشل."""
    def boom(*a, **k):
        raise OSError("symlink مش مدعومة")
    monkeypatch.setattr(os, "symlink", boom)
    caps = fake_caps(1, tmp_path)
    d = tmp_path / "seq"
    R.materialise_captions([(caps[0][0], 0, 3)], 3, str(d))
    for n in range(3):
        p = d / f"{n:06d}.png"
        assert p.exists() and not p.is_symlink()

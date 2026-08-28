"""
كل مفتاح بـ`config.json` موصول فعلًا بالكود.

**هالملف بيقرا `config.json` من القرص عمدًا** — مش config مبني جوا
الاختبار. السبب حادثة حقيقية: قراءة `motion.pan_px` انتقلت لقسم
`geometry` بينما المفتاح ساكن بـ`motion`، فالـpan صار صفر بصمت. كان في
١٩٠ فحص هندسة وما مسك ولا واحد — كلهن بيبنوا config خاص فيهن،
فبيتفقوا مع حالهم ويغلطوا مع الواقع.

الطريقة: غيّر قيمة المفتاح بالconfig المقروء، وتأكد إن **المخرَج
تغيّر**. مفتاح ما بيغيّر شي = ميت أو مفصول عن الكود.

لما تضيف مفتاح جديد، ضيف صفّه هون. شوف CLAUDE.md
"""
import copy
import json
import os

import pytest

from measure import sdr_probe

from autoreel import captions as CAP, cuts as C, exports as X, graph as G, render as R
from conftest import ROOT, needs_raqm, words


@pytest.fixture
def raw():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


@pytest.fixture
def cfg(raw):
    """الconfig الحقيقي بمسار خط مطلق حتى يشتغل من أي مجلد."""
    c = copy.deepcopy(raw)
    c["captions"]["font"] = str(ROOT / c["captions"]["font"])
    return c


def bumped(cfg, path, value):
    c = copy.deepcopy(cfg)
    node = c
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return c


# ------------------------------------------------------- الملف نفسه سليم

def test_config_parses_and_has_every_section(raw):
    for section in ("output", "cuts", "motion", "geometry", "captions",
                    "sfx", "exports", "whisper_model", "language"):
        assert section in raw, f"قسم ناقص بالconfig: {section}"


def test_font_file_referenced_by_config_exists(raw):
    assert (ROOT / raw["captions"]["font"]).is_file()


def test_no_dead_keys_left_behind(raw):
    """
    كل مفتاح مسرود هون عليه فحص تحت. لو ضفت مفتاح للconfig ونسيت
    الفحص، هالفحص بيفشل ويذكّرك.
    """
    covered = {
        "whisper_model", "language",
        "output.width", "output.height", "output.fps", "output.crf",
        "cuts.min_gap", "cuts.pad", "cuts.min_seg",
        "motion.enabled", "motion.zoom_cycle", "motion.pan_px",
        "geometry.fit", "geometry.crop_bias", "geometry.pad_blur",
        "geometry.tonemap", "geometry.tonemap_npl",
        "captions.enabled", "captions.font", "captions.size",
        "captions.max_words", "captions.color", "captions.highlight",
        "captions.box", "captions.y_ratio",
        "sfx.enabled", "sfx.min_gap", "sfx.speech_gain", "sfx.events",
        "exports",
    }
    actual = set()
    for k, v in raw.items():
        if isinstance(v, dict) and k != "exports":
            actual |= {f"{k}.{kk}" for kk in v}
        else:
            actual.add(k)
    assert actual - covered == set(), f"مفاتيح بلا فحص ربط: {actual - covered}"
    assert covered - actual == set(), f"فحص لمفاتيح مش موجودة: {covered - actual}"


# --------------------------------------------------------------- output.*

@pytest.fixture(autouse=True)
def _no_probe(monkeypatch):
    """
    `build_base` بتقرا أبعاد المصدر (لازمة لمرساة القصّ بالمسار الواحد).
    الملفات هون وهمية، والأبعاد مش الشي المفحوص — فبنثبّتها.
    """
    monkeypatch.setattr(R, "probe_source_full",
                        sdr_probe(640, 1138, True))


@pytest.mark.parametrize("key,alt", [("width", 720), ("height", 1280),
                                     ("fps", 24)])
def test_output_geometry_keys_reach_the_filter(cfg, key, alt):
    a = R.segment_filter(cfg)
    b = R.segment_filter(bumped(cfg, ["output", key], alt))
    assert a != b, f"output.{key} ما وصل سلسلة الفلاتر"


def test_output_crf_reaches_ffmpeg(cfg, tmp_path, capsys):
    R.build_output("in.mp4", [(0.0, 1.0)], None,
                   bumped(cfg, ["output", "crf"], 33),
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    assert "33" in capsys.readouterr().out


# ----------------------------------------------------------------- cuts.*

@pytest.mark.parametrize("key,alt", [("min_gap", 5.0), ("pad", 0.4),
                                     ("min_seg", 3.0)])
def test_cuts_keys_change_the_plan(cfg, key, alt):
    w = words(("a", 0.0, 0.5), ("b", 1.2, 1.7), ("c", 4.0, 4.5))
    a = C.segments_from_words(w, 6.0, **cfg["cuts"])
    b = C.segments_from_words(w, 6.0, **bumped(cfg, ["cuts", key], alt)["cuts"])
    assert a != b, f"cuts.{key} ما غيّر خطة القص"


def test_cuts_min_gap_is_the_caption_bridge(cfg, caps_dir=None):
    """`cli.py` بتمرّرها كـbridge_gap — لو انفصلت بيرجع طفي الكابشن."""
    import inspect
    src = inspect.getsource(__import__("autoreel.cli", fromlist=["cli"]))
    assert 'bridge_gap=cfg["cuts"]["min_gap"]' in src


# --------------------------------------------------------------- motion.*

def test_motion_enabled_flattens_the_zoom(cfg, tmp_path, capsys):
    segs = [(i, i + 0.5) for i in range(4)]
    R.build_output("in.mp4", segs, None,
                   bumped(cfg, ["motion", "enabled"], False),
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    off = capsys.readouterr().out
    R.build_output("in.mp4", segs, None, cfg, str(tmp_path / "o.mp4"),
                   str(tmp_path), dry_run=True)
    assert off != capsys.readouterr().out


def test_motion_zoom_cycle_reaches_the_filter(cfg, tmp_path, capsys):
    R.build_output("in.mp4", [(0, 1), (1, 2)], None, cfg,
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    a = capsys.readouterr().out
    R.build_output("in.mp4", [(0, 1), (1, 2)], None,
                   bumped(cfg, ["motion", "zoom_cycle"], [1.0, 1.5]),
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    assert a != capsys.readouterr().out


def test_motion_pan_px_reaches_the_filter(cfg):
    """
    الانحدار الحقيقي اللي فرض هالملف: pan_px انقرا من geometry بينما
    هو بـmotion، فصار صفر بصمت.
    """
    z = max(cfg["motion"]["zoom_cycle"])
    a = R.segment_filter(cfg, zoom=z, pan_dir=1)
    b = R.segment_filter(bumped(cfg, ["motion", "pan_px"], 0), zoom=z, pan_dir=1)
    assert a != b, "motion.pan_px ما وصل سلسلة الفلاتر"


# ------------------------------------------------------------- geometry.*

def test_geometry_fit_switches_the_whole_chain(cfg):
    a = R.segment_filter(cfg)
    b = R.segment_filter(bumped(cfg, ["geometry", "fit"], "pad"))
    assert "split[bg][fg]" in b and "split" not in a


@pytest.mark.parametrize("key,alt", [("tonemap", "hable"), ("tonemap_npl", 250)])
def test_geometry_tonemap_keys_reach_the_chain(cfg, key, alt):
    """
    مفتاحا الـtonemap بينقروا من `geometry` وبينوصلوا `build_graph`.

    المصدر هون **لازم يكون HDR** — بغيره السلسلة بترجع فاضية والمفتاحان
    ما بيغيّروا شي، فالفحص بيمرّ على مفتاح ميت.
    """
    hdr = {"trc": "arib-std-b67", "primaries": "bt2020", "matrix": "bt2020nc",
           "hdr": True, "bits": 10, "pix_fmt": "yuv420p10le", "range": "tv"}
    a, _ = G.build_graph(cfg, [10], [0], [("reel", cfg)], 1080, 1920,
                         with_audio=False, colors=hdr)
    b, _ = G.build_graph(bumped(cfg, ["geometry", key], alt), [10], [0],
                         [("reel", cfg)], 1080, 1920, with_audio=False, colors=hdr)
    assert a != b, f"geometry.{key} ما وصل سلسلة الـtonemap"


def test_geometry_crop_bias_moves_the_window(cfg):
    a = R.segment_filter(cfg)
    b = R.segment_filter(bumped(cfg, ["geometry", "crop_bias"], 0.1))
    assert a != b


def test_geometry_pad_blur_reaches_the_filter(cfg):
    c = bumped(cfg, ["geometry", "fit"], "pad")
    assert "gblur=sigma=24" in R.segment_filter(c)
    assert "gblur=sigma=7" in R.segment_filter(bumped(c, ["geometry", "pad_blur"], 7))


# ------------------------------------------------------------- captions.*

@needs_raqm
@pytest.mark.parametrize("key,alt", [("size", 40), ("color", [1, 2, 3]),
                                     ("highlight", [9, 8, 7]), ("box", [1, 1, 1, 9])])
def test_caption_keys_change_the_pixels(cfg, key, alt):
    t = "واحد اثنين ثلاثة"
    a = CAP.render_caption(t, cfg["captions"], 1080, highlight_idx=1).tobytes()
    CAP._LAYOUT_CACHE.clear()
    b = CAP.render_caption(t, bumped(cfg, ["captions", key], alt)["captions"],
                           1080, highlight_idx=1).tobytes()
    assert a != b, f"captions.{key} ما أثّر على الرسم"


@needs_raqm
def test_caption_font_changes_the_pixels(cfg):
    t = "واحد اثنين"
    a = CAP.render_caption(t, cfg["captions"], 1080).tobytes()
    CAP._LAYOUT_CACHE.clear()
    other = str(ROOT / "fonts" / "Tajawal-Bold.ttf")
    b = CAP.render_caption(t, bumped(cfg, ["captions", "font"], other)["captions"],
                           1080).tobytes()
    assert a != b


def test_caption_max_words_changes_the_grouping(cfg):
    w = words(*[(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(9)])
    a = CAP.group_words(w, cfg["captions"]["max_words"])
    b = CAP.group_words(w, cfg["captions"]["max_words"] + 2)
    assert [len(g["words"]) for g in a] != [len(g["words"]) for g in b]


def test_caption_y_ratio_reaches_the_overlay(cfg, tmp_path, capsys):
    png = tmp_path / "a.png"
    from PIL import Image
    Image.new("RGBA", (10, 10)).save(png)
    R.build_output("in.mp4", [(0.0, 1.0)], [(str(png), 0.0, 1.0)],
                   bumped(cfg, ["captions", "y_ratio"], 0.5),
                   str(tmp_path / "o.mp4"), str(tmp_path), dry_run=True)
    y = int(cfg["output"]["height"] * 0.5)
    assert f"y={y}-h/2" in capsys.readouterr().out


def test_caption_enabled_gates_the_captions(cfg):
    import inspect
    src = inspect.getsource(__import__("autoreel.cli", fromlist=["cli"]))
    assert 'cfg["captions"]["enabled"]' in src or 'root["captions"]["enabled"]' in src


# ------------------------------------------------------- whisper و exports

def test_whisper_keys_are_passed_to_transcribe(cfg, monkeypatch):
    seen = {}

    def fake(path, model_size="small", language="ar", cache=None):
        seen["model"], seen["lang"] = model_size, language
        return []
    from autoreel import transcribe as T
    monkeypatch.setattr(T, "transcribe", fake)
    T.transcribe("x.mp4", cfg["whisper_model"], cfg["language"])
    assert seen["model"] == cfg["whisper_model"]
    assert seen["lang"] == cfg["language"]

    import inspect
    src = inspect.getsource(__import__("autoreel.cli", fromlist=["cli"]))
    assert 'root["whisper_model"], root["language"]' in src


def test_every_export_resolves_and_differs(raw):
    seen = []
    for name in X.names(raw):
        c = X.resolve(raw, name)
        seen.append((c["output"]["width"], c["output"]["height"]))
    assert len(set(seen)) == len(seen), "مقاسان بنفس الأبعاد"


# ------------------------------------------------------------------ sfx.*

def _sfx_graph(cfg, plan=(60, 75, 60, 45), fps=30):
    """
    نص رسم الفلاتر بمؤثرات — الطريق الأقصر لإثبات إن المفتاح موصول.

    الخطة بتنبنى من نفس المصادر اللي `cli` بتستعملها، فأي مفتاح ما
    بيغيّر الرسم = مفصول عن الكود.
    """
    from autoreel import graph as G, sfx as SFX
    scfg = cfg.get("sfx") or {}
    if not scfg.get("enabled", True):
        return ""
    cues = SFX.plan_cues(list(plan), fps, zooms=[1.0, 1.1, 1.2, 1.0],
                         caption_frames=[10, 12, 40, 100, 150, 210], cfg=scfg)
    if not cues:
        return ""
    inputs = {a: i + 1 for i, a in enumerate(sorted({c.asset for c in cues}))}
    return ";".join(G.sfx_chain(
        cues, inputs,
        speech_gain=float(scfg.get("speech_gain", G.DEFAULT_SPEECH_GAIN))))


def test_sfx_enabled_is_wired(cfg):
    """
    **الافتراضي `false`.** ميزة جديدة ما بتغيّر صوت كل ريل بلا طلب —
    وتشغيلها افتراضيًا كسر E2 فعلًا (٩ نقرات بدل ٨، مؤثر انعدّ كنقرة).
    """
    assert cfg["sfx"]["enabled"] is False, "المؤثرات مشغّلة افتراضيًا"
    assert _sfx_graph(bumped(cfg, ["sfx", "enabled"], True)), "التشغيل ما بيبني شي"
    assert _sfx_graph(cfg) == ""


def test_sfx_min_gap_is_wired(cfg):
    """كابشنان متلاصقان (١٠ و١٢): فجوة أكبر بتبلع التاني."""
    on = bumped(cfg, ["sfx", "enabled"], True)
    tight = _sfx_graph(bumped(on, ["sfx", "min_gap"], 0.01))
    wide = _sfx_graph(bumped(on, ["sfx", "min_gap"], 1.0))
    assert tight.count("adelay=") > wide.count("adelay="), \
        "min_gap ما غيّرت عدد المؤثرات"


def test_sfx_speech_gain_is_wired(cfg):
    on = bumped(cfg, ["sfx", "enabled"], True)
    assert "volume=0.7000[spk]" in _sfx_graph(on)
    assert "volume=0.5000[spk]" in _sfx_graph(
        bumped(on, ["sfx", "speech_gain"], 0.5))


# ------------------------------------------- sfx.events (خريطة الأحداث)

def test_the_config_defines_every_event_type(raw):
    """
    **الconfig هو مصدر الخريطة.** لازم يغطّي كل نوع بـ`PRIORITY` —
    نوع ناقص بيعني إن الكود بيرجع لجدوله الاحتياطي بصمت، وبيصير
    مصدران للحقيقة.
    """
    from autoreel import sfx as SFX
    ev = raw["sfx"]["events"]
    assert set(ev) == set(SFX.PRIORITY), \
        f"ناقص/زايد: {set(SFX.PRIORITY) ^ set(ev)}"
    for kind, spec in ev.items():
        assert set(spec) == {"asset", "gain", "enabled"}, f"{kind}: {spec}"


def test_every_asset_named_in_the_config_exists(raw):
    from autoreel import render as R
    for kind, spec in raw["sfx"]["events"].items():
        assert os.path.isfile(R.sfx_asset(spec["asset"])), kind


def test_changing_an_asset_in_the_config_changes_the_graph(cfg):
    """الطفرة: بدّل أصل حدث بالconfig — لازم المخرَج يتبدّل."""
    on = bumped(cfg, ["sfx", "enabled"], True)
    base = _sfx_graph(on)
    swapped = copy.deepcopy(on)
    swapped["sfx"]["events"]["caption"]["asset"] = "tick"
    other = _sfx_graph(swapped)
    assert base != other, "تبديل الأصل ما غيّر الرسم"

    from autoreel import graph as G, sfx as SFX
    cues = SFX.plan_cues([60, 75, 60, 45], 30, zooms=[1.0, 1.1, 1.2, 1.0],
                         caption_frames=[40, 100], cfg=swapped["sfx"])
    assert {c.asset for c in cues if c.kind == "caption"} == {"tick"}


def test_changing_a_gain_in_the_config_changes_the_graph(cfg):
    on = bumped(cfg, ["sfx", "enabled"], True)
    louder = copy.deepcopy(on)
    louder["sfx"]["events"]["caption"]["gain"] = 0.11
    assert "volume=0.1100" in _sfx_graph(louder)
    assert "volume=0.1100" not in _sfx_graph(on)


def test_disabling_one_event_type_removes_only_its_cues(cfg):
    from autoreel import sfx as SFX
    on = copy.deepcopy(bumped(cfg, ["sfx", "enabled"], True))
    args = dict(zooms=[1.0, 1.1, 1.2, 1.0], caption_frames=[40, 100, 150])
    before = SFX.plan_cues([60, 75, 60, 45], 30, cfg=on["sfx"], **args)
    on["sfx"]["events"]["caption"]["enabled"] = False
    after = SFX.plan_cues([60, 75, 60, 45], 30, cfg=on["sfx"], **args)
    assert {c.kind for c in before} > {c.kind for c in after}
    assert "caption" not in {c.kind for c in after}
    assert {c.kind for c in after}, "انطفوا كلهن — الفحص فقد معناه"


def test_the_word_event_is_reachable_from_the_config(cfg):
    """
    `word` مطفي افتراضيًا، **بس لازم يشتغل لما ينتشغّل**. مفتاح
    بالconfig ما بيغيّر شي هو مفتاح ميت — ونفس القاعدة اللي فرضت
    هالملف من الأساس.
    """
    from autoreel import sfx as SFX
    on = copy.deepcopy(bumped(cfg, ["sfx", "enabled"], True))
    on["sfx"]["events"]["word"]["enabled"] = True
    cues = SFX.plan_cues([600], 30, word_frames=[100, 200, 300],
                         cfg=on["sfx"])
    assert "word" in {c.kind for c in cues}, "`word` مفتاح ميت"


def test_no_event_to_asset_mapping_lives_outside_sfx_py():
    """
    حارس ضد مصدر حقيقة تاني: أسماء الأصول ما بتنكتب بأي ملف إنتاج
    غير `sfx.py` (وهو الاحتياطي الموثّق).
    """
    import ast
    root = os.path.join(ROOT, "autoreel")
    names = {"whoosh", "pop", "impact", "tick", "riser"}
    bad = []
    for f in sorted(os.listdir(root)):
        if not f.endswith(".py") or f == "sfx.py":
            continue
        tree = ast.parse(open(os.path.join(root, f), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in names:
                bad.append(f"{f}:{node.lineno} -> {node.value!r}")
    assert not bad, "ربط حدث->أصل برّا sfx.py:\n" + "\n".join(bad)

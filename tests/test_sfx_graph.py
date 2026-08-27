"""
`graph.sfx_chain` — شكل الرسم (وحدات) وسلوكه على ناتج ffmpeg الفعلي.

الفحوص هون بتشغّل الرسم **مباشرة** مش عبر `render.build_output`، لأن
الوصل بالإنتاج مرحلة ٥. يعني: مسار الرسم مثبَّت بالقياس من هلأ،
و`test_sfx_acceptance.py` (المسار الإنتاجي) بيضل أحمر لحد ما ينوصل.
"""
import os
import subprocess

import pytest

from measure import build_source, count_frames, ffmpeg_available
from measure import sfx as S

from autoreel import cuts as C
from autoreel import graph as G
from autoreel import sfx as X

FPS, SR = 30, 48000
SEGS = [(1.0, 3.0), (5.0, 7.5), (9.0, 11.0), (12.5, 14.0)]
SCFG = {"output": {"width": 320, "height": 568, "fps": FPS},
        "motion": {"enabled": False, "zoom_cycle": [1.0], "pan_px": 0},
        "geometry": {"fit": "crop", "crop_bias": 0.5}}


TRANSIENT = ("tick", "pop", "impact")


def _cues():
    plan = C.frame_plan(SEGS, FPS)
    return X.plan_cues(plan, FPS, zooms=[1.0, 1.1, 1.2, 1.0],
                       caption_frames=[40, 100, 150, 210])


def _transient_cues():
    """
    مؤثرات **عابرة بس** — لفحوص العدّ والدقة.

    `whoosh` و`riser` غلافهن بيصعد وينزل، فبيعبروا العتبة النسبية
    أكتر من مرة والكاشف بيعدّهن ٤–٧ نبضات للمؤثر الواحد (مقيس: ٢١
    نبضة لـ٨ مؤثرات). نفس جذر أرضيتهن الكبيرة — ذروتهن مش عند
    بدايتهن. الوجود بينفحص بطاقة النافذة، والعدّ والدقة بالعابرات.
    """
    plan = C.frame_plan(SEGS, FPS)
    return X.plan_cues(plan, FPS, caption_frames=[40, 100, 150, 210],
                       cfg={"events": {k: {"enabled": k in ("start", "caption")}
                                       for k in X.PRIORITY}})


def _inputs(cues):
    return {a: i + 1 for i, a in enumerate(sorted({c.asset for c in cues}))}


# =============================================================== الشكل

def test_the_chain_is_pure_text():
    cues = _cues()
    parts = G.sfx_chain(cues, _inputs(cues))
    assert all(isinstance(p, str) for p in parts)


def test_normalize_zero_is_present():
    """
    الطفرة اللي بتفشّلها: شيلها. مقيس بدونها: الكلام ٠.١١× عند ٢٠
    مؤثرًا، **وبيتنفّس** مع انتهاء كل مؤثر.
    """
    cues = _cues()
    text = ";".join(G.sfx_chain(cues, _inputs(cues)))
    assert "normalize=0" in text
    assert "amix=" in text


def test_every_delay_sets_all_channels():
    """بدون `all=1` المؤثر الستيريو بيقع عند العيّنة ٠ — صامتة تمامًا."""
    cues = _cues()
    parts = G.sfx_chain(cues, _inputs(cues))
    delays = [p for p in parts if "adelay=" in p]
    assert delays
    assert all("all=1" in p for p in delays)


def test_aformat_comes_before_every_delay():
    """
    `adelay=NS` بتعدّ عيّنات بمعدّل **المدخَل**. أصل 44.1k بلا تطبيع
    مسبق بيقع بعد ٥٢٢٤٥ بدل ٤٨٠٠٠ = +٨٨ms.
    """
    cues = _cues()
    parts = G.sfx_chain(cues, _inputs(cues))
    heads = [p for p in parts if "aformat=" in p]
    assert len(heads) == len({c.asset for c in cues})
    for h in heads:
        assert f"sample_rates={SR}" in h and "channel_layouts=stereo" in h
        assert "adelay" not in h, "التأخير قبل التطبيع"


def test_delays_are_absolute_not_cumulative():
    """
    كل `adelay` بتحمل فهرس العيّنة المطلق للمؤثر. هيك الخطأ ما
    بيتراكم **بالبناء** — آخر مؤثر بنفس دقة أوّلهن.
    """
    cues = _cues()
    parts = G.sfx_chain(cues, _inputs(cues))
    got = [int(p.split("adelay=")[1].split("S")[0])
           for p in parts if "adelay=" in p]
    assert got == [c.sample for c in cues]
    assert got == sorted(got)


def test_an_asset_used_many_times_is_opened_once_and_split():
    """مقيس: `asplit` بدل مدخل لكل استعمال بتوفّر ٣٤–٣٨٪ ذاكرة ووقت."""
    cues = _cues()
    parts = G.sfx_chain(cues, _inputs(cues))
    usage = X.asset_usage(cues)
    repeated = [a for a, n in usage.items() if n > 1]
    assert repeated, "السيناريو ما فيه أصل مكرَّر فالفحص فقد معناه"
    heads = [p for p in parts if "aformat=" in p]
    assert len(heads) == len(usage), "أصل انفتح أكتر من مرة"
    for a in repeated:
        assert any(f"asplit={usage[a]}" in p for p in heads)


def test_no_limiter_anywhere():
    """مقيس: `alimiter` بيأخّر التيار ٢٣٩ عيّنة (٤.٩٨ms)."""
    cues = _cues()
    assert "alimiter" not in ";".join(G.sfx_chain(cues, _inputs(cues)))


def test_speech_gain_is_applied_to_the_cut_audio():
    cues = _cues()
    text = ";".join(G.sfx_chain(cues, _inputs(cues)))
    assert f"[acat]volume={G.DEFAULT_SPEECH_GAIN:.4f}" in text


def test_a_missing_asset_input_is_refused():
    cues = _cues()
    with pytest.raises(ValueError):
        G.sfx_chain(cues, {})


def test_no_cues_means_no_filter_at_all():
    """
    بلا مؤثرات المسار لازم يضل **حرفيًا** زي ما كان — وإلا كل مخرَج
    بلا SFX بيتغيّر بلا سبب.
    """
    plan = C.frame_plan(SEGS, FPS)
    starts = G.start_frames(SEGS, FPS)
    before = G.audio_chain(FPS, starts, plan, ["ao0"])
    after = G.audio_chain(FPS, starts, plan, ["ao0"], cues=[], sfx_inputs={})
    assert before == after
    assert not any("amix" in p or "adelay" in p for p in after)


def test_build_graph_without_cues_is_unchanged():
    plan = C.frame_plan(SEGS, FPS)
    starts = G.start_frames(SEGS, FPS)
    a, _ = G.build_graph(SCFG, plan, starts, [("reel", SCFG)], 320, 568)
    b, _ = G.build_graph(SCFG, plan, starts, [("reel", SCFG)], 320, 568,
                         cues=None, sfx_inputs=None)
    assert a == b


# ================================================= على ناتج ffmpeg فعليًا

pytestmark_slow = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود")


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """تشغيلتان متطابقتان إلا بالمؤثرات — والفرق بينهن هو إشارة المؤثر."""
    if not ffmpeg_available():
        pytest.skip("ffmpeg مش موجود")
    d = tmp_path_factory.mktemp("sfxgraph")
    src = build_source(d, width=320, height=568, fps=FPS, nframes=420)
    plan = C.frame_plan(SEGS, FPS)
    starts = G.start_frames(SEGS, FPS)
    cues = _cues()
    inputs = _inputs(cues)

    def render(name, with_cues, acodec, use=None):
        use = use if use is not None else cues
        g, maps = G.build_graph(
            SCFG, plan, starts, [("reel", SCFG)], 320, 568,
            cues=use if with_cues else None,
            sfx_inputs=inputs if with_cues else None)
        gp = str(d / "g.txt")
        open(gp, "w", encoding="utf-8").write(g)
        args = ["ffmpeg", "-y", "-loglevel", "error", "-i", src["path"]]
        if with_cues:
            for a in sorted(inputs, key=inputs.get):
                args += ["-i", S.asset(a)]
        _, v, al = maps[0]
        out = str(d / name)
        args += ["-filter_complex_script", gp, "-map", f"[{v}]", "-map", f"[{al}]",
                 "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
                 "-pix_fmt", "yuv420p", "-c:a", acodec]
        # **`-ac 2` على التشغيلتين** — زي ما بيعمل الإنتاج بالضبط.
        # بدونها المرجع بيطلع مونو والمزيج ستيريو، والمقارنة بينهن
        # عبر مسبار بيخفض لمونو بتخترع معامل ١/√٢ **مش موجود بالرسم**.
        # صار معنا: "كسب الكلام ٠.٤٩٥" وطلع خلل قياس مش إنتاج.
        args += ["-ac", "2"]
        if acodec == "aac":
            args += ["-b:a", "128k", "-ar", str(SR)]
        subprocess.run(args + [out], check=True, capture_output=True)
        return out

    return {
        "plan": plan, "cues": cues,
        "off": render("off.mkv", False, "pcm_s16le"),
        "on": render("on.mkv", True, "pcm_s16le"),
        "tcues": _transient_cues(),
        "on_t": render("on_t.mkv", True, "pcm_s16le", _transient_cues()),
        "off_mp4": render("off.mp4", False, "aac"),
        "on_mp4": render("on.mp4", True, "aac"),
    }


def _touched(cues):
    out = set()
    for c in cues:
        n = S.wav_info(S.asset(c.asset))[3]
        out.update(range(max(0, c.sample - 8), c.sample + n + 8))
    return out


def _sfx_signal(rendered, key="on", cues_key="cues"):
    """
    الفرق بعد **إلغاء كسب الكلام** — إشارة المؤثرات معزولة.

    بلا إلغاء الكسب، فرق الكلام بيضل بالإشارة والكاشف بيمسك نقرات
    المصدر كأنها مؤثرات: مقيس ٢٧ نبضة مقابل ٨ مؤثرات، والزيادة كلها
    عند مضاعفات ٢٤٠٠٠ عيّنة = نقرة كل نص ثانية. بعد الإلغاء بقايا
    الكلام ≈١e−٥.
    """
    touched = _touched(rendered[cues_key])
    g = S.estimate_gain(rendered[key], rendered["off"], touched)
    return S.difference(rendered[key], rendered["off"], gain=g), g


def test_the_effects_are_really_in_the_output(rendered):
    """
    **حارس الوجود.** كل باقي الفحوص بتقيس "ما تغيّر شي" وبتنجح تمامًا
    لو المؤثرات ما نزلت. هاد بيقيس إنها نزلت، وبالعدد الصح.
    """
    diff, _ = _sfx_signal(rendered)
    assert max(diff) > 0.01, "الفرق صفر — ما في مؤثرات بالمخرَج"

    # الوجود بطاقة النافذة مش بعدّ النبضات: الأصول الصاعدة بتعبر
    # العتبة أكتر من مرة، فالعدّ ما بيشتغل إلا للعابرة.
    for c in rendered["cues"]:
        n = S.wav_info(S.asset(c.asset))[3]
        win = diff[c.sample:c.sample + n]
        assert win and max(win) > 0.01, \
            f"ما في طاقة عند {c.asset}@إطار {c.frame}"

    # وبرّا كل النوافذ لازم تكون الإشارة شبه صفر
    touched = _touched(rendered["cues"])
    outside = [diff[i] for i in range(len(diff)) if i not in touched]
    assert max(outside) < 0.01, \
        f"طاقة برّا نوافذ المؤثرات: {max(outside):.4f} — الكلام ما انلغى"


def test_every_planned_cue_has_energy_and_nothing_else_does(rendered):
    """
    العدّ بالنوافذ مش بقائمة نبضات عامة: كل مؤثر مخطَّط إله طاقة
    بنافذته، وولا طاقة برّا النوافذ. السبب بـ`onset_in_window`.
    """
    diff, _ = _sfx_signal(rendered, "on_t", "tcues")
    for c in rendered["tcues"]:
        n = S.wav_info(S.asset(c.asset))[3]
        assert S.onset_in_window(diff, c.sample, n) is not None, \
            f"ما في مؤثر عند {c.asset}@إطار {c.frame}"
    touched = _touched(rendered["tcues"])
    outside = [diff[i] for i in range(len(diff)) if i not in touched]
    assert max(outside) < 0.01, f"طاقة برّا النوافذ: {max(outside):.4f}"


def test_each_transient_cue_lands_on_its_planned_sample(rendered):
    """
    دقة الوضع بأصول **عابرة** بس — أرضية `whoosh`/`riser` بالآلاف لأن
    ذروتهن مش عند بدايتهن (`test_sfx_floor.py`).
    """
    diff, _ = _sfx_signal(rendered, "on_t", "tcues")
    errs = []
    for cue in rendered["tcues"]:
        assert cue.asset in TRANSIENT
        n = S.wav_info(S.asset(cue.asset))[3]
        hit = S.onset_in_window(diff, cue.sample, n)
        assert hit is not None
        err = hit - S.detector_floor(cue.asset) - cue.sample
        errs.append((cue.frame, cue.asset, err))
        assert abs(err) <= 2, \
            f"{cue.asset}@إطار {cue.frame}: انزياح {err} عيّنة"
    assert len(errs) >= 4, f"عابرات قليلة للفحص: {errs}"


def test_placement_error_does_not_accumulate(rendered):
    """`adelay` مطلقة، فآخر مؤثر لازم يكون بنفس دقة أوّلهن."""
    diff, _ = _sfx_signal(rendered, "on_t", "tcues")
    errs = [S.onset_in_window(diff, c.sample,
                              S.wav_info(S.asset(c.asset))[3])
            - S.detector_floor(c.asset) - c.sample
            for c in rendered["tcues"]]
    assert len(errs) >= 2
    assert abs(errs[-1] - errs[0]) <= 1, f"الانزياح بيتراكم: {errs}"


def test_sample_count_is_unchanged(rendered):
    """`duration=first` — مؤثر قريب من النهاية ما بيمدّد المخرَج."""
    assert len(S.pcm(rendered["on"])) == len(S.pcm(rendered["off"]))


def test_a_cue_near_the_end_does_not_extend_the_output(rendered, tmp_path):
    """
    **الطفرة اللي بتفشّلها: شيل `duration=first`.**

    السيناريو العادي ما بيمسكها — كل المؤثرات بتخلص قبل النهاية.
    بيلزم مؤثر **طويل قرب الآخر**: `riser` (٥٥١٩٩ عيّنة) عند إطار
    ٢٣٩ بيمتد لـ٤٣٧٥٩٩ والمخرَج ٣٨٤٠٠٠ — يعني بلا `duration=first`
    المخرَج بيطول.
    """
    plan = rendered["plan"]
    total_samples = len(S.pcm(rendered["off"]))
    last = sum(plan) - 1
    cue = X.Cue(frame=last, sample=X.frame_to_sample(last, FPS),
                kind="finale", asset="riser", gain=0.22)
    assert cue.sample + S.wav_info(S.asset("riser"))[3] > total_samples, \
        "المؤثر ما بيتعدّى النهاية فالفحص فقد معناه"

    starts = G.start_frames(SEGS, FPS)
    g, maps = G.build_graph(SCFG, plan, starts, [("reel", SCFG)], 320, 568,
                            cues=[cue], sfx_inputs={"riser": 1})
    gp = str(tmp_path / "g.txt")
    open(gp, "w", encoding="utf-8").write(g)
    out = str(tmp_path / "tail.mkv")
    src = os.path.join(os.path.dirname(rendered["off"]), "source.mp4")
    _, v, al = maps[0]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                    "-i", S.asset("riser"), "-filter_complex_script", gp,
                    "-map", f"[{v}]", "-map", f"[{al}]",
                    "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
                    "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", out],
                   check=True, capture_output=True)
    assert len(S.pcm(out)) == total_samples, "المخرَج طوّل — `duration=first` ناقصة"


def test_frame_count_is_unchanged(rendered):
    total = sum(rendered["plan"])
    assert count_frames(rendered["on_mp4"]) == total
    assert count_frames(rendered["off_mp4"]) == total


def test_nothing_clips(rendered):
    """
    الهامش محسوب: كسب الكلام × ذروة المصدر + ٠.٩٠×٠.٢٥ < ١.٠.
    ولا عيّنة مقصوصة — لا بـPCM ولا بعد AAC.
    """
    assert S.clipped(rendered["on"]) == 0
    assert S.peak_of(rendered["on"]) < 0.999


def test_speech_is_preserved_up_to_one_constant_gain(rendered):
    """
    **حارس التزامن البنيوي.**

    برّا نوافذ المؤثرات، كل عيّنة كلام لازم تكون العيّنة الأصلية
    مضروبة بـ**نفس** الثابت. هاد أقوى من "متطابقة": بيثبت إنه ما في
    تشويه، ولا تنفّس كسب، ولا **أي إزاحة زمنية** — إزاحة بعيّنة وحدة
    بتخرّب النسبة فورًا.

    وهاد بالضبط اللي بيفشّل `normalize=1`: هناك النسبة **بتتغيّر مع
    الزمن** (مقيس: ٠.٠٢٠٨ -> ٠.٠٣٥٤ عبر ٥ ثواني).

    العتبة على السعات الكبيرة بس: تكميم ١٦ بت بيخرّب النسب الصغيرة
    (مقيس: مدى ١.٦e−٢ عند |x|>٠.٠٠١ مقابل ٢e−٤ عند |x|>٠.٠٥).
    """
    a, b = S.pcm(rendered["off"]), S.pcm(rendered["on"])
    touched = _touched(rendered["cues"])
    clean = [i for i in range(min(len(a), len(b)))
             if i not in touched and abs(a[i]) > 0.05]
    assert len(clean) > 50, f"عيّنات نظيفة قليلة: {len(clean)}"
    ratios = [b[i] / a[i] for i in clean]
    spread = max(ratios) - min(ratios)
    assert spread < 0.01, \
        f"النسبة مش ثابتة (مدى {spread:.4f}) — تشويه أو تنفّس أو إزاحة"

    # والثابت هو **كسب الكلام المطلوب بالضبط**، مش أي رقم.
    mean = sum(ratios) / len(ratios)
    assert abs(mean - G.DEFAULT_SPEECH_GAIN) < 0.01, \
        f"كسب الكلام {mean:.4f} بدل {G.DEFAULT_SPEECH_GAIN}"


def test_the_speech_level_is_the_same_for_mono_and_stereo_sources(tmp_path):
    """
    **الخيار (أ):** مستوى الكلام الواصل ثابت عند الهدف مهما كان شكل
    المصدر. مقيس على الاتنين عبر نفس المسار: ٠.٦٩٩٩ (مونو) و٠.٧٠٠٠
    (ستيريو).

    ما في تعويض ولا ضرب بـ√٢: الرسم صحيح أصلًا، والفرق اللي ظهر
    بالمرحلة ٤ كان **خلل قياس** — مرجع مونو مقابل مزيج ستيريو.
    """
    if not ffmpeg_available():
        pytest.skip("ffmpeg مش موجود")
    src = build_source(tmp_path, width=320, height=568, fps=FPS, nframes=420)
    stereo = str(tmp_path / "stereo.mkv")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src["path"],
                    "-c:v", "copy", "-af", "pan=stereo|c0=c0|c1=c0",
                    "-c:a", "pcm_s16le", stereo], check=True, capture_output=True)

    plan = C.frame_plan(SEGS, FPS)
    starts = G.start_frames(SEGS, FPS)
    cues = [X.Cue(f, X.frame_to_sample(f, FPS), "caption", "pop", 0.25)
            for f in (40, 120, 200)]
    touched = _touched(cues)

    def one(path, tag):
        outs = {}
        for on in (False, True):
            g, maps = G.build_graph(SCFG, plan, starts, [("reel", SCFG)], 320, 568,
                                    cues=cues if on else None,
                                    sfx_inputs={"pop": 1} if on else None)
            gp = str(tmp_path / f"g_{tag}.txt")
            open(gp, "w", encoding="utf-8").write(g)
            args = ["ffmpeg", "-y", "-loglevel", "error", "-i", path]
            if on:
                args += ["-i", S.asset("pop")]
            _, v, al = maps[0]
            o = str(tmp_path / f"{tag}_{on}.mkv")
            subprocess.run(args + ["-filter_complex_script", gp,
                                   "-map", f"[{v}]", "-map", f"[{al}]",
                                   "-c:v", "libx264", "-crf", "23",
                                   "-preset", "veryfast", "-pix_fmt", "yuv420p",
                                   "-c:a", "pcm_s16le", "-ac", "2", o],
                           check=True, capture_output=True)
            outs[on] = o
        a, b = S.pcm(outs[False]), S.pcm(outs[True])
        clean = [i for i in range(min(len(a), len(b)))
                 if i not in touched and abs(a[i]) > 0.05]
        assert len(clean) > 50
        r = sorted(b[i] / a[i] for i in clean)
        return r[len(r) // 2], S.clipped(outs[True])

    g_mono, clip_mono = one(src["path"], "mono")
    g_stereo, clip_stereo = one(stereo, "stereo")
    target = G.DEFAULT_SPEECH_GAIN
    assert abs(g_mono - target) < 0.01, f"مونو {g_mono:.4f} ≠ {target}"
    assert abs(g_stereo - target) < 0.01, f"ستيريو {g_stereo:.4f} ≠ {target}"
    assert abs(g_mono - g_stereo) < 0.005, \
        f"مونو {g_mono:.4f} وستيريو {g_stereo:.4f} مش نفس المستوى"
    assert clip_mono == 0 and clip_stereo == 0

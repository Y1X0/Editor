"""
اختبارات القبول E1..E8 — **على كود الإنتاج الحالي**.

الهدف بهالمرحلة مش النجاح. الهدف نشوف الفشل المتوقَّع بعينينا قبل ما
نكتب أي إصلاح:

    E1 لازم يفشل   ← CR-4 (إطار زيادة)
    E2 لازم يفشل   ← انزياح AAC المتراكم
    E8 لازم ينجح   ← الزوم لكل مقطع شغّال اليوم

اختبار ما شفناه بيفشل مش اختبار. `test_e1_and_e2_fail_today` تحت بيثبّت
هالشرط: لو صار E1 أو E2 يمرقوا على المعمارية القديمة، الاختبار **هو**
اللي بينكسر — يعني حدا فقّع أسنانهن.

كلها `slow`: ترميز ffmpeg حقيقي.
"""
import math
import os

import pytest
from PIL import Image

from measure import (build_source, click_times, count_frames, extract_frames,
                     ffmpeg_available, measure_scale, read_identities)
from measure.clicks import drift_ms
from measure.identity import identity_report
from measure.pipeline import (flat_captions, run_pipeline, segment_of,
                              shrink_config, write_srt)
from measure.zoom import expected_scale

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود"),
]

FPS = 30
SRC_W, SRC_H = 640, 1138
OUT_W, OUT_H = 540, 960
NF = 600                      # ٢٠ ثانية
NSEG = 8

# النقرات كل ٠.٥s. بنحطّ كل مقطع كلام حوالين نقرة واحدة، والفجوات بين
# المقاطع أكبر بكتير من `cuts.min_gap` فالقص أكيد بيصير.
CLICK_AT = [2.0 + 2.0 * i for i in range(NSEG)]
CUES = [(t - 0.12, t + 0.28, "كلمة تانية تالتة") for t in CLICK_AT]

# عتبات مشتقّة من أرضيات `test_measure_floor.py`، مش مخترعة هون.
DRIFT_MAX_MS = 12.0           # أرضية القياس ٥ms
DRIFT_ACCUM_MS = 12.0
ZOOM_TOL = 0.006              # أرضية القياس ٠.٠٠٤


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    return build_source(tmp_path_factory.mktemp("acc_src"),
                        width=SRC_W, height=SRC_H, fps=FPS, nframes=NF)


@pytest.fixture(scope="module")
def run(src, tmp_path_factory):
    """تشغيلة واحدة بيتقاسموها كل الفحوص — الترميز غالي."""
    d = tmp_path_factory.mktemp("acc_run")
    cfg = shrink_config(d / "config.json", OUT_W, OUT_H)
    srt = write_srt(d / "in.srt", CUES)
    out = d / "out.mp4"
    colors = {}

    def color_of(i):
        # ١٢ درجة × ٣ قنوات، خطوة ٢٠ — نفس منطق هوية الإطار
        c = (30 + (i % 12) * 20, 30 + ((i // 12) % 12) * 20,
             30 + ((i // 144) % 12) * 20)
        colors[i] = c
        return c

    with flat_captions(color_of):
        info = run_pipeline(src["path"], out, cfg, srt=srt, sizes="reel")
    info["out"] = str(out)
    info["colors"] = colors
    assert os.path.exists(info["out"]), "ما انكتب ملف مخرَج"
    return info


@pytest.fixture(scope="module")
def frames_dir(run, tmp_path_factory):
    d = tmp_path_factory.mktemp("acc_frames")
    pngs = extract_frames(run["out"], d)
    assert pngs, "ما انستخرج ولا إطار — لا تقارن على مجموعة فاضية"
    return pngs


def test_scenario_is_what_we_think_it_is(run):
    """
    حارس: لو خطة القص طلعت غير اللي مصمّمين عليه، باقي الفحوص بتقيس
    شيئًا تانيًا وهي ناجحة.
    """
    assert len(run["segs"]) == NSEG, f"توقّعنا {NSEG} مقطع، طلعوا {len(run['segs'])}"
    assert run["fps"] == FPS
    assert all(n >= 3 for n in run["plan"]), "مقطع أقصر من ٣ إطارات — سيناريو ضعيف"
    assert run["caps"], "ما انولد ولا كابشن"


# ============================================================ E1: عدد الإطارات

def test_e1_output_frames_equal_frame_plan(run):
    """
    العقد: طول المخرَج = `Σ frame_plan` بالضبط.

    **بيفشل اليوم**: CR-4 — `burn_captions` بتزيد إطارًا واحدًا.
    """
    got = count_frames(run["out"])
    assert got == run["total"], (
        f"المخرَج {got} إطار والمخطط {run['total']} (فرق {got - run['total']:+d})")


# =========================================================== E7: هوية الإطار

def test_e7_no_frame_is_dropped_or_duplicated(run, frames_dir):
    """
    **أهم فحص بالملف.**

    الإسقاط والتكرار بيلغوا بعض بالعدّ، فـE1 عمياء عنهن بالتعريف.
    هون بنقرا رقم إطار المصدر من كل إطار مخرَج.

    التأكيدات معمارية-محايدة عمدًا: ما بنفرض `round` ولا `ceil` لاختيار
    أول إطار بالمقطع (`-ss` بتاخد أول إطار عند-أو-بعد الزمن، و`select`
    بتاخد `round`) — فرق إطار واحد عند حدّ القطع مش خلل. اللي بنفرضه:
    داخل المقطع الواحد الترقيم بيزيد **واحد بالضبط**، وما في تكرار
    بالمخرَج كله.
    """
    ids = read_identities(frames_dir)
    assert ids.count(None) == 0, f"{ids.count(None)} إطار ما انقرا رقمه"

    seen = [x for x in ids if x is not None]
    assert len(seen) == len(set(seen)), (
        f"{len(seen) - len(set(seen))} إطار مكرر بالمخرَج")

    off, plan = run["offsets"], run["plan"]
    for i in range(len(plan)):
        seg = ids[off[i]:off[i] + plan[i]]
        assert len(seg) == plan[i], f"مقطع {i}: {len(seg)} إطار والمخطط {plan[i]}"
        steps = [seg[j + 1] - seg[j] for j in range(len(seg) - 1)]
        assert all(s == 1 for s in steps), (
            f"مقطع {i}: قفزات غير متتالية {[(j, s) for j, s in enumerate(steps) if s != 1]}")


def test_e7_each_segment_starts_at_its_planned_source_frame(run, frames_dir):
    """
    بداية المقطع لازم تقع على الإطار المقصود ±١ (اتفاقية الـseek).
    انحراف أكبر يعني الخطة والمخرَج بيتكلّموا عن مقاطع مختلفة.
    """
    ids = read_identities(frames_dir)
    off = run["offsets"]
    bad = []
    for i, (a, _) in enumerate(run["segs"]):
        want = round(a * run["fps"])
        got = ids[off[i]]
        if got is None or abs(got - want) > 1:
            bad.append((i, want, got))
    assert not bad, f"بدايات مقاطع بعيدة عن الخطة: {bad}"


# =============================================================== E2: الصوت

def test_e2_audio_has_no_cumulative_drift(run):
    """
    نقرة معروفة بكل مقطع. مكانها بالمخرَج بينحسب من خطة الإطارات.

    **بيفشل اليوم**: كل مقطع بينرمّز AAC لحاله وbpriming padding
    بيتراكم — مقاس ≈٥.٤ms لكل قطعة.
    """
    got = click_times(run["out"])
    want = []
    for i, (a, _) in enumerate(run["segs"]):
        # النقرة بتقع بالمصدر عند CLICK_AT[i]، وبداية المقطع a
        want.append(run["offsets"][i] / run["fps"] + (CLICK_AT[i] - a))
    assert len(got) == len(want), f"لقينا {len(got)} نقرة والمتوقَّع {len(want)}"
    errs = drift_ms(got, want)
    assert max(abs(e) for e in errs) <= DRIFT_MAX_MS, (
        f"أقصى انزياح {max(abs(e) for e in errs):.1f}ms · {[round(e, 1) for e in errs]}")
    assert abs(errs[-1] - errs[0]) <= DRIFT_ACCUM_MS, (
        f"تراكم {errs[-1] - errs[0]:+.1f}ms من أول نقرة لآخر وحدة — "
        f"هاد انزياح بيكبر مع طول الريل")


# ========================================================== E3: توقيت الكابشن

def _caption_at(png, run):
    """رقم الكابشن الظاهر بإطار — من لون الرقعة المصمتة."""
    img = Image.open(png).convert("RGB")
    y = int(OUT_H * 0.72)
    c = img.getpixel((OUT_W // 2, y))
    best, bd = None, 10 ** 9
    for i, ref in run["colors"].items():
        d = max(abs(p - q) for p, q in zip(c, ref))
        if d < bd:
            best, bd = i, d
    return best if bd <= 9 else None


def test_e3_every_caption_starts_on_its_planned_frame(run, frames_dir):
    """
    كل كابشن لازم يظهر أول مرة عند `round(start * fps)` بالضبط.
    """
    obs = [_caption_at(p, run) for p in frames_dir]
    assert any(x is not None for x in obs), "ولا كابشن انكشف — الفحص فاضي"
    first = {}
    for n, c in enumerate(obs):
        if c is not None:
            first.setdefault(c, n)
    bad = []
    for i, (_, s, _e) in enumerate(run["caps"]):
        want = round(s * run["fps"])
        if first.get(i) != want:
            bad.append((i, want, first.get(i)))
    assert not bad, f"{len(bad)} كابشن مش على إطاره: {bad[:6]}"


def test_e3_captions_never_overlap_and_keep_their_order(run, frames_dir):
    """
    كابشنان بنفس الإطار = واحد بيغطي التاني. وترتيب غير تصاعدي يعني
    كابشن رجع بعد ما راح.
    """
    obs = [c for c in (_caption_at(p, run) for p in frames_dir) if c is not None]
    assert obs, "ولا كابشن انكشف"
    runs = [obs[0]]
    for c in obs[1:]:
        if c != runs[-1]:
            runs.append(c)
    assert runs == sorted(set(runs), key=runs.index), "الترتيب اتكسر"
    assert len(runs) == len(set(runs)), "كابشن ظهر على دفعتين متفرّقتين"


# ================================================================ E8: الزوم

def _zoom_cycle():
    import json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config.json"), encoding="utf-8") as f:
        return json.load(f)["motion"]["zoom_cycle"]


@pytest.fixture(scope="module")
def observed_bounds(run, frames_dir):
    """
    حدود المقاطع كما ظهرت **فعلًا** بالمخرَج، مأخوذة من قفزات رقم إطار
    المصدر.

    ليش مش `run["offsets"]`؟ لأن E8 اختبار **زوم**، وخلطه بتخطيط
    الإطارات بيخلّيه يفشل لأسباب مالها علاقة فيه — واليوم فعلًا في
    إزاحة تراكمية (CR-5) بتحرّك الحدود عن الخطة. الفصل بيخلّي فشل E8
    يعني "الزوم غلط" وبس، وE1/E7 هنّ اللي بيمسكوا التخطيط.

    التعيين للمقاطع بيضل مربوطًا بالترتيب، فزوم منسوب لمقطع غلط
    بينمسك عادي.
    """
    ids = read_identities(frames_dir)
    assert ids.count(None) == 0, "إطار ما انقرا رقمه — الحدود مش موثوقة"
    starts = [0] + [i for i in range(1, len(ids)) if ids[i] - ids[i - 1] not in (0, 1)]
    nseg = len(run["plan"])
    assert len(starts) == nseg, (
        f"لقينا {len(starts)} حدّ والمقاطع {nseg} — السيناريو مش اللي منظنّه")
    ends = starts[1:] + [len(ids)]
    return list(zip(starts, ends))


def test_e8_zoom_matches_the_cycle_on_every_segment(run, frames_dir, observed_bounds):
    """
    الزوم لكل مقطع شغّال اليوم — فهاد **لازم ينجح** على الكود الحالي،
    ولازم يضل ناجحًا بعد إعادة التصميم. هو حارس الانحدار الوحيد على
    `motion.zoom_cycle`.
    """
    cycle = _zoom_cycle()
    bad = []
    for i, (a, b) in enumerate(observed_bounds):
        got = measure_scale(frames_dir[(a + b) // 2])
        want = expected_scale(SRC_W, SRC_H, OUT_W, OUT_H, cycle[i % len(cycle)])
        if abs(got - want) > ZOOM_TOL:
            bad.append((i, cycle[i % len(cycle)], round(want, 4), round(got, 4)))
    assert not bad, f"زوم مش مطابق: {bad}"


def test_e8_zoom_changes_exactly_at_the_segment_boundary(run, frames_dir,
                                                        observed_bounds):
    """آخر إطار بالمقطع بزومه، وأول إطار باللي بعده بزوم اللي بعده."""
    cycle = _zoom_cycle()
    bad = []
    for i in range(len(observed_bounds) - 1):
        z0, z1 = cycle[i % len(cycle)], cycle[(i + 1) % len(cycle)]
        if z0 == z1:
            continue
        last = observed_bounds[i][1] - 1
        first = observed_bounds[i + 1][0]
        w0 = expected_scale(SRC_W, SRC_H, OUT_W, OUT_H, z0)
        w1 = expected_scale(SRC_W, SRC_H, OUT_W, OUT_H, z1)
        if (abs(measure_scale(frames_dir[last]) - w0) > ZOOM_TOL
                or abs(measure_scale(frames_dir[first]) - w1) > ZOOM_TOL):
            bad.append(i)
    assert not bad, f"الزوم ما تبدّل عند الحدّ بالمقاطع {bad}"


def test_e8_uses_more_than_one_zoom_value(run, observed_bounds):
    """حارس: `zoom_cycle` بقيمة وحدة بيخلّي E8 يمرق بلا ما يفحص شي."""
    cycle = _zoom_cycle()
    used = {cycle[i % len(cycle)] for i in range(len(observed_bounds))}
    assert len(used) >= 2, f"السيناريو استعمل زومًا واحدًا فقط: {used}"


# ========================================= E4/E5: الملفات الوسيطة ودلالات الفشل

def test_e4_no_intermediate_video_files_survive_a_successful_run(src, tmp_path):
    """
    مجلد العمل بينمسح بالنجاح. الفحص هون على **مجلد المخرَج**: ما بيصير
    يضل جنبه ولا ملف تمريرة.
    """
    cfg = shrink_config(tmp_path / "config.json", OUT_W, OUT_H)
    srt = write_srt(tmp_path / "in.srt", CUES)
    outdir = tmp_path / "out"
    outdir.mkdir()
    with flat_captions(lambda i: (200, 40, 40)):
        run_pipeline(src["path"], outdir / "r.mp4", cfg, srt=srt, sizes="reel")
    left = sorted(p for p in os.listdir(outdir) if p != "r.mp4")
    assert left == [], f"ملفات وسيطة ضلّت: {left}"


def test_e5_a_failed_size_does_not_leave_a_playable_looking_output(src, tmp_path):
    """
    فشل مقاس لازم يبيّن: كود خروج ≠ ٠، وما بيضل ملف بشكل مخرَج سليم.

    بنفشّله بمقاس ما بيسع الكابشن — `assert_fits_frame` بترفع قبل
    الترميز، وهاد المسار المقصود.
    """
    cfg = shrink_config(tmp_path / "config.json", 200, 120)
    srt = write_srt(tmp_path / "in.srt", CUES)
    out = tmp_path / "bad.mp4"
    with flat_captions(lambda i: (200, 40, 40)):
        info = run_pipeline(src["path"], out, cfg, srt=srt, sizes="reel")
    assert info["rc"] != 0, "المقاس فشل بس كود الخروج طلع صفر"
    assert not os.path.exists(out), "ضلّ ملف بشكل مخرَج بعد الفشل"


# ================================================== حارس: حالة الانطلاق

def test_the_baseline_really_is_broken_in_the_ways_we_claim(run, frames_dir):
    """
    **بيوثّق الحالة اللي بنبلّش منها، وبيحرس أسنان الفحوص.**

    كل تأكيد هون بيقول "هالخلل موجود اليوم". لو صار واحد منهن يفشل،
    السبب إما إن الخلل انصلّح (وقتها احذف سطره عن قصد وخلّي الاختبار
    الأصلي يحرسه) أو إن الفحص المقابل فقد أسنانه — والتاني بيمرق بصمت
    وهو الأخطر.
    """
    # CR-4: إطار زيادة على الخطة
    got = count_frames(run["out"])
    assert got != run["total"], (
        f"E1 مرق على الكود القديم ({got}={run['total']}) — CR-4 انصلّح أو "
        f"الفحص فقد أسنانه")

    # CR-5: أول إطار بكل مقطع مكرر (والمقطع بيعرض إطارًا أقل من الخطة)
    ids = read_identities(frames_dir)
    dups = [i for i in range(1, len(ids)) if ids[i] == ids[i - 1]]
    assert dups, "E7 مرق على الكود القديم — CR-5 انصلّح أو الفحص فقد أسنانه"

    # الانزياح الصوتي المتراكم
    clicks = click_times(run["out"])
    want = [run["offsets"][i] / run["fps"] + (CLICK_AT[i] - a)
            for i, (a, _) in enumerate(run["segs"])]
    assert len(clicks) == len(want), "عدد النقرات اتغيّر — السيناريو انكسر"
    errs = drift_ms(clicks, want)
    assert abs(errs[-1] - errs[0]) > DRIFT_ACCUM_MS, (
        f"E2 مرق على الكود القديم (تراكم {errs[-1]-errs[0]:+.1f}ms) — "
        f"الانزياح انصلّح أو الفحص فقد أسنانه")


def test_cr5_first_frame_of_every_segment_is_duplicated(run, frames_dir,
                                                        observed_bounds):
    """
    توصيف دقيق لـCR-5 عشان يكون قابلًا للمقارنة بعد الإصلاح.

    كل مقطع بينرمّز بـ`-ss {a:.3f}` وزمن `a` مش على شبكة الإطارات، فأول
    إطار بينكرّر والمقطع بيعرض إطارًا **أقل** من محتواه المخطَّط.
    مقاس: seek على الشبكة (54/30) بيعطي ١٨ إطارًا مميّزًا، وseek برّاها
    (1.780) بيعطي ١٧ مميّز + تكرار.

    **العدّ أعمى عن هالخلل**: `-frames:v n` بيضمن العدد مهما تكرّر
    المحتوى. E7 وحده بيمسكه.
    """
    ids = read_identities(frames_dir)
    per_seg = []
    for a, b in observed_bounds:
        seg = ids[a:b]
        per_seg.append((len(seg), len(set(seg))))
    assert all(d < n for n, d in per_seg), (
        f"توقّعنا تكرارًا بكل مقطع، لقينا {per_seg}")

"""جهاز القياس — **بيطبع ولا بيحكم، وما بيعرّف مقياسًا**.

الأداة انكتبت بعد ما البروتوكول انعتمد، وتنفيذها لازم يكون حرفيًا:
ولا metric جديدة، ولا حكم better/worse، ولا تعويض عن مدخل ناقص.
"""
import pathlib
import subprocess
import sys

import pytest

from ai_pipeline.edit.pacing import MIN_CV, _cv
from ai_pipeline.edit.plan import trivial_plan
from ai_pipeline.edit.repetition import MAX_ASSET_SHARE
from ai_pipeline.timeline.quantize import quantize

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
from measure_edit import PLAN_ONLY, TIMELINE_ONLY, measure  # noqa: E402

TOOL = pathlib.Path("tools/measure_edit.py")


@pytest.fixture
def contracts(tmp_path, output, segments, alignment, assets, audio_duration):
    tl = quantize(output, segments, alignment, assets, audio_duration)
    (tmp_path / "timeline.json").write_text(tl.model_dump_json(), encoding="utf-8")
    (tmp_path / "segments.json").write_text(segments.model_dump_json(),
                                            encoding="utf-8")
    (tmp_path / "assets.json").write_text(assets.model_dump_json(), encoding="utf-8")
    return tmp_path


@pytest.fixture
def dirty(tmp_path):
    """**fixture بمخالفات مقصودة.**

    الـfixture النظيفة ما بتغطّي مسارين: تراكم حصّة الأصل (كل مقطع
    بيظهر مرة وحدة فالجمع ما بينختبر) وترتيب المخالفات (ما في ولا
    مخالفة فالترتيب بلا معنى). طفرتان نجتا لهالسبب بالضبط — نفس شكل
    الحادثة الموثّقة بـ`ai_pipeline/CLAUDE.md`.

    فهون مقطع ١ بيظهر بتلات مواضع غير متجاورة (٩٠٪ من الزمن)،
    ومقطعان قصيران تحت الحدّ.
    """
    from ai_pipeline.models.timeline import Span, Timeline

    tl = Timeline(
        fps=30, sample_rate=48000, total_frames=300,
        visual_spans=(Span(segment_id=1, f_start=0, f_end=90),
                      Span(segment_id=2, f_start=90, f_end=105),
                      Span(segment_id=1, f_start=105, f_end=195),
                      Span(segment_id=3, f_start=195, f_end=210),
                      Span(segment_id=1, f_start=210, f_end=300)),
        text_spans=(Span(segment_id=1, f_start=10, f_end=90),
                    Span(segment_id=2, f_start=90, f_end=195),
                    Span(segment_id=3, f_start=195, f_end=300)),
        asset_in_frame={1: 0, 2: 0, 3: 0})
    (tmp_path / "timeline.json").write_text(tl.model_dump_json(), encoding="utf-8")

    # وخطة مطابقة للخمس لقطات — بلاها `check_pacing` ما بتنشتغل أصلًا
    # وبيضل عنا مخالفتان بس، فترتيب المخالفات ما بينختبر.
    import json
    plan = {"beats": [{"beat_id": 1, "segment_ids": [1], "role": "hook"},
                      {"beat_id": 2, "segment_ids": [2], "role": "turn"},
                      {"beat_id": 3, "segment_ids": [3], "role": "payoff"}],
            "shots": [{"shot_id": 1, "beat_id": 1, "order": 0},
                      {"shot_id": 2, "beat_id": 1, "order": 1},
                      {"shot_id": 3, "beat_id": 1, "order": 2},
                      {"shot_id": 4, "beat_id": 2, "order": 0},
                      {"shot_id": 5, "beat_id": 3, "order": 0}]}
    (tmp_path / "edit_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return tmp_path


def test_the_share_accumulates_across_non_adjacent_spans(dirty):
    """**طفرة نجت لولا هالفحص.**

    `share[sid] = n` بدل `share[sid] += n` بتعطي ٣٠٪ بدل ٩٠٪ —
    تحت الحدّ، فالحارس ما بيشتغل والأداة بتطبع رقمًا مطمئنًا غلط.
    والـfixture النظيفة ما بتمسكها لأن كل مقطع فيها بيظهر مرة وحدة.
    """
    text = measure(dirty)
    assert "90.0%" in text, "الحصّة ما بتتراكم عبر المواضع"
    assert "asset_dominance" in text


def test_the_violations_come_out_sorted(dirty):
    """ترتيب متغيّر بيخلّي `diff` بين تشغيلتين ضجيجًا — و`metrics.txt`
    بينحفظ ليتقارن، فالترتيب جزء من العقد لا تجميلًا."""
    lines = [l[2:] for l in measure(dirty).splitlines() if l.startswith("✗ ")]
    assert len(lines) >= 3, f"الـfixture بتعطي {len(lines)} مخالفة — بلا أسنان"
    rules = [l.split(":")[0] for l in lines]
    assert rules == sorted(rules), f"مش مرتّبة: {rules}"


# ══ الحدّ: ولا حكم ══════════════════════════════════════════════════
def test_the_tool_never_renders_a_verdict():
    """**البند اللي المالك ثبّته صراحةً:** الأداة بتطبع القياسات
    والمخالفات فقط، والحكم الإبداعي خارجها بالكامل.

    الحارس على المصدر لا على المخرَج: مخرَج تشغيلة وحدة ممكن ما يحوي
    الكلمة صدفةً، والمصدر بيحويها للأبد.
    """
    import ast

    tree = ast.parse(TOOL.read_text(encoding="utf-8"))

    # **الحارس على النصوص المنبعثة، لا على الشرح.** أول صياغة مسحت
    # المصدر كله ففشلت على الـdocstring اللي **بتمنع** الحكم — الحارس
    # كان بيتّهم التوثيق. فبنشيل الـdocstrings وبنفحص الباقي.
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            d = ast.get_docstring(n, clean=False)
            if d:
                docs.add(d)

    emitted = [n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and n.value not in docs]
    assert emitted, "ما في نصوص — الحارس بلا أسنان"

    for s in emitted:
        for word in ("better", "worse", "improve", "regress", "verdict",
                     "أحسن", "أسوأ", "تحسّن", "تراجع", "نجح", "فشل"):
            assert word not in s, f"الأداة بتحكم: {word!r} بـ{s!r}"


def test_the_output_carries_no_score(contracts):
    """ولا رقم مجمّع كمان — `visual_score = 82` بلبوس تقرير."""
    text = measure(contracts)
    # `%)` كان بالقائمة أول مرة وفشل على «الحدّ 35%)» — وهاد **حدّ
    # معلَن** لا مجموعًا. الاستدلال بالشكل كان غلط، فانشال.
    for word in ("score", "درجة", "المجموع", "الإجمالي", "/100"):
        assert word not in text, f"مجموع بالمخرَج: {word!r}"


# ══ الحدّ: ولا مقياس جديد ═══════════════════════════════════════════
def test_the_tool_reuses_the_checkers_it_does_not_redefine_them():
    """**تعريف تاني بيفترق بصمت** — أكتر شكل تكرّر بهالمستودع.

    فالأداة بتستورد `_cv` و`asset_runs` و`hard_guards` و`check_pacing`،
    وما بتعيد كتابة ولا وحدة. الحارس على الاستيراد: لو انكتبت
    `_cv` محليًّا، الاستيراد بيختفي وهاد بينمسك.
    """
    src = TOOL.read_text(encoding="utf-8")
    for name in ("_cv", "check_pacing", "hard_guards", "asset_runs"):
        assert f"import" in src and name in src, name
    assert "def _cv" not in src, "الأداة أعادت تعريف `_cv`"
    assert "def check_pacing" not in src
    assert "def hard_guards" not in src


def test_the_cv_the_tool_prints_is_the_checkers_cv(contracts, output, segments,
                                                   alignment, assets,
                                                   audio_duration):
    """ربط الرقمين: اللي بتطبعه الأداة هو اللي القاعدة بتحكم عليه."""
    tl = quantize(output, segments, alignment, assets, audio_duration)
    want = _cv([s.n_frames for s in tl.visual_spans])
    assert f"{want:.3f}" in measure(contracts)


def test_the_share_the_tool_prints_agrees_with_the_guard_at_the_boundary(
        contracts):
    """وحصّة الأصل كمان: الأداة بتحسبها، والحارس بيقرّر عليها.

    الفحص بيربطهما: إذا الأداة طبعت حصّة فوق الحدّ، لازم يكون في
    `asset_dominance` بالمخالفات — وإذا طبعت تحتها، ما بيكون في.
    """
    text = measure(contracts)
    line = next(l for l in text.splitlines() if "أعلى حصّة أصل" in l)
    pct = float(line.split("%")[0].split()[-1])
    fired = "asset_dominance" in text
    assert fired == (pct > MAX_ASSET_SHARE * 100), \
        f"الحصّة {pct}% والحارس {'اشتغل' if fired else 'ما اشتغل'}"


# ══ الحدّ: ما بتعوّض عن مدخل ناقص ═══════════════════════════════════
def test_without_a_plan_the_plan_rules_are_reported_unmeasured_not_passed(
        contracts):
    """**ولا تعويض بـ`trivial_plan`.**

    الافتراضيات بتخلّي الـbaseline يبيّن نظيفًا **بالبناء**:
    `motion` افتراضيها `static` فـ`static_share` بتمرق بـ١٠٠٪ و
    `motion_dominance` ما بتلاقي شي؛ وبلا cues `cue_density` بتسكت؛
    وبطاقة موحّدة `energy_slump` بتسكت. خمس قواعد بتمرق مجّانًا.

    فغياب القياس بينعلن **كغياب**، لا كنجاح.
    """
    text = measure(contracts)
    assert "غير مقيس" in text
    for rule in PLAN_ONLY:
        assert f"? {rule}" in text
    assert "ولا مخالفة" not in text or "غير مقيس" in text


def test_the_trivial_plan_would_have_faked_five_clean_rules(
        output, segments, alignment, assets, audio_duration):
    """**إثبات الخطر، لا ادّعاؤه.**

    بنبني الخطة التافهة ونمرّرها على `check_pacing` ونتأكد إنها فعلًا
    بتمرّ نظيفة على الخمسة — فقرار «لا تعويض» مبني على قياس.
    """
    from ai_pipeline.edit.pacing import check_pacing

    tl = quantize(output, segments, alignment, assets, audio_duration)
    got = {v.rule for v in check_pacing(trivial_plan(segments), tl)}
    assert not (got & set(PLAN_ONLY)), \
        f"التعويض كان بيبلّغ عن {sorted(got & set(PLAN_ONLY))} — الحجّة أضعف"


def test_with_a_plan_the_plan_rules_are_actually_evaluated(
        contracts, output, segments, alignment, assets, audio_duration):
    """والوجه التاني: مع خطة، القواعد الخمسة **بتنقاس فعلًا**."""
    plan = trivial_plan(segments)
    (contracts / "edit_plan.json").write_text(plan.model_dump_json(),
                                              encoding="utf-8")
    text = measure(contracts)
    assert "غير مقيس" not in text
    assert "خطة تحرير             موجودة" in text


def test_the_two_rule_groups_together_are_the_whole_pacing_set():
    """لو انضافت قاعدة إيقاع جديدة ونُسيت هون، بتوقع برّا التصنيف."""
    import ai_pipeline.edit.pacing as P

    src = pathlib.Path(P.__file__).read_text(encoding="utf-8")
    rules = {l.split('"')[1] for l in src.splitlines()
             if "Violation(" in l and '"' in l}
    rules |= {l.strip().strip('",') for l in src.splitlines()
              if l.strip().startswith('"') and l.strip().endswith('",')
              and "_" in l}
    known = set(TIMELINE_ONLY) | set(PLAN_ONLY)
    missing = {r for r in rules if "_" in r and r.islower()} - known
    assert not missing, f"قواعد إيقاع مش مصنَّفة بالأداة: {sorted(missing)}"


# ══ التشغيل الحقيقي ═════════════════════════════════════════════════
def test_the_tool_runs_from_the_command_line(contracts):
    r = subprocess.run([sys.executable, str(TOOL), str(contracts)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "── قياسات" in r.stdout


def test_the_report_is_deterministic(contracts):
    """مخرَج متغيّر بيخلّي كل مقارنة بين تشغيلتين ضجيجًا."""
    assert measure(contracts) == measure(contracts)

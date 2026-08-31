"""Creative Checks — **مخالفات بدليل، وولا درجة مجمّعة**."""
import ast
import pathlib

from ai_pipeline.edit import BeatProposal, EditPlan, ShotProposal
from ai_pipeline.edit.critic import creative_checks, report
from ai_pipeline.edit.pacing import Violation
from ai_pipeline.models.timeline import Span, Timeline


def tl(spec, in_frame=None):
    acc, spans = 0, []
    for sid, n in spec:
        spans.append(Span(segment_id=sid, f_start=acc, f_end=acc + n))
        acc += n
    return Timeline(fps=30, sample_rate=48000, total_frames=acc,
                    visual_spans=tuple(spans),
                    text_spans=(Span(segment_id=spec[0][0], f_start=0, f_end=acc),),
                    asset_in_frame=in_frame or {sid: 0 for sid, _ in spec})


def plan(motions):
    n = len(motions)
    return EditPlan(
        beats=tuple(BeatProposal(beat_id=i + 1, segment_ids=(i + 1,),
                                 role="demonstration") for i in range(n)),
        shots=tuple(ShotProposal(shot_id=i + 1, beat_id=i + 1, order=0,
                                 motion=motions[i]) for i in range(n)))


def test_it_gathers_pacing_and_repetition_together():
    """مصدران، مخرَج واحد — القارئ ما بيلزمه ينادي فاحصين."""
    v = creative_checks(plan(["push"] * 4), tl([(1, 200), (2, 20), (3, 20), (4, 20)]))
    r = {x.rule for x in v}
    assert "motion_dominance" in r          # من الإيقاع
    assert "asset_dominance" in r           # من التكرار


def test_the_order_is_stable():
    """ترتيب متغيّر بيخلّي كل مقارنة بين تشغيلتين ضجيجًا."""
    p, t = plan(["push"] * 4), tl([(1, 200), (2, 20), (3, 20), (4, 20)])
    a = [str(x) for x in creative_checks(p, t)]
    b = [str(x) for x in creative_checks(p, t)]
    assert a == b == sorted(a)


def test_a_clean_plan_reports_nothing():
    """**الـfixture موزونة بحساب، لا بالحدس.**

    أول كتابة أعطت المقطع الثالث 100 من 255 إطارًا = 39٪، فضربها
    `asset_dominance` — والحارس كان محقًّا. الأرقام هون مضبوطة على
    كل القيود سوا: أقصى أصل 31٪ · CV 0.29 · السكون 55٪ · أقصر لقطة
    1.17s · أطولها 2.67s.
    """
    v = creative_checks(plan(["static", "push", "static", "drift"]),
                        tl([(1, 60), (2, 35), (3, 80), (4, 80)]))
    assert v == [], [str(x) for x in v]
    assert report(v).startswith("✓")


def test_the_report_names_the_rule_and_the_evidence():
    v = creative_checks(plan(["push"] * 4), tl([(1, 200), (2, 20), (3, 20), (4, 20)]))
    text = report(v)
    assert "motion_dominance" in text and "%" in text
    assert all(line.startswith("✗") for line in text.splitlines())


# ══════════ الحارس على «ولا درجة مجمّعة» ═══════════════════════════
def test_no_aggregate_score_anywhere_in_the_creative_layer():
    """**ممنوع `visual_score: 82` — بقرار، وعلى شجرة الكود.**

    الرقم المجمّع بيدّعي إنه قاس وهو حكم بلبوس رقم، وبيوقف السؤال بدل
    ما يفتحه. الحارس بيمشي على **أسماء الأسماء** بكل ملفات الطبقة —
    فما بيكفي إن ما حدا كتبها اليوم.
    """
    banned = {"visual_score", "pacing_score", "caption_score", "hook_score",
              "shot_variety", "overall_score", "creative_score", "score"}
    for f in sorted(pathlib.Path("ai_pipeline/edit").glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.arg):
                name = node.arg
            if name and name.lower() in banned:
                raise AssertionError(f"{f.name}: درجة مجمّعة `{name}`")


def test_a_violation_has_no_numeric_verdict_field():
    fields = set(Violation.__dataclass_fields__)
    assert fields == {"rule", "detail", "where"}, fields

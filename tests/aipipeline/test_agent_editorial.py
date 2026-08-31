"""Agent 4 — النيّة التحريرية. **الفحص على الحدود، لا على الذوق.**

الحدّ اللي هالملف بيحرسه: الوكيل بيقول **كيف ينقصّ**، والكود بيحسب
**إيمتى**. فأي حقل زمني أو مسار بمخرَجه لازم يفشل، والخطة اللي ما
بتغطّي المقاطع لازم تفشل، والعلم المطفي لازم يعطي **نفس** الـtimeline
اللي كان.
"""
import pathlib

import pytest

from ai_pipeline.agents import editorial as editorial_agent
from ai_pipeline.agents.providers.recorded import RecordedClient
from ai_pipeline.agents.runner import AgentHarness
from ai_pipeline.edit.compiler import compile_plan
from ai_pipeline.edit.plan import EditPlan, trivial_plan
from ai_pipeline.errors import AgentError
from ai_pipeline.timeline.quantize import quantize

FIX = pathlib.Path(__file__).parent / "fixtures/llm"


def agent(case, segments):
    c = RecordedClient(FIX, case)
    return editorial_agent.run(c, segments, harness=AgentHarness(c))


# ── الحالة السليمة ───────────────────────────────────────────────────
def test_a_recorded_plan_becomes_an_edit_plan(segments):
    plan = agent("ok_three_segments", segments)
    assert isinstance(plan, EditPlan)
    assert len(plan.beats) == 2 and len(plan.shots) == 4
    # **٤ لقطات على ٣ مقاطع** — هون بيبان إن الفصل شغّال فعلًا: العدد
    # ما بيقدر يطلع من مسار «لقطة لكل مقطع».
    assert len(plan.shots) != len(segments.segments)


def test_the_plan_compiles_into_more_shots_than_segments(
        segments, alignment, assets, output, audio_duration):
    """الدليل النهائي: **الـtimeline نفسه** فيه لقطات أكتر من المقاطع."""
    tl = compile_plan(agent("ok_three_segments", segments), output, segments,
                      alignment, assets, audio_duration)
    assert len(tl.visual_spans) == 4
    assert len(tl.text_spans) == 3
    assert tl.visual_spans[-1].f_end == tl.total_frames


def test_the_agent_never_sees_the_source_text(segments):
    """`word_index` نسبي، فعدد الكلمات بيكفّي. تمرير النصّ بيعطي
    الوكيل مادةً يقدر يعيد كتابتها — وهاد مقفول بالمشروع."""
    block = editorial_agent.constraints_block(segments)
    for s in segments.segments:
        assert s.text_arabic not in block
        assert f"{s.segment_id}\t{s.word_end - s.word_start}\t" in block


# ── الحالات الخاطئة ──────────────────────────────────────────────────
@pytest.mark.parametrize("case", [
    "bad_missing_segment",      # مقطع ٣ بلا beat
    "bad_invented_segment",     # beat بيشير لمقطع ٩
    "bad_timestamp_field",      # `duration` — حقل زمني ممنوع
    "bad_file_path",            # `file_path` — مسار ممنوع
    "bad_enum_value",           # `role: montage` برّا المفردات
    "bad_shot_order_gap",       # ترتيب 0 ثم 2
])
def test_every_bad_plan_fails_closed(case, segments):
    """**بيفشل، ما بينهبط.** ولا حالة منهن بتطلّع خطة ناقصة."""
    with pytest.raises(AgentError):
        agent(case, segments)


def test_a_timestamp_is_rejected_by_name_not_by_type(segments):
    """`duration: 2.5` ممنوعة **كاسم**، مش لأن نوعها غلط.

    الفرق مهم: لو الرفض بالنوع، `duration: "قصير"` كانت بتمرق وبتزرع
    قرارًا زمنيًا بخطة ما إلها الحق تحمله.
    """
    with pytest.raises(AgentError) as e:
        agent("bad_timestamp_field", segments)
    assert "duration" in str(e.value)


# ── العلم المطفي ─────────────────────────────────────────────────────
def test_the_trivial_plan_still_reproduces_the_old_timeline(
        segments, alignment, assets, output, audio_duration):
    """**بوابة الترحيل.** المسار الجديد بالخطة التافهة = المسار القديم.

    لو اختلف بايت، الترحيل غلط قبل ما نضيف أي ذكاء — فهالفحص بيمشي
    مع كل تعديل على المترجم لا مرة وحدة عند كتابته.
    """
    old = quantize(output, segments, alignment, assets, audio_duration)
    new = compile_plan(trivial_plan(segments), output, segments, alignment,
                       assets, audio_duration)
    assert new.model_dump_json() == old.model_dump_json()


def test_the_flag_is_off_by_default():
    """تشغيله بيغيّر خطة اللقطات لكل مشروع موجود — فالافتراضي المسار
    المقيس، زي `--sfx` بالمحرر وبنفس السبب."""
    from ai_pipeline.cli import build_parser
    a = build_parser().parse_args([
        "--audio", "a.mp3", "--script", "s.txt", "--srt", "s.srt",
        "--catalog", "c.json", "--recorded", "f/", "-o", "o.mp4"])
    assert a.editorial is False
    assert build_parser().parse_args([
        "--audio", "a.mp3", "--script", "s.txt", "--srt", "s.srt",
        "--catalog", "c.json", "--recorded", "f/", "-o", "o.mp4",
        "--editorial"]).editorial is True
    # `--no-editorial` بتغلب حتى لو انطلب — نفس نمط `--no-sfx`
    assert build_parser().parse_args([
        "--audio", "a.mp3", "--script", "s.txt", "--srt", "s.srt",
        "--catalog", "c.json", "--recorded", "f/", "-o", "o.mp4",
        "--editorial", "--no-editorial"]).editorial is False


# ── انجراف الـprompt عن الـschema ────────────────────────────────────
def test_the_prompt_example_actually_validates():
    """**الحادثة اللي ولّدت هالفحص:** الـprompt أول ما انكتب علّم
    مفردات مش موجودة — `energy: "rising"` و`shot_count: "two"` و
    `pace: "quick"` و`intent: "support"`. الـschema رفضتها، بس
    الرفض بيصير **بعد** نداء النموذج: يعني تشغيلة كاملة بتضيع على
    مفردة الـprompt نفسه علّمها.

    فالمثال بالـprompt لازم يمرق على `EditPlan` زي أي جواب. الانجراف
    بين النصّ والـschema بينمسك هون، بلا نداء ولا شبكة.
    """
    import re

    md = (pathlib.Path("ai_pipeline/agents/prompts/editorial/v1.md")
          .read_text(encoding="utf-8"))
    block = re.search(r"```\n(\{.*?\})\n```", md, re.S)
    assert block, "ما في مثال JSON بالـprompt — الفحص بلا أسنان"
    # **`model_validate_json` لا `model_validate`** — هاد مدخل الإنتاج.
    # الوضع الصارم بيرفض `list` مكان `tuple` بالبايثون المباشر، فالفحص
    # بالمدخل التاني كان بيفشل على مثال سليم ويخبّي الانجراف الحقيقي.
    EditPlan.model_validate_json(block.group(1))


def test_every_closed_vocabulary_the_prompt_lists_is_the_real_one():
    """والقوائم اللي تحت المثال كمان: قيمة بتنذكر وما بتنقبل بتكذب."""
    import ai_pipeline.edit.plan as P

    md = (pathlib.Path("ai_pipeline/agents/prompts/editorial/v1.md")
          .read_text(encoding="utf-8"))
    for name in ("BeatRole", "Importance", "Energy", "ShotCount", "Pace",
                 "ShotWeight", "ShotIntent", "MotionIntent",
                 "TransitionIntent", "Continuity", "EmphasisLevel",
                 "CueAnchor", "CueKind", "CueWeight"):
        for value in getattr(P, name).__args__:
            assert f"`{value}`" in md, f"{name}: {value!r} مش مذكورة بالـprompt"

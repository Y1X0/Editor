"""النافذة البصرية لكل مقطع — **بسؤال السلطة، لا بإعادة تعريفها**.

الـResolver بيلزمه يعرف كم لازم تكون مدة كل لقطة قبل ما يختار أصلًا.
والمدة **مش مدة النطق**: نافذة المقطع البصرية بتمتد من القطع اللي قبله
للقطع اللي بعده، فهي أطول من نافذة نصّه — المقطع الأول بيبلّش من الإطار
صفر مهما تأخّر الكلام، والأخير بيمتد لآخر الشريط.

    alignment.json ──► quantize ──► الـspans البصرية ──► المدة المطلوبة
                                                          ──► Resolver

**ليش بننادي `quantize` بدل ما نحسب القاعدة هون:** القاعدة موجودة
هناك (`cuts = [0] + بدايات النصوص + total_frames`)، وأي نسخة تانية منها
بتفترق عنها بصمت بعد أول تعديل. وهاد بالضبط الخلل اللي هالمستودع
بيعاقب عليه — `motion.pan_px` انفصلت عن قارئها وصار الـpan صفرًا،
و١٩٠ فحص هندسة ما مسكوها لأن كلهن بيبنوا نسخة خاصة فيهن.

فبنمرّر لـ`quantize` **أصولًا استقصائية** مدّتها تغطّي الشريط كله —
وجودها الوحيد إنه يمرّق فحص كفاية المدة، وما بتطلع من هالملف. النتيجة
إن أي تعديل على قاعدة القطع بينتقل لهون تلقائيًا، وما في تعريفان.
"""
from __future__ import annotations

from pathlib import Path

from .models.alignment import Alignment
from .models.assets import Asset, AssetsContract, Probe
from .models.project import Output
from .models.segments import SegmentsContract
from .timeline.quantize import quantize

#: هامش فوق مدة الصوت للأصول الاستقصائية. كبير بقصد: هدفها تمرق فحص
#: الكفاية، مش تمثّل أصلًا حقيقيًا.
_PROBE_MARGIN_S = 1.0


def _probe_assets(segments: SegmentsContract,
                  audio_duration: float) -> AssetsContract:
    """أصول وهمية **للسؤال فقط**. ما بتطلع من هالموديول.

    مبنيّة بعقد Phase 1 نفسه بقصد: لو تغيّرت متطلّبات `Asset` بيفشل
    البناء هون بدل ما يمرق شي ناقص لـ`quantize`.
    """
    # **`max(..., 0)` بقصد.** مدة صوت غير صالحة لازم يرفضها `quantize`
    # برسالتها، مش أن تنفجر هون بشكوى عن `probe` لأصل استقصائي ما
    # أنشأه أحد — تشخيص بيوجّه القارئ لمكان غلط.
    dur = max(audio_duration, 0.0) + _PROBE_MARGIN_S
    return AssetsContract(assets=tuple(
        Asset(segment_id=s.segment_id, source_type="local",
              provider="__probe__", provider_ref=f"__probe__{s.segment_id}",
              file_path=Path("__probe__"), sha256="0" * 64, license="__probe__",
              probe=Probe(width=1920, height=1080, fps=25.0, duration=dur),
              in_point=0.0)
        for s in segments.segments))


def visual_windows(output: Output, segments: SegmentsContract,
                   alignment: Alignment,
                   audio_duration: float) -> dict[int, tuple[float, float]]:
    """`{segment_id: (بداية, نهاية)}` بالثواني، من شبكة الإطارات.

    القيم مشتقّة من فهارس الإطارات، مش من توقيت الكلمات مباشرةً —
    فهي **بالضبط** اللي رح يرمّزه ffmpeg، بلا تقريب تاني.
    """
    tl = quantize(output, segments, alignment,
                  _probe_assets(segments, audio_duration), audio_duration)
    spf = 1.0 / output.fps
    return {s.segment_id: (round(s.f_start * spf, 6), round(s.f_end * spf, 6))
            for s in tl.visual_spans}


def required_seconds(output: Output, segments: SegmentsContract,
                     alignment: Alignment,
                     audio_duration: float) -> dict[int, float]:
    """المدة المطلوبة لكل مقطع — المُدخَل اللي الـResolver بيشتغل عليه."""
    # **ولا فحص إيجابية هون — كان كودًا ميتًا.** `quantize` بترفض أي
    # حدّ بصري غير متزايد («حدّ بصري غير متزايد») قبل ما نوصل، فالشرط
    # هون ما كان بينوصل إله أبدًا. الطفرة عليه مرقت، وهيك انكشف.
    # حارس ما بينقدر ينفشل بيوهم بأمان مش موجودًا.
    return {sid: round(b - a, 6) for sid, (a, b) in
            visual_windows(output, segments, alignment, audio_duration).items()}

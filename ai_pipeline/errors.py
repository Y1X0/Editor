"""أخطاء المسار — كل خطأ بيحمل رمز مرحلة، وما في `except Exception: pass`.

الرمز جزء من العقد مع المستخدم: الرسالة ممكن تتغيّر، الرمز لأ.
"""
from __future__ import annotations


class NurError(Exception):
    """أساس كل أخطاء المسار. الرمز بيتحدّد بالصنف، مش بالنداء."""

    code = "ERROR"

    def __str__(self) -> str:                      # noqa: D105
        return f"[{self.code}] {super().__str__()}"


class ContractError(NurError):
    """عقد ما بيطابق الـschema، أو بينكسر قاعدة دلالية."""

    code = "CONTRACT_ERROR"


class TextIntegrityError(NurError):
    """النص انحرف عن المصدر — ولا حرف بيتغيّر (§19)."""

    code = "TEXT_INTEGRITY_ERROR"


class AlignmentError(NurError):
    code = "ALIGNMENT_ERROR"


class AssetError(NurError):
    code = "ASSET_ERROR"


class TimelineError(NurError):
    code = "TIMELINE_ERROR"


class TypographyError(NurError):
    code = "TYPOGRAPHY_ERROR"


class FfmpegError(NurError):
    code = "FFMPEG_ERROR"


class QaError(NurError):
    """المخرَج نفسه ما طابق الخطة — آخر حارس قبل النشر."""

    code = "QA_ERROR"


class AgentError(NurError):
    """مخرَج الوكيل ما عبَر التحقّق، أو نفدت محاولات الإصلاح.

    بيوقف المسار **قبل** الحدّ الحتمي: ولا نصف نتيجة بتمرق للرندر.
    """

    code = "AGENT_ERROR"


class ProviderError(NurError):
    """فشل بالنقل مع المزوّد: انقطاع · تجاوز حدّ · مهلة · خطأ خدمة.

    منفصل عن `AgentError` بقصد: هاد «ما وصلنا لجواب»، وهداك «وصل جواب
    وما عبَر». الاتنان بيفشلوا مقفولًا، بس التشخيص مختلف.
    """

    code = "PROVIDER_ERROR"

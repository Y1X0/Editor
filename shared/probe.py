"""قراءة المصدر والتحقّق من المخرَج — بلا `ffprobe`، بقرار.

كل اللي هون موجود بـ`autoreel.cuts` و`autoreel.render` ومفحوص هناك.
مجموع هون عشان يكون واضحًا شو بينشارك.
"""
from autoreel.cuts import (                       # noqa: F401
    MIN_FFMPEG,
    VERIFIED_FFMPEG,
    check_ffmpeg,
    delivered,
    ffmpeg_version,
    probe,
    probe_duration,
    verify_source,
)
from autoreel.render import (                     # noqa: F401
    assert_output_not_mislabelled,
    probe_source,
    probe_source_full,
)

__all__ = [
    "probe", "probe_duration", "delivered", "verify_source",
    "probe_source", "probe_source_full", "assert_output_not_mislabelled",
    "check_ffmpeg", "ffmpeg_version", "VERIFIED_FFMPEG", "MIN_FFMPEG",
]

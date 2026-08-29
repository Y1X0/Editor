"""حساب الإطارات والعيّنات — تعريف واحد للثوابت.

`validate_fps` بترفض أي fps ما بيقسم الـsample_rate. `ai_pipeline.models
.project.Output` بتناديها بدل ما تعيد الشرط — تعريفان لنفس الثابت
بيفترقوا بصمت، وهاد سجلّ موثَّق بهالمستودع.
"""
from autoreel.graph import (                      # noqa: F401
    DEFAULT_SR,
    caption_frames,
    caption_sequence,
    offsets_of,
    piecewise,
    validate_fps,
)
from autoreel.sfx import (                        # noqa: F401
    frame_to_sample,
    samples_per_frame,
    seconds_to_frames,
)

__all__ = [
    "validate_fps", "piecewise", "offsets_of",
    "caption_frames", "caption_sequence",
    "frame_to_sample", "samples_per_frame", "seconds_to_frames", "DEFAULT_SR",
]

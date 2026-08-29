"""`project.json` — المدخلات الثابتة وقرارات المخرَج، مرة وحدة.

`project_id` هون **فقط**. تكراره بكل عقد كان بيولّد قاعدة تحقّق
(«project_id consistent») لمشكلة ما بتصير أصلًا لو ما تكرّر.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from shared.frames import validate_fps

from .base import SHA256, SLUG, StrictModel


class Output(StrictModel):
    """قرارات المخرَج — بتتّخذ مرة، وقبل الـtimeline."""

    width: int = Field(1080, ge=16, le=7680)
    height: int = Field(1920, ge=16, le=7680)
    fps: int = Field(30, ge=1, le=120)
    sample_rate: int = Field(48000, ge=8000, le=192000)

    @model_validator(mode="after")
    def _integer_samples_per_frame(self) -> "Output":
        """`sample_rate / fps` لازم يكون عددًا صحيحًا.

        `sample = frame × (sr // fps)` ضرب صحيح. لو القسمة مش صحيحة
        (29.97 مثلًا: 1601.6) بيصير الانزياح تراكميًا وصامتًا.
        """
        # تعريف واحد للثابت. `shared.frames.validate_fps` هي نفسها
        # اللي `autoreel` بتعتمد عليها، فالنظامان ما بيفترقوا بصمت.
        validate_fps(self.fps, self.sample_rate)
        if self.width % 2 or self.height % 2:
            raise ValueError("العرض والارتفاع لازم يكونوا أزواجًا (yuv420p)")
        return self

    @property
    def samples_per_frame(self) -> int:
        return self.sample_rate // self.fps


class Source(StrictModel):
    """بصمة المدخلات — عشان نعرف إذا الرندر لسا مطابقًا لمصدره."""

    script_sha256: SHA256
    audio_sha256: SHA256


class Provenance(StrictModel):
    """من أنتج هالمشروع وبأي أدوات — بلا هيك ما في إعادة إنتاج."""

    tool_version: str
    ffmpeg_version: str
    whisper_model: str | None = None
    llm_model: str | None = None
    llm_prompt_sha256: SHA256 | None = None
    llm_temperature: float | None = Field(None, ge=0.0, le=2.0)


class Project(StrictModel):
    project_id: SLUG
    source: Source
    output: Output = Output()
    theme: SLUG
    provenance: Provenance

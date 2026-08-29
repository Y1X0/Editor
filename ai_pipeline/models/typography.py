"""`typography.json` — أسلوب فقط.

انشال منه:
  · `shaping_engine` — في shaper واحد صحيح (Pillow+libraqm)، وأي قيمة
    تانية مكسورة. knob كل قيمه الأخرى غلط مش knob.
  · `rendered_image_path` — انقلاب طبقات: عقد المرحلة الأبكر ما بيقدر
    يشير لأثر مرحلة أمتّ. المسارات داخلية للـrasterizer.
  · `start` / `end` — مشتقّة من المقطع.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .base import SLUG, StrictModel

Animation = Literal["none", "fade", "fade_in_scale", "fade_in_up"]


class StyleOverride(StrictModel):
    """تجاوز لمقطع واحد. `None` = خُد من الـtheme."""

    font_size: int | None = Field(None, ge=8, le=400)
    text_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    max_lines: int | None = Field(None, ge=1, le=6)


class TypographySegment(StrictModel):
    segment_id: int = Field(ge=1)
    animation: Animation = "fade_in_scale"


class TypographyContract(StrictModel):
    theme: SLUG
    segments: tuple[TypographySegment, ...] = Field(min_length=1)
    overrides: dict[int, StyleOverride] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique_and_overrides_known(self) -> "TypographyContract":
        ids = [s.segment_id for s in self.segments]
        if len(set(ids)) != len(ids):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"معرّفات مكرّرة بالـtypography: {dup}")
        unknown = sorted(set(self.overrides) - set(ids))
        if unknown:
            raise ValueError(f"تجاوز لمقاطع مش موجودة: {unknown}")
        return self

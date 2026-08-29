"""`assets.json` — قرارات اللقطة + إثبات هويتها.

`required_duration` انشال: مشتق من الـtimeline. `sha256` انضاف: بلاه
ما في إعادة إنتاج — نتائج البحث بتتغيّر بين تشغيلة وتشغيلة.
`in_point` انضاف: من وين بالكليب نبلّش — قرار حقيقي كان ناقصًا بالبريف.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .base import SHA256, StrictModel

SourceType = Literal["stock", "local", "generated"]
Fit = Literal["cover", "contain"]
Motion = Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"]


class Probe(StrictModel):
    """اللي ffmpeg بيسلّمه فعلًا عن الملف — مش اللي المزوّد بيدّعيه."""

    width: int = Field(ge=16)
    height: int = Field(ge=16)
    fps: float = Field(gt=0)
    duration: float = Field(gt=0)


class Asset(StrictModel):
    segment_id: int = Field(ge=1)
    source_type: SourceType
    provider: str = Field(min_length=1)
    provider_ref: str = Field(min_length=1)
    file_path: Path
    sha256: SHA256
    license: str = Field(min_length=1)
    attribution: str | None = None
    probe: Probe
    in_point: float = Field(0.0, ge=0.0)
    fit: Fit = "cover"
    motion: Motion = "none"

    @model_validator(mode="after")
    def _in_point_inside(self) -> "Asset":
        if self.in_point >= self.probe.duration:
            raise ValueError(
                f"مقطع {self.segment_id}: in_point {self.in_point} "
                f"خارج مدة الأصل {self.probe.duration}"
            )
        return self


class AssetsContract(StrictModel):
    assets: tuple[Asset, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_per_segment(self) -> "AssetsContract":
        ids = [a.segment_id for a in self.assets]
        if len(set(ids)) != len(ids):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"أكتر من أصل لنفس المقطع: {dup}")
        return self

    def by_segment(self, sid: int) -> Asset:
        for a in self.assets:
            if a.segment_id == sid:
                return a
        raise KeyError(sid)

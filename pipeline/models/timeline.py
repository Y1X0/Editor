"""`timeline.json` — **الحدّ بين عالم الثواني وعالم الإطارات**.

مشتق بالكامل، ولا حدا بيكتبه بالإيد. بعد هالنقطة ما في ولا حساب
بالثواني — كل رقم بيدخل تعبير فلتر هو عدد إطارات أو عدد عيّنات.

من الـspike (F7): في **نوعين** من الـspans.
  visual : بتغطّي [0, total_frames) كاملة — الفيديو لازم يشتغل من
           الإطار صفر، والكلام بيبلّش بعده.
  text   : مدى ظهور النص فقط — بتترك فجوات مقصودة.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from .base import StrictModel


class Span(StrictModel):
    segment_id: int = Field(ge=1)
    f_start: int = Field(ge=0)
    f_end: int = Field(ge=1)             # نصف مفتوح

    @model_validator(mode="after")
    def _non_empty(self) -> "Span":
        if self.f_end <= self.f_start:
            raise ValueError(
                f"مقطع {self.segment_id}: مدى إطارات فاضٍ "
                f"[{self.f_start}, {self.f_end})"
            )
        return self

    @property
    def n_frames(self) -> int:
        return self.f_end - self.f_start


class Timeline(StrictModel):
    fps: int = Field(ge=1)
    sample_rate: int = Field(ge=8000)
    total_frames: int = Field(ge=1)
    visual_spans: tuple[Span, ...] = Field(min_length=1)
    text_spans: tuple[Span, ...] = Field(min_length=1)
    asset_in_frame: dict[int, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "Timeline":
        if self.sample_rate % self.fps:
            raise ValueError("sample_rate/fps لازم يكون صحيحًا")

        # visual: متلاصقة وبتغطّي كل الشريط، بلا فجوة ولا تداخل
        if self.visual_spans[0].f_start != 0:
            raise ValueError(
                f"الـspans البصرية لازم تبدأ من الإطار 0 — "
                f"بدأت من {self.visual_spans[0].f_start}"
            )
        for a, b in zip(self.visual_spans, self.visual_spans[1:]):
            if b.f_start != a.f_end:
                raise ValueError(
                    f"فجوة/تداخل بصري بين {a.segment_id} و{b.segment_id}: "
                    f"{a.f_end} != {b.f_start}"
                )
        if self.visual_spans[-1].f_end != self.total_frames:
            raise ValueError(
                f"الـspans البصرية لازم تنتهي عند {self.total_frames} — "
                f"انتهت عند {self.visual_spans[-1].f_end}"
            )
        total = sum(s.n_frames for s in self.visual_spans)
        if total != self.total_frames:
            raise ValueError(f"Σ الإطارات {total} != total_frames {self.total_frames}")

        # text: مرتّبة، بلا تداخل، وداخل الشريط
        for a, b in zip(self.text_spans, self.text_spans[1:]):
            if b.f_start < a.f_end:
                raise ValueError(
                    f"تداخل نصّي بين {a.segment_id} و{b.segment_id}"
                )
        for s in self.text_spans:
            if s.f_end > self.total_frames:
                raise ValueError(
                    f"مقطع {s.segment_id}: نص بيتجاوز نهاية الشريط "
                    f"({s.f_end} > {self.total_frames})"
                )

        vis_ids = {s.segment_id for s in self.visual_spans}
        missing = sorted({s.segment_id for s in self.text_spans} - vis_ids)
        if missing:
            raise ValueError(f"مقاطع نصّية بلا span بصري: {missing}")
        unknown = sorted(set(self.asset_in_frame) - vis_ids)
        if unknown:
            raise ValueError(f"asset_in_frame لمقاطع مش موجودة: {unknown}")
        return self

    @property
    def samples_per_frame(self) -> int:
        return self.sample_rate // self.fps

    @property
    def total_samples(self) -> int:
        """طول الصوت المثبَّت — `apad,atrim=end_sample=N` بيستعمله."""
        return self.total_frames * self.samples_per_frame

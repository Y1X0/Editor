"""`alignment.json` — مصدر الحقيقة الزمني الوحيد.

مشتق من الصوت، **وقابل للتحرير باليد**. لمحتوى ديني هاد شرط: لازم
تقدر تصلّح توقيتًا غلط بلا ما تعيد النسخ كله.

الفهرس `i` بيشير لموقع الكلمة **بالنص المصدر** بعد التقطيع على المسافات
— مش لموقعها بمخرَج Whisper. هاد اللي بيخلي `word_span` بالمقاطع تعني
شيئًا مستقرًّا.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from .base import StrictModel


class Word(StrictModel):
    i: int = Field(ge=0)
    text: str = Field(min_length=1)
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    conf: float | None = Field(None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> "Word":
        if self.end <= self.start:
            raise ValueError(f"كلمة {self.i} ({self.text!r}): end <= start")
        return self


class Alignment(StrictModel):
    method: str = Field(min_length=1)
    words: tuple[Word, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _contiguous_and_monotonic(self) -> "Alignment":
        for k, w in enumerate(self.words):
            if w.i != k:
                raise ValueError(
                    f"فهارس الكلمات لازم تكون 0..n-1 بالترتيب — "
                    f"بالموقع {k} لقينا i={w.i}"
                )
        # تداخل جزئي بين كلمتين مقبول (Whisper بيرجّعه)، بس البداية
        # لازم تكون غير متناقصة — وإلا الـspan ما بيعطي مدى صالحًا.
        for a, b in zip(self.words, self.words[1:]):
            if b.start < a.start:
                raise ValueError(
                    f"بدايات متراجعة: كلمة {a.i} تبدأ {a.start} "
                    f"وكلمة {b.i} تبدأ {b.start}"
                )
        return self

    def span_time(self, lo: int, hi: int) -> tuple[float, float]:
        """توقيت مدى نصف مفتوح [lo, hi) — **مشتق، ما بينخزَّن**."""
        if not 0 <= lo < hi <= len(self.words):
            raise ValueError(f"مدى خارج الحدود: [{lo}, {hi}) من {len(self.words)}")
        sub = self.words[lo:hi]
        return sub[0].start, max(w.end for w in sub)

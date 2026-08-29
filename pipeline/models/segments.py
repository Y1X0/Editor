"""`segments.json` — مخرَج Agent 1، أو مخرَج المقسِّم الحتمي.

**الوكيل ما بيكتب توقيتًا.** بيكتب مدى فهارس كلمات، والكود بيجيب الوقت
من `alignment.json`. النتيجة إن ستّ حالات فشل من قائمة QA بتصير
**مستحيلة بالبناء** بدل ما تنكون مفحوصة:

    start >= end · توقيت سالب · تداخل مقاطع · duration mismatch
    ترتيب معرّفات غلط · timestamps خارج مدى الصوت

`text_arabic` **صدى للقراءة البشرية فقط** — بينتقارن بايت-بايت مع
شريحة المصدر، وأي اختلاف بيرمي `TextIntegrityError` (§19).
"""
from __future__ import annotations

from pydantic import Field, model_validator

from .base import StrictModel


class Segment(StrictModel):
    segment_id: int = Field(ge=1)
    word_start: int = Field(ge=0)
    word_end: int = Field(ge=1)          # نصف مفتوح: [word_start, word_end)
    text_arabic: str = Field(min_length=1)
    visual_mood_prompt: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _span_non_empty(self) -> "Segment":
        if self.word_end <= self.word_start:
            raise ValueError(
                f"مقطع {self.segment_id}: مدى فاضي "
                f"[{self.word_start}, {self.word_end})"
            )
        return self


class SegmentsContract(StrictModel):
    segments: tuple[Segment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids_and_spans(self) -> "SegmentsContract":
        ids = [s.segment_id for s in self.segments]
        if len(set(ids)) != len(ids):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"معرّفات مكرّرة: {dup}")
        if ids != list(range(1, len(ids) + 1)):
            raise ValueError(f"المعرّفات لازم تكون 1..n بالترتيب — لقينا {ids}")
        for a, b in zip(self.segments, self.segments[1:]):
            if b.word_start < a.word_end:
                raise ValueError(
                    f"تداخل: مقطع {a.segment_id} بينتهي عند {a.word_end} "
                    f"ومقطع {b.segment_id} بيبدأ عند {b.word_start}"
                )
        return self

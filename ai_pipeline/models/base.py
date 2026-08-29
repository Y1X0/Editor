"""أساس كل العقود.

قرار: `extra="forbid"` — مفتاح زيادة بالعقد **بيفشل**، ما بينتجاهل.
الـLLM بيخترع مفاتيح، والتجاهل الصامت بيخلّي القرار المخترَع يمرق بلا أثر.

وقرار: `frozen=True` — العقد بعد ما ينقرا ما بيتغيّر. أي اشتقاق بيطلّع
قيمة جديدة، ما بيعدّل العقد. هيك «مصدر الحقيقة» بيضل واحدًا.
"""
from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SLUG = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]

_HEX6 = re.compile(r"^#[0-9A-Fa-f]{6}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )


def hex_to_rgb(s: str) -> tuple[int, int, int]:
    if not _HEX6.match(s):
        raise ValueError(f"لون غير صالح: {s!r} — المتوقَّع #RRGGBB")
    return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))

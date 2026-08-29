"""قراءة العقود وكتابتها — §2 و§3 من قائمة الفشل.

**دايمًا `model_validate_json`، أبدًا `model_validate(json.load(...))`.**
بالوضع الصارم، مصفوفة JSON بتتحوّل لـtuple لما تمرق من نصّ JSON، بس
لائحة بايثون بتنرفض. والأهمّ إن `"1"` مكان `1` بينرفض بالحالتين — وهاد
المقصود: الـLLM بيرجّع نصوصًا مكان أرقام، والقبول الصامت بيمرّر قرارًا
مخترَعًا للرندر.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import ContractError

M = TypeVar("M", bound=BaseModel)


def load(path: str | Path, model: type[M]) -> M:
    p = Path(path)
    if not p.is_file():
        raise ContractError(f"عقد مفقود: {p} (المتوقَّع {model.__name__})")
    raw = p.read_bytes()
    if not raw.strip():
        raise ContractError(f"عقد فاضي: {p}")
    try:
        return model.model_validate_json(raw)
    except ValidationError as e:
        first = e.errors()[0]
        # **JSON مشوَّه بيوصل هون كمان.** `ValidationError` تبع pydantic
        # فرع من `ValueError`، فأي `except ValueError` بعدها كود ميت —
        # وكان عندنا واحد، ورسالته «JSON غير صالح» ما كانت بتنطبع أبدًا.
        # التمييز بنوع الخطأ الأول: `json_invalid` = الملف مش JSON.
        if first["type"] == "json_invalid":
            raise ContractError(
                f"{p}: JSON غير صالح — {first['msg']}") from e
        loc = ".".join(str(x) for x in first["loc"]) or "(الجذر)"
        raise ContractError(
            f"{p}: {len(e.errors())} خطأ تحقّق — أولها عند `{loc}`: "
            f"{first['msg']}"
        ) from e


def save(path: str | Path, obj: BaseModel) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return p


def round_trip(obj: M) -> M:
    """بيتأكّد إن العقد بينكتب وبينقرا بلا خسارة — حارس للتطوير."""
    return type(obj).model_validate_json(obj.model_dump_json())


def contract_path(root: str | Path, name: str) -> Path:
    return Path(root) / "contracts" / f"{name}.json"


def load_json(path: str | Path) -> dict:
    """قراءة خام — للفحوص اللي بدها تشوف JSON قبل التحقّق."""
    p = Path(path)
    if not p.is_file():
        raise ContractError(f"ملف مفقود: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ContractError(f"{p}: JSON غير صالح — {e}") from e

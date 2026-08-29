"""النص المصدر — **غير قابل للتغيير**.

التقطيع على المسافات البيضاء فقط. ولا تطبيع، ولا حذف تشكيل، ولا
توحيد ألف/همزة. أي تطبيع بيصير **للمطابقة فقط** وبنسخة منفصلة، والنص
اللي بينرسم هو المصدر حرفيًا (§19).
"""
from __future__ import annotations

from pathlib import Path


def tokenize(script: str) -> tuple[str, ...]:
    """كلمات المصدر بالترتيب. `split()` بلا وسيط = أي مسافة بيضاء."""
    return tuple(script.split())


def load_script(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"النص المصدر فاضي: {path}")
    return text


def slice_text(tokens: tuple[str, ...], lo: int, hi: int) -> str:
    """شريحة المصدر كما هي — هاي اللي بتنرسم، وهاي اللي بتنقارن."""
    if not 0 <= lo < hi <= len(tokens):
        raise ValueError(f"مدى خارج الحدود: [{lo}, {hi}) من {len(tokens)} كلمة")
    return " ".join(tokens[lo:hi])

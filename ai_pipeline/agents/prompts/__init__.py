"""سجلّ الـprompts — **هوية الـprompt اللي أنتج كل قرار**.

`Provenance` تبع Phase 1 فيها `llm_prompt_sha256` وما فيها
`llm_prompt_version` (قرار مقفل). فالـsha هو **الرابط الوحيد** بين عقد
قديم والـprompt اللي أنتجه، والسجلّ هو اللي بيحوّله لإصدار. وعلى هاد
شرطان مش توصيتان:

  **(أ) كل `sha256` فريد.** نسخة/لصق بتعطي إصدارين بنفس الـsha، وقتها
  `sha -> version` ما بتعود دالة وعقد قديم بينسب لإصدارين.

  **(ب) الإصدارات append-only.** حذف `script/v1.md` بيخلي كل عقد قديم
  يشير لـsha ما إله مصدر — فقدان إعادة إنتاج بأثر رجعي. التعديل بيصير
  بإضافة `v2`؛ و`v1` بيضل بمكانه للأبد.

والـ`PromptRef` بينطلع **من السجلّ**، لا من مستدعٍ ولا من نموذج:

    ملف الـprompt ─► SHA-256 ─► registry ─► PromptRef ─► LLMRequest

وليس `user -> prompt_sha256`.

الأخطاء `ContractError` مش صنفًا جديدًا: `errors.py` append-only ومسموح
فيه `AgentError` و`ProviderError` بس، وعليه حارس. سجلّ مكسور خلل عقد
بالمعنى الدقيق — بيانات ما بتطابق مواصفتها.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ...errors import ContractError
from ..providers.base import PromptRef

HERE = Path(__file__).parent
REGISTRY = HERE / "registry.json"


@dataclass(frozen=True)
class PromptEntry:
    agent: str
    version: str
    sha256: str
    model_family: str
    created: str

    @property
    def relpath(self) -> str:
        return f"{self.agent}/{self.version}.md"


def sha256_of(path: Path) -> str:
    """بصمة **بايتات الملف**. مصدر الحقيقة، مش الرقم المسجَّل."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


_REQUIRED = {"agent", "version", "sha256", "model_family", "created"}


def load_registry(root: str | Path | None = None) -> tuple[PromptEntry, ...]:
    """بيقرا السجلّ **ويتحقّق منه بالكامل**. أي خلل بيرمي.

    السجلّ اللي بينقرا بلا تحقّق بيصير توثيقًا، مش حارسًا.
    """
    base = Path(root) if root is not None else HERE
    reg = base / "registry.json"
    if not reg.is_file():
        raise ContractError(f"سجلّ الـprompts مفقود: {reg}")
    try:
        raw = json.loads(reg.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ContractError(f"{reg}: JSON غير صالح — {e}") from e
    if not isinstance(raw, dict) or not isinstance(raw.get("prompts"), list):
        raise ContractError(f"{reg}: المتوقَّع {{'prompts': [...]}}")
    if not raw["prompts"]:
        raise ContractError(f"{reg}: سجلّ فاضي")

    entries: list[PromptEntry] = []
    for i, row in enumerate(raw["prompts"]):
        if not isinstance(row, dict):
            raise ContractError(f"{reg}: المدخل {i} مش كائنًا")
        if missing := sorted(_REQUIRED - set(row)):
            raise ContractError(f"{reg}: المدخل {i} ناقصه {missing}")
        if extra := sorted(set(row) - _REQUIRED):
            raise ContractError(f"{reg}: المدخل {i} فيه حقول زيادة {extra}")
        e = PromptEntry(**row)
        if len(e.sha256) != 64 or not all(c in "0123456789abcdef" for c in e.sha256):
            raise ContractError(
                f"{reg}: {e.relpath}: sha256 مش ٦٤ محرفًا ستّ عشريًا صغيرًا")
        entries.append(e)

    # (أ) sha -> version لازم تكون دالة
    seen_sha: dict[str, PromptEntry] = {}
    for e in entries:
        if (prev := seen_sha.get(e.sha256)) is not None:
            raise ContractError(
                f"{reg}: sha مكرّر بين {prev.relpath} و{e.relpath} — "
                f"`sha -> version` ما عادت دالة، وعقد قديم بينسب لإصدارين. "
                f"غيّر محتوى الجديد، ولا تعيد استعمال بصمة منشورة.")
        seen_sha[e.sha256] = e

    # (agent, version) لازم تكون فريدة كمان
    seen_key: set[tuple[str, str]] = set()
    for e in entries:
        if (e.agent, e.version) in seen_key:
            raise ContractError(f"{reg}: مدخل مكرّر لـ{e.relpath}")
        seen_key.add((e.agent, e.version))

    # الملف موجود، وبصمته الفعلية بتطابق المسجَّلة
    for e in entries:
        p = base / e.agent / f"{e.version}.md"
        if not p.is_file():
            raise ContractError(
                f"{reg}: {e.relpath} مسجَّل وملفه مفقود — "
                f"الإصدارات append-only، والمنشور ما بينحذف.")
        actual = sha256_of(p)
        if actual != e.sha256:
            raise ContractError(
                f"{e.relpath}: المحتوى تغيّر بلا رفع إصدار.\n"
                f"      المسجَّل: {e.sha256}\n"
                f"      الفعلي : {actual}\n"
                f"      الإصدار المنشور جزء من الـprovenance — أضف `v2` "
                f"بدل ما تعدّل هاد.")

    # ولا ملف prompt برّا السجلّ
    on_disk = {f"{p.parent.name}/{p.name}" for p in base.glob("*/*.md")}
    listed = {e.relpath for e in entries}
    if orphan := sorted(on_disk - listed):
        raise ContractError(
            f"{reg}: ملفات prompt مش مسجَّلة: {orphan} — "
            f"prompt بلا مدخل ما إله بصمة، فما بينقدر ينتنسب.")
    return tuple(entries)


def prompt_ref(agent: str, version: str,
               root: str | Path | None = None) -> PromptRef:
    """`PromptRef` **من السجلّ**. الـsha ما بيجي من المستدعي."""
    for e in load_registry(root):
        if (e.agent, e.version) == (agent, version):
            return PromptRef(agent=e.agent, version=e.version, sha256=e.sha256)
    known = ", ".join(sorted(x.relpath for x in load_registry(root)))
    raise ContractError(
        f"ما في prompt مسجَّل لـ{agent}/{version} — المسجَّل: {known}")


def prompt_text(agent: str, version: str,
                root: str | Path | None = None) -> str:
    """نصّ الـsystem prompt. بينقرا **بعد** ما السجلّ ينتحقّق."""
    ref = prompt_ref(agent, version, root)
    base = Path(root) if root is not None else HERE
    return (base / ref.agent / f"{ref.version}.md").read_text(encoding="utf-8")


def version_for_sha(sha256: str, root: str | Path | None = None) -> str:
    """الاتجاه العكسي: من عقد قديم لإصداره. هاد سبب شرط التفرّد."""
    for e in load_registry(root):
        if e.sha256 == sha256:
            return e.version
    raise ContractError(f"sha مش مسجَّل: {sha256[:16]}… — prompt مجهول")

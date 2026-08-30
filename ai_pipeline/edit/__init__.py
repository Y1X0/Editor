"""طبقة النيّة التحريرية — بين `segments` و`timeline`.

    alignment ──► segments ──► [ EditPlan ] ──► timeline ──► render

`plan.py` بيقول **ما يُسمح للمحرّر أن يقوله**، و`compiler.py` بيحوّله
لزمن. الحدّ بينهما صارم: النيّة نسبية، والزمن مطلق، و`quantize` هي
المعبر الوحيد.
"""
from .plan import (                                              # noqa: F401
    BeatProposal, CueProposal, EditPlan, EmphasisProposal, ShotProposal,
    trivial_plan,
)

__all__ = ["EditPlan", "BeatProposal", "ShotProposal", "EmphasisProposal",
           "CueProposal", "trivial_plan"]

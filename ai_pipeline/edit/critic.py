"""Creative Checks — **حكم على الخطة، لا على الملف**.

    Technical QA      هل نُفّذ كما خُطّط؟        ⟶ يرمي
    Creative Checks   هل الخطة نفسها جيدة؟      ⟶ يبلّغ

الفصل مقصود ومطلق. `qa/output.py` بترمي لأن الملف غلط — ما بينفع
تنشر ملفًا ناقص إطارات. والإيقاع والتكرار **أحكام**: بتتبلّغ ويتقرّر
عليها، وما بتوقف الترميز.

## ولا درجة مجمّعة — بقرار

`visual_score: 82` **ممنوع**، وعليه حارس بيمشي على حقول `Violation`.

الرقم المجمّع بيدّعي إنه قاس وهو حكم بلبوس رقم، وبيوقف السؤال بدل ما
يفتحه. وهالمستودع فيه **تمان حوادث موثّقة** انخدعنا فيها برقم يبدو
دقيقًا، وواحدة منها كلّفت ثماني جولات بجلسة وحدة.

فالمخرَج قائمة **مخالفات بدليل**: اسم القاعدة، والقيمة المقيسة، وأين.
والقارئ بيقدر يكذّب كل وحدة على حدة — وهاد الفرق بين قياس وحكم.
"""
from __future__ import annotations

from ..models.assets import AssetsContract
from ..models.timeline import Timeline
from .pacing import Violation, check_pacing
from .plan import EditPlan
from .repetition import hard_guards


def creative_checks(plan: EditPlan, timeline: Timeline,
                    assets: AssetsContract | None = None) -> list[Violation]:
    """كل المخالفات من كل الفاحصين، بترتيب ثابت.

    **الترتيب ثابت بقصد**: مخرَج متغيّر الترتيب بيخلّي كل مقارنة بين
    تشغيلتين ضجيجًا.
    """
    out = list(check_pacing(plan, timeline))
    out += hard_guards(timeline, assets)
    return sorted(out, key=lambda v: (v.rule, v.where))


def report(violations: list[Violation]) -> str:
    """تقرير للقراءة البشرية. `✓` لما ما في مخالفات — **بلا رقم**."""
    if not violations:
        return "✓ ولا مخالفة إبداعية"
    return "\n".join(f"✗ {v}" for v in violations)

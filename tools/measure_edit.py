"""جهاز قياس — **بيطبع، وما بيحكم**.

بيقرا عقود مخرَج واحد وبيطلّع القياسات الآلية اللي حسمها
`CREATIVE_BASELINE.md` §١. وبس.

## ⚠️ ولا حكم better/worse بهالملف

الأداة ما بتقارن تشغيلتين، وما بتقول «أحسن» ولا «أسوأ» ولا بتعطي
درجة. بتطبع أرقامًا ومخالفات، والحكم الإبداعي **خارجها بالكامل**
(§٢ بالبروتوكول: تلات قيم بشرية، بلا proxy).

وعليه حارس بيمسح مفردات الحكم من مصدر هالملف نفسه.

## ⚠️ وولا مقياس جديد

كل رقم هون بيجي من `pacing` أو `repetition` أو العقود. الأداة اللي
بتعرّف مقياسًا بتصير **التعريف التاني** اللي بيفترق بصمت — وهاد أكتر
شكل تكرّر بهالمستودع. لهيك حتى `_cv` بتنستورد ولا بتنعاد كتابتها.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_pipeline.edit.pacing import _cv, check_pacing          # noqa: E402
from ai_pipeline.edit.plan import EditPlan                     # noqa: E402
from ai_pipeline.edit.repetition import (                      # noqa: E402
    MAX_ASSET_SHARE, asset_runs, hard_guards,
)
from ai_pipeline.models.assets import AssetsContract           # noqa: E402
from ai_pipeline.models.segments import SegmentsContract       # noqa: E402
from ai_pipeline.models.timeline import Timeline               # noqa: E402

#: قواعد `check_pacing` اللي بتنحسب من الـtimeline وحدها.
TIMELINE_ONLY = ("min_shot_duration", "max_shot_duration", "shot_variance")

#: والباقي بيلزمه `EditPlan` — **ما إلها بديل**.
#:
#: تعويضها بـ`trivial_plan` كان بيخلّي الـbaseline يبيّن نظيفًا
#: **بالبناء لا بالاستحقاق**: `ShotProposal.motion` افتراضيها
#: `static`، فـ`static_share` بتمرق بـ100٪، و`motion_dominance` و
#: `motion_run` ما بيلاقوا شي، وبلا cues `cue_density` بتسكت،
#: وبطاقة موحّدة `energy_slump` بتسكت. يعني ٥ قواعد بتمرق مجّانًا.
#:
#: فالأداة **بتعلن عدم القياس** بدل ما تخترع خطة.
PLAN_ONLY = ("motion_dominance", "motion_run", "static_share",
             "cue_density", "energy_slump")


def _load(p: Path, model):
    return model.model_validate_json(p.read_bytes())


def measure(root: Path) -> str:
    """`root` مجلّد فيه العقود. بيرجّع التقرير كنصّ **حتمي الترتيب**."""
    out: list[str] = []
    tl = _load(root / "timeline.json", Timeline)

    plan_path = root / "edit_plan.json"
    plan = _load(plan_path, EditPlan) if plan_path.is_file() else None

    assets_path = root / "assets.json"
    assets = _load(assets_path, AssetsContract) if assets_path.is_file() else None

    segs_path = root / "segments.json"
    segs = _load(segs_path, SegmentsContract) if segs_path.is_file() else None

    # ── البنية ───────────────────────────────────────────────────────
    lens = [s.n_frames for s in tl.visual_spans]
    dur = tl.total_frames / tl.fps
    out.append("── البنية ─────────────────────────────────────────")
    out.append(f"المدة                 {dur:.2f}s ({tl.total_frames} إطار @ {tl.fps}fps)")
    out.append(f"لقطات بصرية           {len(tl.visual_spans)}")
    out.append(f"مقاطع نصّية            {len(tl.text_spans)}")
    if segs is not None:
        out.append(f"مقاطع بالعقد          {len(segs.segments)}")
    out.append(f"خطة تحرير             {'موجودة' if plan else 'غير موجودة'}")

    # ── أرقام الفاحصين ───────────────────────────────────────────────
    # `_cv` **مستورَدة** لا معادة — تعريف واحد.
    out.append("")
    out.append("── قياسات ─────────────────────────────────────────")
    out.append(f"معامل تباين اللقطات    {_cv(lens):.3f}")
    out.append(f"أقصر لقطة             {min(lens) / tl.fps:.2f}s")
    out.append(f"أطول لقطة             {max(lens) / tl.fps:.2f}s")

    share: dict[int, int] = {}
    for sp in tl.visual_spans:
        share[sp.segment_id] = share.get(sp.segment_id, 0) + sp.n_frames
    top = max(share.items(), key=lambda kv: (kv[1], -kv[0]))
    out.append(f"أعلى حصّة أصل          {top[1] / tl.total_frames:.1%} "
               f"(مقطع {top[0]}, الحدّ {MAX_ASSET_SHARE:.0%})")
    runs = asset_runs(tl)
    out.append(f"مقاطع الأصول المتّصلة   {len(runs)} من {len(tl.visual_spans)} لقطة")

    # ── المخالفات ────────────────────────────────────────────────────
    out.append("")
    out.append("── مخالفات ────────────────────────────────────────")
    rep = hard_guards(tl, assets)
    pac = check_pacing(plan, tl) if plan else []

    for v in sorted(pac + rep, key=lambda v: (v.rule, v.where)):
        out.append(f"✗ {v}")
    if not (pac or rep):
        out.append("ولا مخالفة من القواعد المقيسة")

    if plan is None:
        out.append("")
        out.append("── غير مقيس ───────────────────────────────────────")
        out.append("بلا `edit_plan.json` هالقواعد ما انقاست — "
                   "غيابها غياب قياس، لا نتيجة:")
        for r in PLAN_ONLY:
            out.append(f"  ? {r}")
        out.append(f"المقيس فعليًا: {len(TIMELINE_ONLY)} من "
                   f"{len(TIMELINE_ONLY) + len(PLAN_ONLY)} قاعدة إيقاع "
                   f"+ 3 قواعد تكرار")

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="قياسات آلية على عقود مخرَج واحد — بلا حكم")
    ap.add_argument("contracts", type=Path,
                    help="مجلّد فيه timeline.json (و edit_plan/assets/segments)")
    ap.add_argument("--env", type=Path,
                    help="ENV.json ليطبع البيئة مع القياس")
    a = ap.parse_args()

    if a.env and a.env.is_file():
        e = json.loads(a.env.read_text(encoding="utf-8"))
        print("── البيئة ─────────────────────────────────────────")
        for k in sorted(e):
            print(f"{k:<20}  {e[k]}")
        print()
    print(measure(a.contracts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

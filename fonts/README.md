# الخطوط

`Tajawal-Bold.ttf` · `Tajawal-ExtraBold.ttf` — Boutros International.

**رخصة الخط SIL OFL 1.1، نصّها الكامل بـ`OFL.txt` جنبه.** رخصة المشروع
(MIT بجذر المستودع) بتغطّي **الكود بس** — الخط مرخّص لحاله وشروطه
مختلفة، وأهمها إنه بينوزَّع بنفس الرخصة وما بينباع لحاله.

المصدر: https://github.com/google/fonts/tree/main/ofl/tajawal

## ليش Tajawal بالذات

بيدعم الوزن الثقيل اللي بيلزم الكابشن على خلفية متحركة، وبيتشكّل صح
مع HarfBuzz. **وما بيدعم صيغ العرض العربية القديمة** — وهاد سبب مباشر
لقرار «ولا `arabic_reshaper`» بـ`CLAUDE.md`: reshape قبل الرسم مع هالخط
بتعطي مربعات فاضية.

لو بدّلت الخط، شغّل الصور المرجعية من جديد وشوفها بعينك:

```bash
AUTOREEL_REGEN_GOLDEN=1 pytest tests/test_golden_caption.py
```

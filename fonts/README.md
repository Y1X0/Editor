# الخطوط

| الخط | الحامل | الرخصة | مين بيستعمله |
|---|---|---|---|
| `Tajawal-Bold` · `Tajawal-ExtraBold` | Boutros International | `OFL.txt` | `autoreel` |
| `Amiri-Regular` · `Amiri-Bold` | مشروع Amiri | `OFL-Amiri.txt` | `ai_pipeline` |
| `AmiriQuran-Regular` | مشروع Amiri | `OFL-Amiri.txt` | `ai_pipeline` (القرآني) |

**الرختان الاتنتان SIL OFL 1.1 بس حاملا الحقوق مختلفان** — لهيك ملفان
مش ملف. دمجهن بيضيّع إسنادًا بتلزمه الرخصة نفسها.

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


## ليش AmiriQuran للنص القرآني — مقيس

| الخط | ascent عند size=72 | أعلى حبر فعلي (علامات وقف) | |
|---|---|---|---|
| `Amiri-Bold` | 81 | **127** | تجاوز +46px |
| `AmiriQuran-Regular` | 131 | 128 | بيسع ✅ |

و**Tajawal ما بتقدر ترسم النص القرآني أصلًا**: ما فيها علامات الوقف
ولا الألف الخنجرية، فبتطلّع **دوائر منقّطة** مكانهن. مقيس على
`الٓمٓ ۚ ذَٰلِكَ ٱلْكِتَٰبُ` — شوف `docs/ai-video-pipeline/SPIKE-FINDINGS.md` / F2.

المصدر: https://github.com/google/fonts/tree/main/ofl/amiri

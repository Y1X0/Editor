# محرّك التحرير — مواصفة معمارية

**وثيقة تصميم. ولا سطر كود منتَج فيها، ولا واحد بينكتب قبل اعتمادها.**

الهدف الانتقال من «مولّد `EditPlan` أحسن» إلى **محرّر**: نظام بيقرّر
شو المشاهد لازم يشوف وليش، وبيراجع قراره قبل ما ينفّذه.

> **مقيَّدة بـ`CREATIVE_BASELINE.md`.** التنفيذ ما بيبلّش قبل baseline
> محفوظ ومجمّد. هالوثيقة **تصميم**، فمسموحة الآن؛ وأول commit تنفيذي
> ممنوع قبل الخطوة ٣.

---

## ٠· اللي بينبنى فوقه، وما بينلمس

الطبقات اللي أثبتت نفسها **مجمّدة**. البناء فوقها لا استبدالها:

```
مجمّد كليًّا (ولا بايت):
  autoreel/ · shared/ · ai_pipeline/qa/ · ai_pipeline/io/
  ai_pipeline/validation/ · ai_pipeline/renderer/
  models/segments.py · models/alignment.py · models/typography.py
  models/project.py · models/assets.py
  timeline/quantize.py         ← سلطة الإطارات، ما بتتغيّر

مجمّد سلوكيًّا (بينمدّد، ما بينعدّل):
  edit/pacing.py · edit/repetition.py    ← ١١ قاعدة، تبقى كما هي
  agents/runner.py                        ← الحواجز الأربعة
  agents/prompts/registry.json            ← append-only
```

و**قاعدة الوكيل ما بتتغيّر**: ولا وكيل بيقدر يكتب `start` ولا `end`
ولا `duration` ولا `frame` ولا مسار ملف. `FORBIDDEN_FIELD_NAMES`
بتبقى، والمترجم وحده بيحوّل الوزن النسبي لإطارات.

---

## ١· أربعة اعتراضات على التصميم المقترح — وحلولها

التصميم صحيح باتجاهه. وهاي أربع نقاط لو مرقت كما هي بتعيدنا لنفس
المكان بشكل جديد.

### ١.١ ⚠️ الأخطر: `Sequence Editor` و`Critic` بيتداخلوا مع طبقة **مقيسة** موجودة

المطلوب من `Sequence Editor` بالتصميم:

> هل أكرر composition؟ · هل أحتاج change of scale؟ · هل الـprogression
> واضح؟ · هل أُظهر الـpayoff قبل أوانه؟

**تلاتة من الأربعة محسومة اليوم بكود قابل للدحض:** `pacing.py` بتقيس
تكرار الحركة والتباين وحصّة السكون، و`repetition.py` بتقيس الهيمنة
والظهور المتفرّق والـrewind. إحدى عشرة قاعدة، كل وحدة بدليل ورقم،
وكلها ممسوكة بمطفرات.

لو حوّلناهن لوكيل LLM، بنكون **نقلنا قدرة مقيسة لقدرة غير قابلة
للقياس**. وهاد بالضبط عكس اتجاه المشروع كله.

**الحلّ — قسمة صريحة على معيار واحد:**

> **اللي بينكتب كقيد بينكتب كقيد. واللي بيلزمه معنى بس هو اللي
> بيروح للنموذج.**

| السؤال | مين بيجاوب | ليش |
|---|---|---|
| هل تكرّرت الحركة ٣ مرات؟ | **كود** | عدّ |
| هل حصّة أصل > ٣٥٪؟ | **كود** | نسبة |
| هل تكرّر نفس التأطير؟ | **كود** (بعد `AssetAnalysis.composition`) | مقارنة |
| هل تغيّر مقاس اللقطة بين لقطتين؟ | **كود** | `SCALE_ORDER` موجود |
| **ليش** هالتكرار مقصود؟ | **نموذج** | معنى |
| هل هاد كشف مبكّر للـpayoff؟ | **نموذج** | سرد |
| هل هاللقطة بتضيف معلومة بصرية؟ | **نموذج** | دلالة |

يعني `Sequence Editor` **مش وكيلًا** — هو وحدة قيود حتمية جديدة
(`edit/sequence.py`) بتمدّد `pacing`/`repetition` بقواعد التتابع
البصري. والنموذج بيدخل بعدها، وبس على الأسئلة الدلالية.

### ١.٢ حلقة `Critic → Revision` بلا حدّ ولا إثبات

نموذج بينقد مخرَج نموذج، ونموذج بيصلّح. بلا قيود هاي:

- **ما بتنتهي**: كل إصلاح ممكن يجرّ ملاحظة جديدة.
- **ما بتنقاس**: ما في طريقة تعرف إذا المراجعة حسّنت وللا خرّبت.
- **بتخبّي درجة**: «هالخطة أضعف» حكم مجمّع بصياغة نصّية.

**الحلّ — ثلاثة قيود، كلها قابلة للفحص:**

1. **جولة واحدة بالضبط.** نفس انضباط `MAX_ATTEMPTS = 2`
   بـ`runner.py`: محاولة + إصلاح واحد. ولا تالتة.

2. **الملاحظة بمفردات مغلقة** زي `Violation.rule`:
   `repetition` · `premature_reveal` · `weak_hook` · `continuity` ·
   `flat_progression` · `unmotivated_cut`. أي نوع برّا القائمة
   **بيفشل بالـschema**، فما في «ملاحظة» حرّة بتصير درجة مقنّعة.

3. **المراجعة لازم تُثبت نفسها — وهاد الحارس الأهم:**

   ```
   قبول المراجعة  ⟺  (الملاحظة المستهدَفة اختفت)
                   ∧ (ولا مخالفة آلية جديدة انولدت)
                   ∧ (العقود ضلّت سليمة)
   ```

   ما تحقّقت؟ **بنرجع للمسوّدة**، وبنسجّل إن المراجعة فشلت. مراجعة
   بتزيد `asset_dominance` عشان تصلّح `weak_hook` **مرفوضة**.

   هيك المراجعة بتصير عملية قابلة للدحض بدل ما تكون ثقة بالنموذج.

### ١.٣ عدد نداءات النموذج بيتضاعف — وكل واحد سطح فشل

اليوم ٤ وكلاء. التصميم المقترح بيوصلهن ٩ (story · director · visual ·
sequencer · critic · reviser + التلاتة الحاليين)، وبسقف محاولتين
لكل واحد يعني **حتى ١٨ نداء** للفيديو الواحد.

**الحلّ — دمج وحذف، بلا خسارة قدرة:**

| المرحلة | القرار |
|---|---|
| Story Analyst | **بينضمّ للـScript Agent** — هو أصلًا بيقسّم، وبنية الـbeats نفس النداء لا نداء تاني |
| Edit Director | **وكيل** — النيّة التحريرية والبصرية سوا |
| Visual Search | **بينضمّ للـDirector** — «شو لازم نشوف» و«كيف ندوّر عليه» قرار واحد |
| Sequence Editor | **كود** (§١.١) |
| Critic | **وكيل**، دلالي فقط |
| Revision | **وكيل**، جولة وحدة |

الناتج **٣ نداءات LLM جديدة** فوق الموجود، لا ٦.

### ١.٤ «أصل + نافذة» بيلزمه **تعديل عقد مجمَّد**

المطلوب بالتصميم: `A@04–07` لا `A`. وهاد ما بينفّذ اليوم:

```python
class Timeline(StrictModel):
    asset_in_frame: dict[int, int]      # ← مفتاحه segment_id
```

المفتاح **مقطع**، فلقطتان على نفس المقطع بتتشاركا نقطة دخول وحدة —
حدّ موثَّق بـ`c08b3d6` وانترك بقصد وقتها.

النافذة لكل لقطة بتلزمها **حقل جديد بـ`models/timeline.py`**، مثلًا
`shot_in_frame: tuple[int, ...]` موازٍ لـ`visual_spans` بالطول
والترتيب.

> **هاد قرار على شجرة مجمّدة، وبيلزمه إذنك الصريح** — تمامًا زي
> القرار ١ اللي فتح `timeline/`. ما بعمله بلا موافقة، وبلاه §٨
> بالتصميم المقترح **ما بتنفّذ**.

---

## ٢· المعمارية المعتمَدة

```
  script + audio + alignment
            │
            ▼
  ┌───────────────────────┐
  │  SCRIPT + STORY       │  وكيل (موجود، بينمدّد)
  │  تقسيم + beats + دور  │  ──► SegmentsContract + StoryModel
  │  + editorial_function │
  └───────────┬───────────┘
              ▼
  ┌───────────────────────┐
  │  EDIT DIRECTOR        │  وكيل (جديد)
  │  لقطات · أوزان · نيّة  │  ──► DraftPlan (EditPlan + استراتيجية)
  │  + استراتيجية بصرية    │
  └───────────┬───────────┘
              ▼
  ┌───────────────────────┐
  │  RESOLVER             │  **كود** (موجود، بينمدّد)
  │  أصل + نافذة صالحة    │  ──► AssetsContract + تفسير لكل اختيار
  └───────────┬───────────┘
              ▼
  ┌───────────────────────┐
  │  SEQUENCE CONSTRAINTS │  **كود** (جديد)
  │  قيود التتابع البصري   │  ──► [Violation]
  └───────────┬───────────┘
              ▼
  ┌───────────────────────┐
  │  EDITORIAL CRITIC     │  وكيل (جديد) — **دلالي فقط**
  │  بياخد المخالفات      │  ──► Critique (مفردات مغلقة)
  │  الآلية كمُدخَل         │
  └───────────┬───────────┘
              ▼
  ┌───────────────────────┐
  │  REVISION             │  وكيل (جديد) — جولة وحدة
  │  + حارس الإثبات       │  ──► FinalPlan أو **رجوع للمسوّدة**
  └───────────┬───────────┘
              ▼
     compile_plan ──► quantize ──► render        (كلها مجمّدة)
```

**والناقد بياخد المخالفات الآلية كمُدخَل** — مش بيعيد اكتشافها. هيك
ما بينسأل «هل في تكرار؟» (الكود جاوب) بل **«هالتكرار مبرَّر سرديًا
وللا لأ؟»**، وهاد السؤال الوحيد اللي بيلزمه نموذج.

---

## ٣· العقود الجديدة

كلها `StrictModel` · `frozen` · `extra="forbid"` · مفردات مغلقة ·
وكلها تحت `FORBIDDEN_FIELD_NAMES`.

### ٣.١ `edit/story.py` — `StoryModel`

```python
EditorialFunction = Literal[
    "introduce", "contrast", "explain", "escalate",
    "surprise", "demonstrate", "reinforce", "reveal", "conclude"]
```

`role` بيقول **وين إحنا بالقصة**. `editorial_function` بيقول **شو
لازم يعمل هالجزء للمشاهد**. الاتنين ضروريان: `problem` وحدها ما
بتفرّق بين شرح المشكلة وتصعيدها.

### ٣.٢ `edit/plan.py` — إضافات على `BeatProposal`/`ShotProposal`

| حقل | على | القيم |
|---|---|---|
| `function` | beat | `EditorialFunction` |
| `strategy` | shot | `literal` · `contrast` · `metaphor` · `consequence` · `detail` |
| `concept` | shot | نصّ ≤ ٢٠٠ حرف — **الفكرة، لا الملف** |
| `avoid` | shot | مفردات مغلقة: `literal_text` · `generic_stock` · `same_class_as_previous` |
| `repeat_reason` | shot | إلزامي لما `continuity == "return"` |

**`repeat_reason` هو حلّ §٩ عندك.** التكرار بيضل ممنوعًا بالحارس
القاطع، **إلا لما ينكون معلَنًا**: `A → B → A` بتمرق فقط لو اللقطة
التالتة قالت `continuity="return"` وأعطت سببًا. تكرار معلَن قرار
قابل للمراجعة؛ تكرار صامت خلل. والحارس ما بيضعف — بيصير بيسأل عن
**إعلان**.

### ٣.٣ `edit/critique.py` — `Critique`

```python
FindingType = Literal[
    "repetition", "premature_reveal", "weak_hook",
    "continuity", "flat_progression", "unmotivated_cut"]

class Finding(StrictModel):
    kind: FindingType
    where: tuple[int, ...]        # beat_id أو shot_id
    reason: str = Field(min_length=1, max_length=300)
```

**ولا حقل درجة، ولا `severity` رقمية.** الترتيب بالخطورة إغراء
مباشر لجمعها.

### ٣.٤ `models/timeline.py` — `shot_in_frame` ⚠️

الحقل الوحيد المطلوب على شجرة مجمّدة (§١.٤). **موقوف على إذنك.**

---

## ٤· الملفات — بالضبط

### بينتضاف

```
ai_pipeline/edit/story.py           StoryModel + EditorialFunction
ai_pipeline/edit/critique.py        Critique + Finding
ai_pipeline/edit/sequence.py        قيود التتابع البصري (كود)
ai_pipeline/edit/revise.py          حارس إثبات المراجعة
ai_pipeline/agents/director.py      Edit Director
ai_pipeline/agents/critic_agent.py  Editorial Critic
ai_pipeline/agents/reviser.py       Revision
ai_pipeline/agents/prompts/director|critic|reviser/v1.md
tests/aipipeline/test_story.py · test_sequence.py · test_critique.py
tests/aipipeline/test_revise.py · test_agent_director.py
tests/aipipeline/test_agent_critic.py · test_agent_reviser.py
tests/aipipeline/fixtures/llm/{director,critic,reviser}_v1/
```

### بينتعدّل

| ملف | التعديل | خطورة |
|---|---|---|
| `edit/plan.py` | ٥ حقول جديدة + حارس `repeat_reason` | متوسّطة |
| `agents/script.py` | يطلّع `StoryModel` كمان | متوسّطة |
| `agents/resolver.py` | اختيار **نافذة** لا ملف · `explain()` | متوسّطة |
| `agents/scoring.py` | `explain()` يرجّع ✓/✗ لكل حدّ | منخفضة |
| `edit/compiler.py` | يمرّر نوافذ اللقطات | متوسّطة |
| `edit/critic.py` | يمرّر المخالفات للناقد الدلالي | منخفضة |
| `cli.py` | التوصيل + حفظ `edit_plan.json` | متوسّطة |
| `prompts/registry.json` | ٣ مدخلات (append-only) | منخفضة |
| **`models/timeline.py`** | **`shot_in_frame`** | ⚠️ **مجمّد — بإذن** |

### ما بينلمس

`autoreel/` · `shared/` · `timeline/quantize.py` · `validation/` ·
`qa/` · `io/` · `renderer/` · `models/{segments,alignment,typography,project,assets}.py`
· `edit/pacing.py` · `edit/repetition.py` · `agents/runner.py`

---

## ٥· تفسير الاختيار — «ليش A غلب B»

§٣ عندك: مش `A = 8.73`. الحدود الثمانية موجودة بـ`scoring.py` مفصولة
أصلًا، و`terms()` بترجّع القاموس بلا جمع. الناقص **العرض**:

```
لقطة 4 — concept: "consequence of choosing product first"

  المرشّح              دلالي  مقاس  حركة  تأطير  مدة  استمرار
  cat_hands_desk@4-7     ✓     ✓     ✓     ✓     ✓      —     ← اختير
  cat_office_wide        ✓     ✗     ✓     ✗     ✓      —
  cat_person_talk        ✗     ✓     ✗     ✓     ✓      —
```

الرقم بيضل داخليًّا للترتيب (ترتيب كلّي لازم لاختيار ملف واحد)،
و**اللي بينعرض ✓/✗ لكل حدّ**. وحارس `test_the_selection_score_never_leaves_choose`
بيضل شغّالًا.

---

## ٦· اختبار كل قرار

لكل حارس جديد: **الحالة الصحيحة · الحالة الخاطئة · طفرة تعطّله ·
الطفرة لازم تفشّل الفحص.**

| القرار | الفحص اللي بيثبته | الطفرة |
|---|---|---|
| الوكيل ما بيكتب زمنًا | `FORBIDDEN_FIELD_NAMES` على الحقول الجديدة | ضيف `duration` لـ`ShotProposal` |
| `repeat_reason` إلزامي عند `return` | بناء `return` بلا سبب بيرمي | شيل الشرط |
| التكرار المعلَن بيمرق | `A→B→A` معلَن بيعدّي، وصامت بيتبلّغ | خلّي الحارس يتجاهل الإعلان |
| المراجعة بتثبت نفسها | مراجعة بتزيد مخالفة **بتنرفض** | اقبلها بلا فحص |
| جولة وحدة | جولتان بترميا | ارفع السقف |
| الناقد بلا درجة | حارس AST على `critique.py` | ضيف `severity: int` |
| الناقد بياخد المخالفات كمُدخَل | الـprompt بيحوي المخالفات الآلية | شيلهن |
| قيود التتابع كود لا نموذج | حارس شجرة: `sequence.py` بلا استيراد وكيل | استورد `LLMClient` |
| النافذة لكل لقطة | لقطتان على نفس المقطع بنافذتين مختلفتين | ارجع لمفتاح المقطع |
| الترحيل | `trivial_plan` بيعطي نفس الـtimeline بايت-بايت | — |

**وبوابة الترحيل بتضل قائمة:** أي تعديل على `compiler.py` أو
`plan.py` لازم يبقي `trivial_plan` مطابقًا للمسار القديم.

---

## ٧· الترتيب — وكل مرحلة إلها baseline

| # | المرحلة | بيلمس منتَجًا؟ |
|---|---|---|
| ٠ | **baseline محفوظ** (`CREATIVE_BASELINE.md` §٧) | لا |
| ١ | `shot_in_frame` — **بإذن صريح** | ⚠️ عقد مجمّد |
| ٢ | `StoryModel` + `editorial_function` | نعم |
| ٣ | حقول الاستراتيجية + `repeat_reason` | نعم |
| ٤ | `sequence.py` — قيود التتابع (كود) | لا (إضافة) |
| ٥ | Edit Director | نعم |
| ٦ | الـResolver: نافذة + `explain()` | نعم |
| ٧ | `Critique` + الناقد الدلالي | نعم |
| ٨ | المراجعة + حارس الإثبات | نعم |
| ٩ | التوصيل بـ`cli.py` خلف `--editorial` | نعم |

**كل مرحلة**: طقم أخضر · مطفرات · خط أساس مقاس · commit مستقل.
و`--editorial` بيضل **مطفيًا افتراضيًا** لحد ما المقارنة A/B تمرق.

---

## ٨· اللي هالتصميم ما بيحلّه

- **ما بيضمن مونتاجًا أحسن.** بيضيف قرارات وقيودًا ومراجعة؛ وهل
  النتيجة أحسن **بيتقرّر بـ`CREATIVE_BASELINE.md` وحده**.
- **الناقد لسا نموذجًا.** ممكن يلاقي مشكلة مش موجودة، أو يفوّت وحدة.
  حارس الإثبات بيحدّ الضرر، ما بيلغيه.
- **`concept` نصّ حرّ.** الحقل الوحيد غير المغلق بالتصميم، ولازم
  يكون: الفكرة البصرية ما بتنحصر بقائمة. وخطره معلَن — بيمرق للـ
  Resolver كنيّة بحث، لا كأمر.
- **ولا شي بيقرا الصورة.** كل «بصري» هون من `AssetAnalysis` المكتوبة
  بشريًا. نموذج رؤية ممنوع بقرار قائم.

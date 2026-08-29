# Phase 3 — طبقة الوكلاء · **مواصفة مقفلة**

| | |
|---|---|
| **الحالة** | **SPEC-LOCKED · 0 سطر تنفيذ** |
| قُفلت على | `040a628` (نهاية Phase 2) |
| التنفيذ | **ممنوع** حتى إشارة بدء صريحة من المالك |
| مرجع الـAPI | Claude API skill · النموذج `claude-opus-5` |

> هالملف **عقد**، مش اقتراحًا. أي انحراف عنه وقت التنفيذ بيلزمه موافقة
> صريحة، مش اجتهادًا. البنود المعلَّمة **«غير قابل للتفاوض»** بيلزمها
> إعادة فتح المواصفة.

---

## ١ · المعمارية

```
النص المصدر ─┐                        ← غير موثوق (حقن مُحتمَل)
audio.wav   ─┴─► alignment.json       ← حتمي، مصدر الحقيقة الزمني
                     │
   ┌─────────────────┴───────────────────────────────┐
   │  AgentHarness  (ai_pipeline/agents/runner.py)   │
   │                                                  │
   │  prompt vN ──► LLMClient ──► نصّ خام             │
   │                   │                              │
   │            ┌──────┴──────┐                       │
   │            │  Proposal   │  ← schema **ضيّق**     │
   │            │   (DTO)     │    (اللي مسموح يقوله)  │
   │            └──────┬──────┘                       │
   │                   │  adapter حتمي                 │
   └───────────────────┼──────────────────────────────┘
                       ▼
              عقد Phase 1 كامل   ← الكود بيعبّي المشتقّات
                       │
        validation بنيوي + دلالي + سلامة النص (Phase 1/2)
                       │
                  ✅ PASS ONLY
                       ▼
              quantize() ─► timeline.json ─► FFmpeg ─► QA
```

### الفكرة الحاكمة — schema بطبقتين

> **اللي الوكيل مسموح يقوله (Proposal) أضيق من العقد اللي الرندر بياخده.**
> والموسّع بينهن **كود حتمي**، مش الوكيل.

النتيجة إن أخطر البنود ما بتصير «مرفوضة»، بتصير **غير قابلة للتعبير**:
ما في حقل بالـschema يكتب فيه الوكيل مسارًا، ولا معرّف أصل، ولا توقيتًا،
ولا نصًّا، ولا أمر ffmpeg.

---

## ٢ · حدّ القرار (AI Decision Boundary)

| القرار | المالك |
|---|---|
| **وين نقسم النص** (مدى فهارس الكلمات) | 🤖 LLM |
| **الـvisual mood** لكل مقطع | 🤖 LLM |
| **صياغة استعلام البحث** + must/avoid | 🤖 LLM |
| **اختيار animation** من enum مغلق | 🤖 LLM |
| الترتيب بين مرشّحين (لاحقًا) | 🤖 LLM |
| النص العربي نفسه | 💻 كود — من المصدر |
| كل توقيت (`start`/`end`/`duration`) | 💻 كود — من `alignment.json` |
| `total_frames` · `f_start` · `f_end` · العيّنات | 💻 كود — `quantize()` |
| رسم الفلاتر · أوامر ffmpeg | 💻 كود |
| مفاتيح الكاش · أسماء الملفات | 💻 كود |
| كل تحقّق وكل فحص مخرَج | 💻 كود |
| `file_path` · `sha256` · `license` · `probe` · `in_point` | 🔧 Resolver |
| وجود الأصل ومدّته الكافية | 🔧 Resolver + `quantize` |
| مسار الخط · اللون · الحجم | 🔧 Theme (بيانات مملوكة للكود) |
| الموافقة البصرية النهائية | 👤 إنسان |
| مناسبة الصورة للسياق الديني | 👤 **إنسان — بلا استثناء** |

---

## ٣ · عقود الوكلاء

### Agent 1 — Script / Pacing

**المدخل:** النص المصدر بكتلة موسومة · `alignment.json` مختصرًا
`[(i, word, start, end)]` · قيود الإيقاع من الـtheme.

**المخرَج المسموح — `SegmentsProposal`:**

```jsonc
{ "segments": [ { "segment_id": 1,
                  "word_start": 0,          // فهرس، مش وقت
                  "word_end": 5,
                  "visual_mood_prompt": "…" } ] }
```

**ما في `text_arabic`، ولا `start`، ولا `end`، ولا `duration`.** الموسّع
بياخد `slice_text(tokens, a, b)` وبيبني `Segment` تبع Phase 1.

> «timestamp injection attempt» بتصير **خطأ schema**، مش خطأ منطق:
> `extra="forbid"` بترفض `"start"` قبل ما توصل لأي مدقّق.

### Agent 2 — Visual Asset Director

**المخرَج المسموح — `AssetIntent`:**

```jsonc
{ "intents": [ { "segment_id": 1,
                 "query": "slow motion rain on dark window",
                 "must_include": ["rain","night"],      // ≤5
                 "must_avoid":   ["people","text"],     // ≤5
                 "shot_type": "wide|medium|macro|aerial|abstract",
                 "palette":   "charcoal|deep_blue|warm_gold|monochrome",
                 "motion":    "none|zoom_in|zoom_out|pan_left|pan_right" } ] }
```

**ولا حقل هوية أصل.** فـ«hallucinated asset identifier» ما إله مكان.
الـResolver لحاله بيملأ `provider` · `provider_ref` · `file_path` ·
`sha256` · `license` · `probe` · `in_point`.

### Agent 3 — Typography Director

**المخرَج المسموح — `TypographyProposal`:**

```jsonc
{ "segments": [ { "segment_id": 1,
                  "animation":  "none|fade|fade_in_scale|fade_in_up",
                  "font_role":  "quranic|body|emphasis",   // دور، لا مسار
                  "size_step":  -1,                        // −2..+2 من الـtheme
                  "color_role": "primary|muted|accent" } ] }
```

**مفردات مغلقة بالكامل.** ولا hex، ولا مسار، ولا `shaping_engine`.
الـtheme بيحوّل `font_role → fonts/AmiriQuran-Regular.ttf`. وبعد التحويل
بينمرق على `check_font_can_render` تبع Phase 2.

---

## ٤ · واجهة المزوّد

```python
@dataclass(frozen=True)
class LLMRequest:
    prompt: PromptRef            # (agent, version, sha256)
    system: str
    user_blocks: tuple[Block, ...]   # المصدر جوّا <source> </source>
    schema: type[BaseModel]      # الـProposal
    max_tokens: int
    effort: Literal["low","medium","high","xhigh","max"]
    timeout_s: float

@dataclass(frozen=True)
class LLMResponse:
    text: str
    parsed: BaseModel | None
    stop_reason: str             # end_turn · max_tokens · refusal · …
    stop_details: dict | None
    model: str
    request_id: str | None
    usage: dict

class LLMClient(Protocol):
    def complete(self, req: LLMRequest) -> LLMResponse: ...
```

| التطبيق | الدور |
|---|---|
| `AnthropicClient` | `messages.parse()` + `output_config={"format":…,"effort":…}` · `thinking={"type":"adaptive"}` · **`claude-opus-5`** |
| `RecordedClient` | يعيد تشغيل fixtures — **بلا شبكة وبلا مفاتيح** |
| `ScriptedFailureClient` | مخرَجات مكسورة عمدًا — للضوابط السالبة |

### خمس حقائق من الـAPI بتحكم التصميم

1. **`temperature` مرفوضة بـ400 على Opus 5** → ما في `temperature=0`.
   **الحتمية بتجي من تثبيت العقد، لا من المُعايِن.**
   `Provenance.llm_temperature` بتضل `None` — وهاد صحيح مش نقص.
2. **`prefill` مرفوض بـ400** → structured outputs إلزامية مش تفضيلًا.
3. **`stop_reason: "refusal"` بيرجع HTTP 200** بجسم فاضي وبلا استثناء.
4. **`budget_tokens` مرفوض بـ400** → العمق بـ`output_config.effort`.
5. **الـSDK بيعيد المحاولة لحاله** (429/5xx/408/اتصال، افتراضي 2)
   و`timeout` افتراضي 10 دقائق → الوقت الجداري `timeout × (retries+1)`.

---

## ٥ · RecordedClient

```
tests/aipipeline/fixtures/llm/
├── script_v1/ok_three_segments.json
├── script_v1/ok_single_segment.json
├── script_v1/bad_extra_start_field.json      ← محاولة حقن توقيت
├── script_v1/bad_duplicate_ids.json
├── script_v1/bad_malformed.txt               ← مش JSON
├── script_v1/bad_prose_wrapper.txt           ← ```json + كلام حولها
├── visual_v1/bad_hallucinated_asset_id.json
├── typography_v1/bad_font_path.json
└── typography_v1/bad_enum_value.json
```

كل fixture: `text` + `stop_reason` + `usage` + `request_id` مزيّف.
`RecordedClient(key=(agent, prompt_version, case))` بيرجّعه حرفيًا.

**قواعد ثابتة:** ولا اختبار بيلمس الشبكة · ولا اختبار بيحتاج مفتاحًا ·
حارس `ast` بيمنع `import anthropic` على مستوى الموديول بأي مكان بـ
`ai_pipeline/` غير `agents/providers/anthropic_client.py`، وهناك **جوّا
الدالة**. استيراد الحزمة بينجح بلا الـSDK.

---

## ٦ · إصدار الـprompts

```
ai_pipeline/agents/prompts/
├── registry.json        {agent, version, sha256, model_family, created}
├── script/v1.md
├── visual/v1.md
└── typography/v1.md
```

- الـprompt **أثر إنتاج**: ملف نصّي مستقل، مش سلسلة جوّا الكود.
- **حارس:** `sha256(الملف) == registry.sha256` — تعديل بلا رفع إصدار
  **بيفشل الطقم**.
- الـsystem prompt **ثابت البادئة** ليشتغل prompt caching.

### ٦.١ — شرطان رسميان (مثبَّتان بقرار المالك)

`Provenance.llm_prompt_version` **مش رح ينضاف للعقد** (قرار مقفل).
فـ`llm_prompt_sha256` بيصير **الرابط الوحيد** بين عقد قديم والـprompt
اللي أنتجه. وعلى هاد:

> **(أ) كل `sha256` بـ`registry.json` فريد.**
> نسخة/لصق بتعطي إصدارين بنفس الـsha، وقتها `sha → version` ما بتعود
> دالة، وعقد قديم بيصير بينسب لإصدارين. حارس بيفشل على أي تكرار.

> **(ب) إصدارات الـprompts append-only.**
> **ممنوع حذف أو استبدال إصدار منشور.** حذف `script/v1.md` بيخلي كل
> عقد قديم يشير لـsha ما إله مصدر — يعني فقدان قابلية إعادة الإنتاج
> بأثر رجعي. التعديل بيصير بإضافة `v2`؛ و`v1` بيضل بمكانه للأبد.
> حارس بيفشل لو انشال إصدار من `registry.json` أو من القرص.

هالبندان **جزء من العقد**، مش توصية.

### ٦.٢ — سجلّ التشغيل

`projects/<id>/logs/agent_runs.jsonl`، سطر لكل محاولة:

```jsonc
{"ts":"…","agent":"script","prompt_version":"v1","prompt_sha256":"…",
 "provider":"anthropic","model":"claude-opus-5","request_id":"req_…",
 "effort":"high","attempt":1,"stop_reason":"end_turn",
 "usage":{"input":…,"output":…,"cache_read":…},
 "validation":"ok|schema_error|semantic_error","error_code":null,
 "contract_version":"1","duration_ms":…}
```

**ولا سرّ ولا مفتاح ولا متغيّر بيئة** — وعليه فحص بيمشّط الأثر على
أشكال المفاتيح.

---

## ٧ · سياسة الفشل وإعادة المحاولة

| الحالة | السلوك |
|---|---|
| 429 · 5xx · timeout · اتصال | الـSDK بيعيد (2) + محاولة خارجية **واحدة** بـjitter · **سقف وقت جداري صريح** |
| JSON مشوَّه / خطأ schema | **محاولة إصلاح واحدة بالضبط** — نرجّع نصّ خطأ التحقّق كرسالة user |
| نفس الفشل مرتين | **fail closed** — الخلل بالـprompt أو النموذج، مش بالعيّنة |
| خطأ دلالي (تداخل، تغطية ناقصة) | نفس القاعدة: إصلاح واحد ثم فشل |
| `stop_reason == "refusal"` | **ولا إعادة محاولة.** فشل فوري مع `stop_details.category` |
| `stop_reason == "max_tokens"` | **فشل** — مخرَج مقطوع مش مخرَجًا ناقصًا |
| 400 · 401 · 404 | فشل فوري بلا إعادة |
| نفاد المحاولات | `AgentError` بسجلّ كل محاولة ورمزها |

### القواعد الأربع — **غير قابلة للتفاوض**

```
1. extra="forbid"   إجباري على كل Proposal
2. stop_reason      يُفحص قبل أي قراءة لـcontent
3. الإصلاح          محاولة واحدة بالضبط — لا اثنتان
4. فشل AI           لا يشغّل rule segmenter — يفشل Closed
```

**ولا هبوط تلقائي للمنتج الحتمي.** المقسِّم القاعدي بينتشغّل بعلم صريح
(`--segmenter rule`) لا كاحتياطي صامت. الهبوط الصامت أخطر من الفشل:
بتفتكر إنك مشغّل مسار AI وأنت لأ.

**وسبب رفض الوكيل مش عابرًا:** نصّ ديني + رفض = إشارة لازم يشوفها
إنسان، مش شي نلفّ حوله بصياغة أنعم.

---

## ٨ · حدّ الثقة والأمان

**النص المصدر مُدخَل غير موثوق** بمعنى حقن الأوامر. ثلاث طبقات،
**بلا أي محاولة كشف**:

1. **الفصل** — التعليمات بالـ`system`؛ المصدر بكتلة `user` موسومة
   `<source>…</source>`، وأي وسم مطابق بالمصدر بينهرَّب.
2. **الاحتواء بالـschema (الأساس)** — حتى لو الحقن نجح ١٠٠٪، الوكيل ما
   عنده حقل يكتب فيه نصًّا ولا مسارًا ولا أمرًا. **أقصى ضرر ممكن:
   تقسيم بصري رديء.**
3. **الفحص بعد التوسيع** — `check_text_integrity` + `check_coverage` +
   `check_font_can_render`.

> **ما بنكشف الحقن، بنجعله بلا أثر.** الكشف سباق تسلّح؛ ضيق الـschema حدّ.

وكمان: المفاتيح من البيئة فقط · ولا مفتاح بعقد ولا سجلّ ولا رسالة خطأ ·
سقف إدخال بـ`count_tokens` قبل الإرسال · سقف `max_tokens` · سقف عدد
المقاطع.

---

## ٩ · الملفات

**جديدة — كلها داخل `ai_pipeline/` و`tests/aipipeline/`:**

```
ai_pipeline/agents/
├── schemas.py        SegmentsProposal · AssetIntent · TypographyProposal
├── expand.py         Proposal ──► عقد Phase 1   (حتمي، نقي)
├── runner.py         AgentHarness: نداء · تحقّق · إصلاح · سجلّ
├── prompts/          registry.json + script/v1.md + visual/v1.md + typography/v1.md
├── script.py · visual.py · typography.py
└── providers/
    ├── base.py       LLMClient · LLMRequest · LLMResponse · PromptRef
    ├── anthropic_client.py     (استيراد anthropic **داخل الدالة**)
    ├── recorded.py
    └── scripted.py
ai_pipeline/errors.py            +AgentError +ProviderError  (إضافة، بلا تعديل)
tests/aipipeline/
├── test_agent_schemas.py · test_agent_expand.py · test_agent_runner.py
├── test_agent_security.py · test_prompt_registry.py · test_provider_contract.py
└── fixtures/llm/…
```

**معدَّلة:** `pyproject.toml` (extra `ai`) · `ai_pipeline/CLAUDE.md`.

---

## ١٠ · الضوابط السالبة

**كل ضابط بيثبت أمرين:** الاستثناء وقع، **و** الجانب الحتمي ما اتلمس —
بفحص إن `contracts/` ما انكتب ولا ملف، وإن `quantize()` ما انتنادت (spy).

| # | الضابط | الطبقة اللي بتمسكه |
|---|---|---|
| 1 | JSON مشوَّه | `io/contracts` + runner |
| 2 | مخالف للـschema (حقل ناقص) | Proposal schema |
| 3 | **حقل زائد ممنوع** | `extra="forbid"` |
| 4 | enum غير صالح (`animation:"explode"`) | `Literal` |
| 5 | **معرّف أصل مهلوَس** | ما في حقل إله → مفتاح زائد |
| 6 | **مسار خط اعتباطي** | `font_role` مغلق |
| 7 | **محاولة حقن توقيت** (`"start":0.0`) | مفتاح زائد · `quantize` ما انتنادت |
| 8 | **حقن أوامر بالنص الديني** | schema + سلامة النص بايت-بايت |
| 9 | معرّفات مقاطع مكرّرة | `SegmentsContract` (Phase 1) |
| 10 | مخرَج ضخم (٥٠٠ مقطع) | سقف + `max_tokens` |
| 11 | فشل المزوّد (5xx) | `ScriptedFailureClient` |
| 12 | timeout | ↑ · سقف الوقت الجداري محترَم |
| 13 | نفاد المحاولات | ↑ · سجلّ فيه كل محاولة |
| 14 | **رفض** (`stop_reason=refusal`) | runner · **صفر إعادة محاولة** |
| 15 | **قطع** (`max_tokens`) | runner · فشل مش قبول جزئي |
| 16 | استجابة فاضية | runner |
| 17 | كلام حوالين الـJSON | parse |
| 18 | **الإصلاح مرة وحدة** | runner · محاولتان بالضبط |
| 19 | **ولا هبوط تلقائي** | runner · فشل الوكيل ≠ تشغيل القاعدي |
| 20 | **ولا سرّ بالأثر** | مشّاط على العقود والسجلّات |
| 21 | **حتمية الرندر** | نفس العقد → نفس بايتات `timeline.json` ونفس أمر ffmpeg |
| 22 | **prompt اتغيّر بلا إصدار** | registry (§6.1) |
| 23 | **`import anthropic` على مستوى الموديول** | `ast` |
| 24 | **sha مكرّر بالـregistry** | §6.1 (أ) |
| 25 | **حذف إصدار منشور** | §6.1 (ب) |

**وطفرات إلزامية على الحواجز الأربعة:** شيل `extra="forbid"` · شيل فحص
`stop_reason` · خلّي الإصلاح حلقة مفتوحة · خلّ فشل الوكيل يهبط للقاعدي.
**الأربعة لازم يفشّلوا الطقم** — وإلا الحاجز ديكور.

---

## ١١ · التبعيات

| | |
|---|---|
| `anthropic` | **extra اختيارية** `[project.optional-dependencies] ai` — **مش أساسية** |
| غيرها | **ولا واحدة** |

الطقم كله بيشتغل بلا `anthropic` مثبَّتة، وبلا شبكة، وبلا مفتاح.

---

## ١٢ · اللي ما بينلمس

| | |
|---|---|
| `autoreel/` | **ولا بايت** — hash الشجرة بيتفحص قبل وبعد |
| `shared/` | ولا تغيير |
| **العقود الستة تبع Phase 1** | ولا تغيير semantics |
| `validation/semantic.py` · `font.py` · `inputs.py` | ولا تغيير |
| `qa/output.py` · `timeline/quantize.py` · `io/contracts.py` | ولا تغيير |
| الـ157 فحصًا الحالية | ولا حذف ولا إضعاف · الضوابط السالبة بتضل |
| `pyproject.toml` | إضافة extra فقط |

---

## ١٣ · القرارات المقفلة

| # | القرار | الحسم |
|---|---|---|
| 1 | `Provenance.llm_prompt_version` | **لا يُضاف.** الإصدار بـ`agent_runs.jsonl`، و`registry.json` بيربط `sha256 → version` |
| 2 | `--segmenter rule` | **علم صريح فقط.** فشل AI = فشل Closed |
| 3 | `registry.json` | كل `sha256` **فريد** (§6.1 أ) |
| 4 | إصدارات الـprompts | **append-only** — ممنوع حذف أو استبدال منشور (§6.1 ب) |

---

**الحالة: SPEC-LOCKED · 0 سطر تنفيذ.**

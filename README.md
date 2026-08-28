# auto-reel

محرر ريلز أوتوماتيكي بالعربي: قص الصمت + زوم عند القطات + كابشن عربي محروق
مع تلوين كاريوكي. مبني على ffmpeg + Pillow + faster-whisper.

## التنصيب (Termux)

```bash
pkg install python ffmpeg libraqm harfbuzz fribidi
pip install --no-binary :all: --force-reinstall Pillow
pip install -r requirements.txt
python -c "from PIL import features; print('raqm:', features.check('raqm'))"   # لازم True
```

## التنصيب (لينكس / ماك)

```bash
pip install -r requirements.txt
python -c "from PIL import features; print('raqm:', features.check('raqm'))"
```

## الاستخدام

```bash
python -m autoreel.cli raw.mp4 -o reel.mp4
python -m autoreel.cli raw.mp4 --srt subs.srt -o reel.mp4    # بدون Whisper
python -m autoreel.cli raw.mp4 --no-cut --no-motion -o reel.mp4
python -m autoreel.cli raw.mp4 --sizes all -o reel.mp4        # ريلز + مربع + عريض
python -m autoreel.cli raw.mp4 --sizes all --preview-frames -o reel.mp4
python -m autoreel.cli raw.mp4 --dry-run -o reel.mp4          # اطبع أوامر ffmpeg بس
python -m autoreel.cli raw.mp4 --sfx -o reel.mp4              # مع مؤثرات صوتية
```

**المؤثرات الصوتية مطفية افتراضيًا** — `--sfx` بتشغّلها. بتضيف أصواتًا
قصيرة على أحداث الفيديو (قطة، ظهور كابشن، تغيّر زوم، بداية ونهاية)،
وبتخفض الكلام لـ٠.٧٠ عشان يضل في هامش. خريطة الأحداث بـ`config.json`
تحت `sfx.events`، والأصول بـ`assets/sfx/`. التفصيل بـ`CLAUDE.md`.

على فيديو جديد شغّل `--preview-frames` أول شي: بيطلّع إطار PNG من كل
مقاس بلا ترميز، فتشوف نافذة القص قبل ما تصرف دقايق. لو الوجه مقصوص
بالمربع، عدّل `geometry.crop_bias` (أصغر = النافذة بتطلع لفوق).

أول تشغيل بينزّل موديل Whisper (~٥٠٠MB للـ small). التفريغ بينحفظ بملف
`raw.small.ar.words.json` جنب الفيديو — الموديل واللغة جزء من الاسم،
فتغييرهن بالconfig بيفرّغ من جديد بدل ما يرجّع نتيجة قديمة.

## المخرجات

`reel` 1080×1920 · `square` 1080×1080 · `wide` 1920×1080 · H.264 · الصوت مقصوص مع الصورة بنفس التوقيت.

## المتطلبات الخارجية

### نسخة ffmpeg

| | |
|---|---|
| **مفحوصة** | **7.0+** — كل أرقام المشروع مقاسة عليها |
| الأدنى المسموح | 6.0 (بيشتغل، بيطلع تحذير) |
| تحت 6.0 | بيفشل صراحة |

`cli` بتفحص النسخة بأول تشغيلة (`cuts.check_ffmpeg`).

**ليش الفحص موجود:** انكتب المشروع كله وكل أرقامه مقاسة على 7.0.2،
وطلع على 6.1.1 إن `amix=duration=first` بتعطي **١٢٨٠ عيّنة أقل** —
الصوت بينقصّ ٢٦.٧ms والأداة بتقول "تمّ بنجاح". أربع اختبارات بتفشل
هناك وهي ناجحة هون.

الطول انتثبّت **بالبناء** بعدها (`apad,atrim=end_sample=N` بـ
`graph.sfx_chain`) فالفرق ما عاد يقدر يظهر، بس الدرس أعمّ: **"كل
الاختبارات خضراء" بلا ذكر النسخة ادعاء ناقص.** فحص النسخة شبكة
أمان، مش الحلّ.

### ffprobe

**مش مطلوب.** الأبعاد ووجود الصوت والمدة كلهن
بينقروا من نداء `ffmpeg -i` واحد. مقصود: تثبيتات ffmpeg الثابتة
(الشائعة على Termux) كتير منها بلا `ffprobe`.

الثمن إن المدة بتنقرا من سطر `Duration: HH:MM:SS.ss` يعني **مقرَّبة
لجزء المئة** (فرق ≤٥ms عن `ffprobe`). ما إله أثر إلا مع `--no-cut`،
والتفصيل بـ`ISSUES.md`. وملف بلا مدة (`Duration: N/A` — تيار حي أو
خام) بيفشل صراحة بدل ما ينخمّن.

## الاختبارات

```bash
pip install -r requirements-dev.txt
pytest
pytest -m "not golden"    # لو مكدّس الخطوط عندك مختلف
```

الاختبارات اللي بتشغّل ffmpeg فعليًا بتفترض **7.0+**. لو نسختك أقدم
اذكرها مع أي بلاغ فشل — الرقم جزء من النتيجة مش تفصيلًا حولها.

## ملاحظة

كل التفاصيل التقنية والمطبّات موثّقة بـ`CLAUDE.md` — اقرأه قبل ما تعدّل
على الكابشن.
